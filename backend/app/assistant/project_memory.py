from __future__ import annotations

import math
from difflib import SequenceMatcher
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.services import metadata_store
from app.services.tenant_access import current_access_context

DEFAULT_POLICY = {
    "enabled": True,
    "auto_recall": True,
    "retention_days": 90,
    "max_entries": 200,
    "allowed_kinds": [
        "chart", "model", "report", "explanation", "statistical_result",
        "root_cause", "decision_scenario", "analysis_result",
    ],
}

_RECALL_HINTS = (
    "session précédente", "session precedente", "d'avant", "d’avant", "ancien", "ancienne",
    "précédent", "precedent", "précédente", "precedente", "retrouve", "retrouver",
    "rappelle", "rappeler", "mémoire", "memoire", "autre session", "dernière session",
    "derniere session", "analyse d'avant", "analyse d’avant", "modèle d'avant", "modele d'avant",
    "graphique d'avant", "rapport d'avant",
)


# v2.37 — local semantic recall.  This dictionary intentionally stays small,
# auditable and domain-oriented.  It expands equivalent business/analytics
# concepts without sending memory contents to an external embedding service.
_SEMANTIC_PHRASES = {
    "revenue": ("sales", "vente", "ventes", "revenu", "revenus", "chiffre d affaires", "chiffre d'affaire", "ca"),
    "profit": ("profit", "profits", "benefice", "benefices", "bénéfice", "bénéfices", "marge", "margin"),
    "geography": ("region", "regions", "région", "régions", "geographie", "géographie", "territoire", "country", "pays", "zone"),
    "forecast": ("forecast", "forecasting", "prevision", "prévision", "previsions", "prévisions", "projection", "tendance future"),
    "anomaly": ("anomalie", "anomalies", "anomaly", "outlier", "outliers", "valeur atypique"),
    "model": ("modele", "modèle", "model", "predictif", "prédictif", "prediction", "prédiction", "automl"),
    "chart": ("graphique", "graph", "chart", "visualisation", "visualization", "courbe", "histogramme"),
    "analysis": ("analyse", "analysis", "etude", "étude", "resultat", "résultat", "insight"),
    "quality": ("qualite", "qualité", "quality", "nettoyage", "missing", "manquant", "doublon"),
    "root_cause": ("cause racine", "root cause", "pourquoi", "driver", "facteur explicatif"),
}
_KIND_HINTS = {
    "model": {"model"},
    "chart": {"chart"},
    "report": {"report"},
    "analysis": {"analysis_result", "statistical_result", "explanation", "root_cause", "decision_scenario"},
    "forecast": {"analysis_result", "model"},
    "anomaly": {"analysis_result"},
}


def scope_for_context(context: Any) -> tuple[str, str | None, str | None]:
    access = current_access_context()
    requested_workspace = getattr(context, "workspaceId", None)
    if access is not None:
        if requested_workspace and str(requested_workspace) != str(access.workspace_id):
            raise PermissionError("Le contexte assistant ne correspond pas au workspace authentifié.")
        workspace_id = str(access.workspace_id)
        return f"workspace:{workspace_id}", workspace_id, str(access.user_id)
    if requested_workspace:
        workspace_id = str(requested_workspace)
        return f"workspace:{workspace_id}", workspace_id, None
    return "local:default", None, None


def get_policy(scope_id: str) -> dict[str, Any]:
    row = metadata_store.fetch_one(
        "SELECT policy_json FROM assistant_project_memory_policy WHERE scope_id=:scope",
        {"scope": scope_id},
    )
    policy = dict(DEFAULT_POLICY)
    if row:
        loaded = metadata_store.json_loads(row.get("policy_json"), {}) or {}
        if isinstance(loaded, dict):
            policy.update(loaded)
    return _normalize_policy(policy)


def save_policy(scope_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    policy = get_policy(scope_id)
    policy.update({k: v for k, v in updates.items() if k in DEFAULT_POLICY})
    policy = _normalize_policy(policy)
    now = metadata_store.utcnow()
    exists = metadata_store.fetch_one(
        "SELECT scope_id FROM assistant_project_memory_policy WHERE scope_id=:scope",
        {"scope": scope_id},
    )
    params = {"scope": scope_id, "policy": metadata_store.json_dumps(policy), "updated": now}
    if exists:
        metadata_store.execute(
            "UPDATE assistant_project_memory_policy SET policy_json=:policy,updated_at=:updated WHERE scope_id=:scope",
            params,
        )
    else:
        metadata_store.execute(
            "INSERT INTO assistant_project_memory_policy(scope_id,policy_json,created_at,updated_at) VALUES(:scope,:policy,:updated,:updated)",
            params,
        )
    _enforce_retention(scope_id, policy)
    return policy


def save_artifacts(context: Any, session_id: str, artifacts: list[dict[str, Any]]) -> int:
    if not artifacts:
        return 0
    scope_id, workspace_id, user_id = scope_for_context(context)
    policy = get_policy(scope_id)
    if not policy["enabled"]:
        return 0
    allowed = set(policy["allowed_kinds"])
    saved = 0
    now = metadata_store.utcnow()
    for artifact in artifacts:
        kind = str(artifact.get("kind") or "analysis_result")
        if kind not in allowed:
            continue
        artifact_id = str(artifact.get("id") or "").strip()
        if not artifact_id:
            continue
        existing = metadata_store.fetch_one(
            "SELECT id FROM assistant_project_memory WHERE scope_id=:scope AND artifact_id=:artifact",
            {"scope": scope_id, "artifact": artifact_id},
        )
        payload = _compact_payload(artifact)
        ui_state = getattr(context, "uiState", None) or {}
        if isinstance(ui_state, dict):
            dataset_name = ui_state.get("datasetName")
            if dataset_name and "dataset_name" not in payload:
                payload["dataset_name"] = str(dataset_name)[:240]
            temporal = ui_state.get("temporalCoverage")
            if isinstance(temporal, dict) and temporal.get("primary"):
                payload.setdefault("temporal_coverage", temporal.get("primary"))
        title = str(artifact.get("reference_name") or artifact.get("label") or kind)[:160]
        summary = str(artifact.get("summary") or title)[:1200]
        params = {
            "id": existing.get("id") if existing else str(uuid4()),
            "scope": scope_id,
            "workspace": workspace_id,
            "user": user_id,
            "session": session_id,
            "artifact": artifact_id,
            "dataset": artifact.get("dataset_id"),
            "kind": kind,
            "title": title,
            "summary": summary,
            "payload": metadata_store.json_dumps(payload),
            "updated": now,
        }
        if existing:
            metadata_store.execute(
                """UPDATE assistant_project_memory
                   SET session_id=:session,dataset_id=:dataset,kind=:kind,title=:title,summary=:summary,
                       payload_json=:payload,updated_at=:updated,last_used_at=:updated
                   WHERE id=:id AND scope_id=:scope""",
                params,
            )
        else:
            metadata_store.execute(
                """INSERT INTO assistant_project_memory(
                       id,scope_id,workspace_id,user_id,session_id,artifact_id,dataset_id,kind,title,summary,
                       payload_json,pinned,created_at,updated_at,last_used_at
                   ) VALUES(
                       :id,:scope,:workspace,:user,:session,:artifact,:dataset,:kind,:title,:summary,
                       :payload,0,:updated,:updated,:updated
                   )""",
                params,
            )
        saved += 1
    _enforce_retention(scope_id, policy)
    return saved


def list_entries(scope_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    _enforce_retention(scope_id, get_policy(scope_id))
    rows = metadata_store.fetch_all(
        """SELECT id,artifact_id,dataset_id,kind,title,summary,payload_json,pinned,created_at,updated_at,last_used_at
           FROM assistant_project_memory WHERE scope_id=:scope
           ORDER BY pinned DESC, last_used_at DESC, created_at DESC""",
        {"scope": scope_id},
    )
    return [_row_to_entry(row) for row in rows[: max(1, min(limit, 200))]]




def get_entry(scope_id: str, entry_id: str) -> dict[str, Any] | None:
    row = metadata_store.fetch_one(
        """SELECT id,artifact_id,dataset_id,kind,title,summary,payload_json,pinned,created_at,updated_at,last_used_at
           FROM assistant_project_memory WHERE scope_id=:scope AND id=:id""",
        {"scope": scope_id, "id": entry_id},
    )
    return _row_to_entry(row) if row else None


def duplicate_entry(scope_id: str, entry_id: str) -> dict[str, Any] | None:
    """Duplicate a compact project-memory recipe without touching datasets/models.

    The duplicate receives a fresh memory id + artifact id.  It is intentionally
    not pinned and keeps the source dataset binding so a later replay remains
    subject to normal dataset/schema validation.
    """
    row = metadata_store.fetch_one(
        """SELECT id,scope_id,workspace_id,user_id,session_id,artifact_id,dataset_id,kind,title,summary,
                  payload_json,pinned,created_at,updated_at,last_used_at
           FROM assistant_project_memory WHERE scope_id=:scope AND id=:id""",
        {"scope": scope_id, "id": entry_id},
    )
    if not row:
        return None
    new_id = str(uuid4())
    new_artifact_id = f"memory-copy:{uuid4()}"
    now = metadata_store.utcnow()
    payload = metadata_store.json_loads(row.get("payload_json"), {}) or {}
    if not isinstance(payload, dict):
        payload = {}
    payload = dict(payload)
    payload["copied_from_project_memory_id"] = row.get("id")
    payload["copied_from_artifact_id"] = row.get("artifact_id")
    title = f"Copie — {str(row.get('title') or row.get('kind') or 'Analyse')}"[:160]
    metadata_store.execute(
        """INSERT INTO assistant_project_memory(
               id,scope_id,workspace_id,user_id,session_id,artifact_id,dataset_id,kind,title,summary,
               payload_json,pinned,created_at,updated_at,last_used_at
           ) VALUES(
               :id,:scope,:workspace,:user,:session,:artifact,:dataset,:kind,:title,:summary,
               :payload,0,:now,:now,:now
           )""",
        {
            "id": new_id,
            "scope": scope_id,
            "workspace": row.get("workspace_id"),
            "user": row.get("user_id"),
            "session": f"memory-duplicate:{entry_id}",
            "artifact": new_artifact_id,
            "dataset": row.get("dataset_id"),
            "kind": row.get("kind"),
            "title": title,
            "summary": row.get("summary") or title,
            "payload": metadata_store.json_dumps(payload),
            "now": now,
        },
    )
    _enforce_retention(scope_id, get_policy(scope_id))
    return get_entry(scope_id, new_id)


def search_entries(scope_id: str, query: str, *, dataset_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    """Search governed project memory using deterministic local semantic ranking.

    No external model is called.  The ranker combines concept expansion, field
    overlap, fuzzy phrase similarity, artifact-kind hints, dataset affinity,
    pinning and temporal hints.  Returned entries expose the score/reasons so
    the UI and audit trail can explain why an artifact was recalled.
    """
    entries = list_entries(scope_id, limit=200)
    if not str(query or "").strip():
        return entries[: max(1, min(limit, 20))]

    ranked: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        score, reasons = _semantic_score(entry, query, dataset_id=dataset_id)
        if score < 0.12:
            continue
        enriched = dict(entry)
        enriched["search_score"] = round(min(score, 1.0), 4)
        enriched["match_reasons"] = reasons[:5]
        enriched["search_mode"] = "semantic_local"
        ranked.append((score, enriched))

    ranked.sort(
        key=lambda item: (item[0], item[1].get("pinned", False), item[1].get("last_used_at") or ""),
        reverse=True,
    )
    results = [entry for _score, entry in ranked[: max(1, min(limit, 20))]]
    if results:
        now = metadata_store.utcnow()
        for entry in results[:3]:
            metadata_store.execute(
                "UPDATE assistant_project_memory SET last_used_at=:now WHERE id=:id AND scope_id=:scope",
                {"now": now, "id": entry["id"], "scope": scope_id},
            )
    return results


def _semantic_score(entry: dict[str, Any], query: str, *, dataset_id: str | None = None) -> tuple[float, list[str]]:
    payload = entry.get("payload") or {}
    query_norm = _normalize(query)
    query_tokens = _semantic_tokens(query)
    text = _entry_search_text(entry)
    text_norm = _normalize(text)
    text_tokens = _semantic_tokens(text)
    reasons: list[str] = []
    score = 0.0

    common = query_tokens & text_tokens
    if common:
        coverage = len(common) / max(1, len(query_tokens))
        score += 0.58 * coverage
        reasons.append("concepts communs: " + ", ".join(sorted(common)[:4]))

    # Exact phrase/sub-phrase is a strong deterministic signal.
    if query_norm and query_norm in text_norm:
        score += 0.34
        reasons.append("expression exacte")
    else:
        ratio = SequenceMatcher(None, query_norm[:240], text_norm[:500]).ratio() if query_norm and text_norm else 0.0
        if ratio >= 0.45:
            score += min(0.18, ratio * 0.18)
            reasons.append("formulation proche")

    requested = _requested_kinds(query)
    if requested:
        if str(entry.get("kind") or "") in requested:
            score += 0.18
            reasons.append("type d'artefact demandé")
        else:
            score -= 0.08

    aliases = [str(x) for x in payload.get("aliases") or [] if x]
    if any(_normalize(alias) and _normalize(alias) in query_norm for alias in aliases):
        score += 0.28
        reasons.append("alias/identifiant reconnu")

    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    for key in ("target", "column", "metric", "algorithm"):
        value = params.get(key)
        if value and _normalize(str(value)) in query_norm:
            score += 0.16
            reasons.append(f"paramètre {key} reconnu")
            break

    if dataset_id and str(entry.get("dataset_id") or "") == str(dataset_id):
        score += 0.10
        reasons.append("dataset actif")
    if entry.get("pinned"):
        score += 0.06
        reasons.append("épinglé")

    temporal_score, temporal_reason = _temporal_match(query_norm, entry.get("created_at"))
    if temporal_score:
        score += temporal_score
        reasons.append(temporal_reason)

    return max(0.0, score), reasons


def _entry_search_text(entry: dict[str, Any]) -> str:
    payload = entry.get("payload") or {}
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    values: list[str] = [
        str(entry.get("title") or ""), str(entry.get("summary") or ""), str(entry.get("kind") or ""),
        str(payload.get("tool") or ""), str(payload.get("dataset_name") or ""),
        " ".join(str(x) for x in payload.get("columns") or []),
        " ".join(str(x) for x in payload.get("aliases") or []),
        " ".join(f"{k} {v}" for k, v in params.items() if v not in (None, "", [], {})),
        " ".join(str(k) for k in metrics.keys()),
    ]
    return " ".join(value for value in values if value)


def _semantic_tokens(value: str) -> set[str]:
    normalized = _normalize(value)
    expanded = set(_tokens(normalized))
    for canonical, phrases in _SEMANTIC_PHRASES.items():
        if canonical in expanded or any(_normalize(phrase) in normalized for phrase in phrases):
            expanded.add(canonical)
            for phrase in phrases:
                expanded.update(_tokens(phrase))
    # Light stemming keeps the ranker deterministic and language-agnostic enough
    # for common French/English analytics labels.
    stems = set()
    for token in expanded:
        stems.add(_stem_token(token))
    return {token for token in expanded | stems if token}


def _stem_token(token: str) -> str:
    token = _normalize(token)
    for suffix in ("ements", "ement", "ations", "ation", "iques", "ique", "ments", "ment", "ées", "ee", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[:-len(suffix)]
    return token


def _requested_kinds(query: str) -> set[str]:
    norm = _normalize(query)
    requested: set[str] = set()
    for canonical, kinds in _KIND_HINTS.items():
        phrases = _SEMANTIC_PHRASES.get(canonical, (canonical,))
        if canonical in norm or any(_normalize(phrase) in norm for phrase in phrases):
            requested.update(kinds)
    return requested


def _temporal_match(query_norm: str, created_at: Any) -> tuple[float, str]:
    created = _parse_dt(created_at)
    years = {int(value) for value in re.findall(r"\b(20\d{2})\b", query_norm)}
    if years:
        return (0.20, f"année {created.year}") if created.year in years else (-0.05, "année différente")
    current_year = datetime.now(timezone.utc).year
    if any(phrase in query_norm for phrase in ("l an dernier", "annee derniere", "année dernière")):
        return (0.20, "année précédente") if created.year == current_year - 1 else (-0.05, "hors année précédente")
    if any(phrase in query_norm for phrase in ("recent", "récent", "derniere", "dernière", "plus recent", "plus récent")):
        age_days = max(0, (datetime.now(timezone.utc) - created).days)
        return (max(0.0, 0.12 * math.exp(-age_days / 90.0)), "récence")
    return 0.0, ""


def should_recall(message: str, *, has_session_artifacts: bool) -> bool:
    lower = _normalize(message)
    if any(_normalize(hint) in lower for hint in _RECALL_HINTS):
        return True
    if not has_session_artifacts and re.search(r"\b(graphique|modele|modèle|rapport|analyse|resultat|résultat)\b", lower):
        return True
    return False


def pin_entry(scope_id: str, entry_id: str, pinned: bool) -> dict[str, Any] | None:
    row = metadata_store.fetch_one(
        "SELECT id FROM assistant_project_memory WHERE id=:id AND scope_id=:scope",
        {"id": entry_id, "scope": scope_id},
    )
    if not row:
        return None
    metadata_store.execute(
        "UPDATE assistant_project_memory SET pinned=:pinned,updated_at=:updated WHERE id=:id AND scope_id=:scope",
        {"pinned": 1 if pinned else 0, "updated": metadata_store.utcnow(), "id": entry_id, "scope": scope_id},
    )
    return next((e for e in list_entries(scope_id, limit=200) if e["id"] == entry_id), None)


def forget_entry(scope_id: str, entry_id: str) -> bool:
    row = metadata_store.fetch_one(
        "SELECT id FROM assistant_project_memory WHERE id=:id AND scope_id=:scope",
        {"id": entry_id, "scope": scope_id},
    )
    if not row:
        return False
    metadata_store.execute(
        "DELETE FROM assistant_project_memory WHERE id=:id AND scope_id=:scope",
        {"id": entry_id, "scope": scope_id},
    )
    return True


def clear_unpinned(scope_id: str) -> int:
    rows = metadata_store.fetch_all(
        "SELECT id FROM assistant_project_memory WHERE scope_id=:scope AND pinned=0",
        {"scope": scope_id},
    )
    for row in rows:
        metadata_store.execute(
            "DELETE FROM assistant_project_memory WHERE id=:id AND scope_id=:scope",
            {"id": row["id"], "scope": scope_id},
        )
    return len(rows)


def to_session_artifact(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry.get("payload") or {})
    payload.setdefault("id", entry.get("artifact_id") or entry.get("id"))
    payload.setdefault("kind", entry.get("kind"))
    payload.setdefault("label", entry.get("title"))
    payload.setdefault("summary", entry.get("summary"))
    payload["project_memory_id"] = entry.get("id")
    payload["memory_source"] = "project"
    aliases = list(payload.get("aliases") or [])
    if entry.get("id"):
        aliases.append(f"project-memory:{entry.get('id')}")
    if entry.get("artifact_id"):
        aliases.append(str(entry.get("artifact_id")))
    payload["aliases"] = list(dict.fromkeys(str(x) for x in aliases if x))[:16]
    return payload


def _row_to_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "artifact_id": row.get("artifact_id"),
        "dataset_id": row.get("dataset_id"),
        "kind": row.get("kind"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "payload": metadata_store.json_loads(row.get("payload_json"), {}) or {},
        "pinned": bool(row.get("pinned")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_used_at": row.get("last_used_at"),
    }


def _compact_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id", "kind", "kind_sequence", "reference_name", "label", "display_name", "tool",
        "dataset_id", "model_id", "chart_id", "report_id", "columns", "metrics", "summary",
        "created_at", "params", "aliases", "dataset_name", "temporal_coverage",
    }
    return {k: artifact.get(k) for k in allowed if artifact.get(k) not in (None, "", [], {})}


def _normalize_policy(policy: dict[str, Any]) -> dict[str, Any]:
    allowed_kinds = policy.get("allowed_kinds") if isinstance(policy.get("allowed_kinds"), list) else DEFAULT_POLICY["allowed_kinds"]
    return {
        "enabled": bool(policy.get("enabled", True)),
        "auto_recall": bool(policy.get("auto_recall", True)),
        "retention_days": max(1, min(int(policy.get("retention_days", 90)), 3650)),
        "max_entries": max(10, min(int(policy.get("max_entries", 200)), 2000)),
        "allowed_kinds": [str(x) for x in allowed_kinds if str(x) in DEFAULT_POLICY["allowed_kinds"]],
    }


def _enforce_retention(scope_id: str, policy: dict[str, Any]) -> None:
    rows = metadata_store.fetch_all(
        "SELECT id,pinned,created_at FROM assistant_project_memory WHERE scope_id=:scope ORDER BY pinned DESC,created_at DESC",
        {"scope": scope_id},
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(policy["retention_days"]))
    keep_unpinned = 0
    for row in rows:
        if bool(row.get("pinned")):
            continue
        created = _parse_dt(row.get("created_at"))
        keep_unpinned += 1
        if created < cutoff or keep_unpinned > int(policy["max_entries"]):
            metadata_store.execute(
                "DELETE FROM assistant_project_memory WHERE id=:id AND scope_id=:scope",
                {"id": row["id"], "scope": scope_id},
            )


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _tokens(value: str) -> set[str]:
    stop = {"le", "la", "les", "de", "du", "des", "un", "une", "ce", "cette", "mon", "ma", "mes", "et", "a", "au", "aux", "pour", "dans", "sur", "avec", "précédent", "precedent"}
    return {token for token in re.findall(r"[a-z0-9_\-]{2,}", _normalize(value)) if token not in stop}
