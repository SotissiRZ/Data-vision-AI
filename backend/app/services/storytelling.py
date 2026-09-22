from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from app.services.analysis_history import get_analysis
from app.services.decision import decision_support
from app.services.insight_engine import generate_insights
from app.services.profiling import profile_dataframe
from app.services.quality import quality_report
from app.services.saved_visualizations import list_visualizations
from app.services.storage import get_meta, load_dataframe

AUDIENCES = {"executive", "operations", "analyst", "general"}
TONES = {"concise", "balanced", "detailed"}


def _hash(payload: Any, length: int = 20) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _audience_label(audience: str) -> str:
    return {
        "executive": "Direction / décideurs",
        "operations": "Équipes opérationnelles",
        "analyst": "Analystes / data",
        "general": "Audience générale",
    }[audience]


def _evidence(
    evidence_id: str,
    *,
    kind: str,
    title: str,
    statement: str,
    source_ref: str,
    dataset_id: str,
    version: int,
    payload: dict[str, Any] | None = None,
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "kind": kind,
        "title": _clean(title, 180),
        "statement": _clean(statement, 1200),
        "source_ref": _clean(source_ref, 240),
        "dataset_id": dataset_id,
        "dataset_version": int(version),
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "payload": payload or {},
        "deterministic": True,
    }


def _claim(text: str, evidence_ids: list[str], *, role: str = "finding", confidence: float = 0.9) -> dict[str, Any]:
    clean_ids = [str(x) for x in evidence_ids if x]
    return {
        "id": f"claim:{_hash([text, clean_ids, role], 16)}",
        "text": _clean(text, 1200),
        "role": role,
        "evidence_ids": clean_ids,
        "evidence_count": len(clean_ids),
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "causal_claim": False,
    }


def _page(
    number: int,
    *,
    role: str,
    headline: str,
    summary: str,
    claims: list[dict[str, Any]],
    visual_refs: list[str] | None = None,
    takeaway: str | None = None,
) -> dict[str, Any]:
    claims = [c for c in claims if c.get("text")]
    evidenced = sum(1 for c in claims if c.get("evidence_ids"))
    coverage = round(evidenced / len(claims), 4) if claims else 1.0
    return {
        "page_number": number,
        "role": role,
        "headline": _clean(headline, 180),
        "summary": _clean(summary, 1400),
        "claims": claims,
        "visual_refs": [str(x) for x in (visual_refs or []) if x][:4],
        "takeaway": _clean(takeaway or "", 900),
        "proof_coverage": coverage,
    }


def build_story_blueprint(
    dataset_id: str,
    *,
    audience: str = "executive",
    objective: str | None = None,
    tone: str = "balanced",
    max_pages: int = 6,
    analysis_session_id: str | None = None,
    visualization_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, evidence-linked, multi-page analytical story.

    The function never asks a language model to calculate or invent claims. Narrative text is
    assembled from profiling, quality, decision support, Insight Engine and an optional locked
    AI Analyst session whose own findings already carry executable-tool provenance.
    """
    audience = audience if audience in AUDIENCES else "executive"
    tone = tone if tone in TONES else "balanced"
    max_pages = max(3, min(int(max_pages), 8))
    objective = _clean(objective or "Comprendre les faits saillants et soutenir une décision traçable.", 500)

    meta = get_meta(dataset_id)
    version = int(meta.get("version", 1))
    df = load_dataframe(dataset_id)
    profile = profile_dataframe(df)
    quality = quality_report(df)
    decision = decision_support(profile, quality)
    insights_payload = generate_insights(dataset_id, df, max_insights=30, persist=False)
    insights = list(insights_payload.get("insights") or [])
    insights.sort(key=lambda x: float(x.get("priority_score") or 0), reverse=True)

    analysis: dict[str, Any] | None = None
    if analysis_session_id:
        analysis = get_analysis(analysis_session_id)
        if str((analysis.get("provenance") or {}).get("dataset_id")) != dataset_id:
            raise ValueError("La session AI Analyst n'appartient pas à ce dataset")

    saved = [
        item for item in list_visualizations(dataset_id)
        if int(item.get("dataset_version", 0)) == version
    ]
    if visualization_ids:
        wanted = {str(x) for x in visualization_ids}
        saved = [item for item in saved if str(item.get("id")) in wanted]
    saved = saved[:10]

    evidence: list[dict[str, Any]] = []
    profile_id = "evidence:profile"
    evidence.append(_evidence(
        profile_id,
        kind="profile",
        title="Périmètre du dataset",
        statement=f"{int(profile.get('rows') or len(df))} observations, {int(profile.get('columns_count') or len(df.columns))} variables et {int(profile.get('duplicates') or 0)} doublon(s) détecté(s).",
        source_ref="profiling_engine",
        dataset_id=dataset_id,
        version=version,
        payload={
            "rows": int(profile.get("rows") or len(df)),
            "columns": int(profile.get("columns_count") or len(df.columns)),
            "duplicates": int(profile.get("duplicates") or 0),
        },
    ))
    quality_id = "evidence:quality"
    evidence.append(_evidence(
        quality_id,
        kind="quality",
        title="Qualité des données",
        statement=f"Score qualité {quality.get('score', 0)}/100 avec {int(quality.get('issues_count') or 0)} alerte(s).",
        source_ref="quality_rule_engine",
        dataset_id=dataset_id,
        version=version,
        payload={"score": quality.get("score"), "issues_count": int(quality.get("issues_count") or 0)},
    ))

    insight_evidence_ids: list[str] = []
    for insight in insights[:10]:
        fingerprint = str(insight.get("fingerprint") or insight.get("id") or _hash(insight))
        evidence_id = f"evidence:insight:{fingerprint[:16]}"
        insight_evidence_ids.append(evidence_id)
        evidence.append(_evidence(
            evidence_id,
            kind="insight",
            title=str(insight.get("title") or "Insight"),
            statement=str(insight.get("statement") or ""),
            source_ref=f"insight:{fingerprint}",
            dataset_id=dataset_id,
            version=version,
            payload={
                "category": insight.get("category"),
                "severity": insight.get("severity"),
                "priority_score": insight.get("priority_score"),
                "method": (insight.get("calculation") or {}).get("method"),
                "evidence": insight.get("evidence") or {},
            },
            confidence=float(insight.get("confidence") or 0.8),
        ))

    analysis_evidence_ids: list[str] = []
    if analysis:
        for idx, finding in enumerate((analysis.get("findings") or [])[:6], 1):
            evidence_id = f"evidence:analysis:{idx}"
            analysis_evidence_ids.append(evidence_id)
            ev = finding.get("evidence") or {}
            evidence.append(_evidence(
                evidence_id,
                kind="ai_analysis",
                title=str(finding.get("title") or f"Constat {idx}"),
                statement=str(finding.get("statement") or ""),
                source_ref=f"analysis:{analysis_session_id}:{ev.get('tool') or 'tool'}",
                dataset_id=dataset_id,
                version=version,
                payload={"tool": ev.get("tool"), "level": finding.get("level")},
                confidence=0.9,
            ))

    visual_refs: list[str] = []
    for item in saved:
        visual_id = str(item.get("id") or "")
        if not visual_id:
            continue
        visual_refs.append(visual_id)
        evidence.append(_evidence(
            f"evidence:visual:{visual_id}",
            kind="visualization",
            title=str(item.get("title") or "Visualisation"),
            statement=str(item.get("insight") or item.get("reason") or f"Visualisation {item.get('visualization', {}).get('type', 'chart')}."),
            source_ref=f"visualization:{visual_id}",
            dataset_id=dataset_id,
            version=version,
            payload={"type": (item.get("visualization") or {}).get("type")},
        ))

    top = insights[:6]
    top_claims = [
        _claim(
            str(item.get("statement") or ""),
            [insight_evidence_ids[idx]],
            role="key_finding",
            confidence=float(item.get("confidence") or 0.8),
        )
        for idx, item in enumerate(top)
        if idx < len(insight_evidence_ids)
    ]

    situation_summary = (
        f"Cette histoire analytique répond à l'objectif « {objective} ». "
        f"Elle s'appuie sur la version {version} verrouillée du dataset et sépare les faits calculés des recommandations."
    )
    if audience == "executive":
        situation_summary += " La structure privilégie les décisions, les risques et les preuves essentielles."
    elif audience == "operations":
        situation_summary += " La structure privilégie les anomalies observables et les actions opérationnelles."
    elif audience == "analyst":
        situation_summary += " La structure privilégie méthodes, métriques et limites d'interprétation."

    pages: list[dict[str, Any]] = []
    pages.append(_page(
        1,
        role="context",
        headline="Contexte et périmètre de l'analyse",
        summary=situation_summary,
        claims=[
            _claim(evidence[0]["statement"], [profile_id], role="scope", confidence=1.0),
            _claim(evidence[1]["statement"], [quality_id], role="data_readiness", confidence=1.0),
        ],
        visual_refs=visual_refs[:1],
        takeaway="Le périmètre et la qualité des données sont explicités avant toute interprétation.",
    ))

    if top_claims:
        pages.append(_page(
            len(pages) + 1,
            role="signals",
            headline="Les signaux qui méritent l'attention",
            summary="Les constats suivants sont classés par priorité calculée et reliés à leur preuve d'origine.",
            claims=top_claims[:3],
            visual_refs=visual_refs[:2],
            takeaway="Ces constats décrivent les signaux les plus saillants; ils ne constituent pas, à eux seuls, une preuve de causalité.",
        ))

    driver_claims = top_claims[3:]
    if analysis_evidence_ids and analysis:
        for idx, finding in enumerate((analysis.get("findings") or [])[:3]):
            if idx < len(analysis_evidence_ids):
                driver_claims.append(_claim(
                    str(finding.get("statement") or ""),
                    [analysis_evidence_ids[idx]],
                    role="analysis_finding",
                    confidence=0.9,
                ))
    if driver_claims:
        pages.append(_page(
            len(pages) + 1,
            role="drivers",
            headline="Facteurs, relations et explications observées",
            summary="Cette page rassemble les relations descriptives et constats analytiques qui aident à expliquer les signaux prioritaires.",
            claims=driver_claims[:4],
            visual_refs=visual_refs[1:4],
            takeaway="Les relations observées doivent être interprétées avec les hypothèses statistiques et le contexte métier.",
        ))

    quality_claims = [_claim(evidence[1]["statement"], [quality_id], role="risk", confidence=1.0)]
    for issue in (quality.get("issues") or [])[:3]:
        text = str(issue.get("description") or "").strip()
        if text:
            # Quality issue detail is traceable through the quality report summary evidence.
            quality_claims.append(_claim(text, [quality_id], role="risk", confidence=0.98))
    pages.append(_page(
        len(pages) + 1,
        role="risks",
        headline="Risques, qualité et limites de lecture",
        summary="Les décisions doivent intégrer la qualité du dataset, l'incertitude et l'absence de causalité implicite.",
        claims=quality_claims,
        takeaway="Une conclusion est publiable seulement si ses limites sont visibles et si la version des données reste verrouillée.",
    ))

    action_claims: list[dict[str, Any]] = []
    for action in (decision.get("actions") or [])[:5]:
        text = f"{action.get('action', '')} Preuve: {action.get('evidence', '')}".strip()
        refs = [quality_id if "qualit" in text.lower() or "probl" in text.lower() else profile_id]
        action_claims.append(_claim(text, refs, role="recommended_action", confidence=0.9))
    if not action_claims:
        action_claims.append(_claim(
            "Poursuivre l'exploration en conservant la version du dataset, les preuves et les limites avec chaque conclusion.",
            [profile_id, quality_id],
            role="recommended_action",
            confidence=0.9,
        ))
    pages.append(_page(
        len(pages) + 1,
        role="decision",
        headline="Décisions et prochaines actions",
        summary="Les actions proposées sont dérivées des contrôles et constats disponibles; elles restent soumises à validation humaine.",
        claims=action_claims,
        takeaway="DataVision informe la décision mais ne remplace pas la validation métier ou réglementaire.",
    ))

    pages.append(_page(
        len(pages) + 1,
        role="closing",
        headline="Conclusion, preuves et conditions de publication",
        summary="La narration conserve un lien explicite entre chaque claim et ses preuves, avec le dataset et sa version d'origine.",
        claims=[
            _claim("Toutes les affirmations automatiques de cette trame sont reliées à au moins une preuve calculée.", [profile_id, quality_id], role="governance", confidence=1.0),
            _claim("Les associations descriptives ne doivent pas être reformulées comme des effets causaux sans protocole causal adapté.", [profile_id], role="limitation", confidence=1.0),
        ],
        visual_refs=[],
        takeaway="Avant diffusion, le rapport doit passer la validation d'intégrité et, en contexte gouverné, le Data Reliability Gate.",
    ))

    # Keep the closing page even when a shorter story is requested.
    if len(pages) > max_pages:
        pages = pages[: max_pages - 1] + [pages[-1]]
    for idx, page in enumerate(pages, 1):
        page["page_number"] = idx

    evidence_ids = {e["id"] for e in evidence}
    missing_links: list[str] = []
    claim_count = 0
    linked_claims = 0
    for page in pages:
        for claim in page.get("claims", []):
            claim_count += 1
            refs = claim.get("evidence_ids") or []
            valid = [ref for ref in refs if ref in evidence_ids]
            claim["evidence_ids"] = valid
            claim["evidence_count"] = len(valid)
            if valid:
                linked_claims += 1
            else:
                missing_links.append(str(claim.get("id")))
        claims = page.get("claims") or []
        page["proof_coverage"] = round(sum(1 for c in claims if c.get("evidence_ids")) / len(claims), 4) if claims else 1.0

    proof_coverage = round(linked_claims / claim_count, 4) if claim_count else 1.0
    blueprint_seed = {
        "dataset_id": dataset_id,
        "dataset_version": version,
        "audience": audience,
        "objective": objective,
        "tone": tone,
        "pages": pages,
    }
    story_id = f"story:{_hash(blueprint_seed, 24)}"
    return {
        "story_id": story_id,
        "schema_version": 1,
        "engine": "datavision_storytelling_v272",
        "dataset": {"id": dataset_id, "name": meta.get("original_name"), "version": version},
        "audience": audience,
        "audience_label": _audience_label(audience),
        "objective": objective,
        "tone": tone,
        "page_count": len(pages),
        "pages": pages,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "claim_count": claim_count,
        "proof_coverage": proof_coverage,
        "missing_evidence_links": missing_links,
        "visualization_ids": visual_refs,
        "analysis_session_id": analysis_session_id,
        "governance": {
            "dataset_version_locked": True,
            "claims_require_evidence": True,
            "causal_claims_generated": False,
            "numeric_calculation_by_llm": False,
            "human_decision_required": True,
        },
    }
