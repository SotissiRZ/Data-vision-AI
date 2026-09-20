from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.quality import quality_report
from app.services.storage import get_meta, list_versions, load_dataframe


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root_id(dataset_id: str) -> str:
    meta = get_meta(dataset_id)
    return str(meta.get("root_id") or meta["id"])


def _base_dir(dataset_id: str) -> Path:
    path = get_settings().data_root / "insights" / _root_id(dataset_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


def _is_identifier(name: str, series: pd.Series, rows: int) -> bool:
    low = str(name).lower()
    unique = int(series.nunique(dropna=True))
    by_name = low in {"id", "index", "row", "record", "patient_id", "customer_id", "user_id"} or low.endswith("_id")
    id_token = any(token in low for token in ("uuid", "identifier", "identifiant", "code", "key", "numero", "number", "record_no", "record_number"))
    high_unique = rows > 20 and unique / max(rows, 1) > 0.98
    return by_name or (high_unique and id_token)


def _priority(severity: str, confidence: float, impact: float) -> float:
    base = {"critical": 100.0, "high": 82.0, "medium": 62.0, "low": 42.0, "info": 30.0}.get(severity, 30.0)
    value = base * 0.68 + max(0.0, min(1.0, confidence)) * 17.0 + max(0.0, min(1.0, impact)) * 15.0
    return round(max(0.0, min(100.0, value)), 2)


def _stable_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _make_insight(
    *,
    dataset_id: str,
    version: int,
    category: str,
    severity: str,
    title: str,
    statement: str,
    evidence: dict[str, Any],
    method: str,
    source_columns: list[str] | None = None,
    confidence: float = 0.8,
    impact: float = 0.5,
    explanation: str | None = None,
    action_label: str | None = None,
    action_view: str | None = None,
) -> dict[str, Any]:
    proof = {
        "dataset_id": dataset_id,
        "version": int(version),
        "category": category,
        "title": title,
        "evidence": evidence,
        "method": method,
        "source_columns": source_columns or [],
    }
    fingerprint = _stable_fingerprint(proof)
    return {
        "id": fingerprint[:20],
        "fingerprint": fingerprint,
        "category": category,
        "severity": severity,
        "priority_score": _priority(severity, confidence, impact),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "impact": round(max(0.0, min(1.0, impact)), 4),
        "title": title,
        "statement": statement,
        "explanation": explanation or "Insight calculé par un moteur déterministe. Il décrit une association ou un changement observé et ne prouve pas une causalité.",
        "evidence": evidence,
        "suggested_action": {"label": action_label, "view": action_view} if action_label and action_view else None,
        "action": action_label,
        "calculation": {
            "engine": "datavision_insight_engine_v1",
            "method": method,
            "source_columns": source_columns or [],
            "deterministic": True,
            "llm_used_for_numeric_calculation": False,
        },
        "dataset": {"id": dataset_id, "version": int(version)},
        "causal_claim": False,
    }


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    rows = len(df)
    out: list[str] = []
    for col in df.select_dtypes(include=np.number).columns:
        if not _is_identifier(str(col), df[col], rows) and df[col].notna().sum() >= 5 and df[col].nunique(dropna=True) > 1:
            out.append(str(col))
    return out


def _categorical_columns(df: pd.DataFrame) -> list[str]:
    rows = max(len(df), 1)
    out: list[str] = []
    for col in df.columns:
        series = df[col]
        if _is_identifier(str(col), series, rows):
            continue
        unique = int(series.nunique(dropna=True))
        if 2 <= unique <= min(30, max(6, int(rows * 0.25))):
            out.append(str(col))
    return out


def _date_candidates(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    candidates: list[tuple[str, pd.Series]] = []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            parsed = pd.to_datetime(series, errors="coerce")
        else:
            low = str(col).lower()
            likely = any(token in low for token in ("date", "time", "jour", "day", "month", "mois", "year", "annee", "année"))
            if not likely:
                continue
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        ratio = float(parsed.notna().mean()) if len(parsed) else 0.0
        if ratio >= 0.65 and parsed.nunique(dropna=True) >= 3:
            candidates.append((str(col), parsed))
    return candidates


def _quality_insights(dataset_id: str, version: int, df: pd.DataFrame) -> list[dict[str, Any]]:
    report = quality_report(df)
    rows = max(len(df), 1)
    insights: list[dict[str, Any]] = []
    score = int(report.get("score") or 0)
    if score < 80:
        severity = "critical" if score < 50 else "high" if score < 70 else "medium"
        insights.append(_make_insight(
            dataset_id=dataset_id, version=version, category="quality", severity=severity,
            title="Qualité des données à traiter",
            statement=f"Le score qualité est de {score}/100 avec {report.get('issues_count', 0)} problème(s) détecté(s).",
            evidence={"quality_score": score, "issues_count": int(report.get("issues_count") or 0)},
            method="quality_rule_engine", confidence=0.99, impact=min(1.0, (100-score)/60.0),
            action_label="Ouvrir Qualité", action_view="quality",
        ))
    for issue in list(report.get("issues") or [])[:12]:
        sev = str(issue.get("severity") or "medium")
        sev = "high" if sev == "high" else "medium" if sev == "medium" else "low"
        col = str(issue.get("column") or "")
        impact = 0.7 if sev == "high" else 0.5 if sev == "medium" else 0.3
        insights.append(_make_insight(
            dataset_id=dataset_id, version=version, category="quality", severity=sev,
            title=f"Qualité · {issue.get('code') or 'contrôle'}",
            statement=str(issue.get("description") or "Problème de qualité détecté."),
            evidence={k: issue.get(k) for k in ("code", "column", "description", "impact", "recommendation") if issue.get(k) is not None},
            method="quality_rule_engine", source_columns=[col] if col else [], confidence=0.98, impact=impact,
            explanation=str(issue.get("impact") or "Contrôle déterministe de qualité."),
            action_label="Préparer les données", action_view="prepare",
        ))
    return insights


def _correlation_insights(dataset_id: str, version: int, df: pd.DataFrame, numeric: list[str]) -> list[dict[str, Any]]:
    if len(numeric) < 2:
        return []
    cols = numeric[:14]
    frame = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = frame.corr(method="pearson", min_periods=5)
    pairs: list[tuple[float, str, str, float, int]] = []
    for i, a in enumerate(cols):
        for b in cols[i+1:]:
            value = _safe_float(corr.loc[a, b])
            n = int(frame[[a, b]].dropna().shape[0])
            if value is not None and n >= 5 and abs(value) >= 0.55:
                pairs.append((abs(value), a, b, value, n))
    pairs.sort(reverse=True)
    out = []
    for abs_value, a, b, value, n in pairs[:5]:
        severity = "high" if abs_value >= 0.85 else "medium" if abs_value >= 0.7 else "info"
        out.append(_make_insight(
            dataset_id=dataset_id, version=version, category="correlation", severity=severity,
            title="Association linéaire notable",
            statement=f"{a} et {b} présentent une corrélation de Pearson r={value:.3f} sur {n} observations complètes.",
            evidence={"x": a, "y": b, "coefficient": round(value, 6), "n_complete": n, "absolute_coefficient": round(abs_value, 6)},
            method="pearson_correlation", source_columns=[a, b], confidence=min(0.99, 0.55 + n / max(len(df), 1) * 0.4), impact=min(1.0, abs_value),
            explanation="Association descriptive entre deux variables numériques. Une corrélation élevée ne démontre pas une relation causale.",
            action_label="Examiner les corrélations", action_view="tests",
        ))
    return out


def _anomaly_insights(dataset_id: str, version: int, df: pd.DataFrame, numeric: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows = max(len(df), 1)
    for col in numeric[:12]:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) < 8:
            continue
        median = float(s.median())
        mad = float(np.median(np.abs(s.to_numpy(dtype=float) - median)))
        if mad <= 1e-12:
            continue
        z = 0.67448975 * (s - median).abs() / mad
        count = int((z > 3.5).sum())
        if not count:
            continue
        rate = count / max(len(s), 1)
        severity = "high" if rate >= 0.1 else "medium" if rate >= 0.03 else "low"
        out.append(_make_insight(
            dataset_id=dataset_id, version=version, category="anomaly", severity=severity,
            title=f"Valeurs atypiques · {col}",
            statement=f"{count} observation(s) de {col} dépassent le seuil de z-score robuste 3,5 ({rate*100:.1f}% des valeurs observées).",
            evidence={"column": col, "anomalies_count": count, "observed_count": int(len(s)), "anomaly_rate_pct": round(rate*100, 4), "threshold": 3.5, "median": round(median, 6), "mad": round(mad, 6)},
            method="robust_z_mad", source_columns=[col], confidence=0.95, impact=min(1.0, rate*5.0),
            action_label="Ouvrir Anomalies", action_view="anomaly",
        ))
    return out


def _trend_insights(dataset_id: str, version: int, df: pd.DataFrame, numeric: list[str]) -> list[dict[str, Any]]:
    dates = _date_candidates(df)
    if not dates or not numeric:
        return []
    date_col, parsed = dates[0]
    out: list[dict[str, Any]] = []
    for col in numeric[:8]:
        work = pd.DataFrame({"date": parsed, "value": pd.to_numeric(df[col], errors="coerce")}).dropna()
        if len(work) < 8:
            continue
        work = work.sort_values("date")
        grouped = work.set_index("date")["value"].resample("MS").mean().dropna()
        if len(grouped) < 4:
            grouped = work.set_index("date")["value"].resample("W").mean().dropna()
        if len(grouped) < 4:
            continue
        y = grouped.to_numpy(dtype=float)
        x = np.arange(len(y), dtype=float)
        slope = float(np.polyfit(x, y, 1)[0])
        mean_abs = max(abs(float(np.mean(y))), 1e-9)
        normalized = slope / mean_abs
        first = float(np.mean(y[: max(1, len(y)//3)]))
        last = float(np.mean(y[-max(1, len(y)//3):]))
        delta_pct = None if abs(first) <= 1e-12 else (last-first)/abs(first)*100.0
        if abs(normalized) < 0.015 and (delta_pct is None or abs(delta_pct) < 8):
            continue
        direction = "hausse" if slope > 0 else "baisse"
        magnitude = min(1.0, max(abs(normalized)*8.0, abs(delta_pct or 0)/60.0))
        severity = "high" if magnitude >= 0.8 else "medium" if magnitude >= 0.45 else "info"
        out.append(_make_insight(
            dataset_id=dataset_id, version=version, category="trend", severity=severity,
            title=f"Tendance {direction} · {col}",
            statement=f"{col} montre une tendance à la {direction} sur {len(grouped)} périodes" + (f" (variation agrégée ≈ {delta_pct:.1f}%)." if delta_pct is not None else "."),
            evidence={"metric": col, "date_column": date_col, "periods": int(len(grouped)), "slope_per_period": round(slope, 8), "normalized_slope": round(normalized, 8), "delta_pct": None if delta_pct is None else round(delta_pct, 4), "first_period": grouped.index[0].isoformat(), "last_period": grouped.index[-1].isoformat()},
            method="time_aggregation_linear_trend", source_columns=[date_col, col], confidence=min(0.96, 0.55 + len(grouped)*0.035), impact=magnitude,
            explanation="Tendance descriptive calculée sur des agrégats temporels. Elle n'implique pas que le temps soit la cause de l'évolution.",
            action_label="Ouvrir Forecasting", action_view="forecast",
        ))
    return out


def _segment_insights(dataset_id: str, version: int, df: pd.DataFrame, numeric: list[str], categorical: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    rows = max(len(df), 1)
    for dim in categorical[:8]:
        counts = df[dim].value_counts(dropna=False)
        if counts.empty:
            continue
        share = float(counts.iloc[0] / rows)
        if share >= 0.55 and len(counts) >= 2:
            label = str(counts.index[0])
            out.append(_make_insight(
                dataset_id=dataset_id, version=version, category="segment", severity="medium" if share >= 0.75 else "info",
                title=f"Segment dominant · {dim}",
                statement=f"Le segment {label!r} représente {share*100:.1f}% des lignes pour {dim}.",
                evidence={"dimension": dim, "segment": label, "count": int(counts.iloc[0]), "share_pct": round(share*100, 4), "segments_count": int(len(counts))},
                method="segment_share", source_columns=[dim], confidence=0.99, impact=min(1.0, share),
                action_label="Explorer les données", action_view="data",
            ))
        for metric in numeric[:5]:
            work = pd.DataFrame({"dim": df[dim], "metric": pd.to_numeric(df[metric], errors="coerce")}).dropna()
            if len(work) < 12:
                continue
            grouped = work.groupby("dim")["metric"].agg(["mean", "count"]).query("count >= 3")
            if len(grouped) < 2:
                continue
            overall = float(work["metric"].mean())
            std = float(work["metric"].std(ddof=1))
            if not math.isfinite(std) or std <= 1e-12:
                continue
            grouped["effect"] = (grouped["mean"] - overall) / std
            idx = grouped["effect"].abs().idxmax()
            effect = float(grouped.loc[idx, "effect"])
            if abs(effect) < 0.65:
                continue
            segment_mean = float(grouped.loc[idx, "mean"])
            count = int(grouped.loc[idx, "count"])
            severity = "high" if abs(effect) >= 1.5 else "medium" if abs(effect) >= 1.0 else "info"
            out.append(_make_insight(
                dataset_id=dataset_id, version=version, category="segment", severity=severity,
                title=f"Segment distinctif · {dim}",
                statement=f"Le segment {str(idx)!r} présente une moyenne de {metric} de {segment_mean:.3g}, soit un écart standardisé de {effect:.2f} par rapport à l'ensemble.",
                evidence={"dimension": dim, "segment": str(idx), "metric": metric, "segment_mean": round(segment_mean, 8), "overall_mean": round(overall, 8), "standardized_effect": round(effect, 6), "segment_n": count},
                method="segment_standardized_mean_difference", source_columns=[dim, metric], confidence=min(0.95, 0.6 + count/max(rows,1)*0.35), impact=min(1.0, abs(effect)/2.0),
                explanation="Différence descriptive entre un segment et l'ensemble. Elle sert à prioriser l'exploration et ne constitue pas un test causal.",
                action_label="Analyser les groupes", action_view="tests",
            ))
            break
    return out


def _version_change_insights(dataset_id: str, version: int, df: pd.DataFrame) -> list[dict[str, Any]]:
    try:
        versions = list_versions(dataset_id)
    except Exception:
        return []
    current_pos = next((i for i, row in enumerate(versions) if str(row.get("id")) == str(dataset_id)), -1)
    if current_pos <= 0:
        return []
    previous_meta = versions[current_pos - 1]
    previous_id = str(previous_meta.get("id"))
    try:
        prev = load_dataframe(previous_id)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    prev_rows = len(prev)
    curr_rows = len(df)
    if prev_rows:
        delta = (curr_rows - prev_rows) / abs(prev_rows) * 100.0
        if abs(delta) >= 10:
            out.append(_make_insight(
                dataset_id=dataset_id, version=version, category="change", severity="high" if abs(delta) >= 40 else "medium",
                title="Changement de volume entre versions",
                statement=f"Le nombre de lignes est passé de {prev_rows} à {curr_rows} ({delta:+.1f}%) depuis la version précédente.",
                evidence={"previous_dataset_id": previous_id, "previous_version": int(previous_meta.get("version") or max(1, version-1)), "previous_rows": prev_rows, "current_rows": curr_rows, "delta_pct": round(delta, 4)},
                method="dataset_version_row_count_change", confidence=1.0, impact=min(1.0, abs(delta)/60.0),
                action_label="Voir l'historique", action_view="prepare",
            ))
    common_numeric = [c for c in df.select_dtypes(include=np.number).columns if c in prev.columns][:12]
    for col in common_numeric:
        a = pd.to_numeric(prev[col], errors="coerce").dropna()
        b = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(a) < 5 or len(b) < 5:
            continue
        ma, mb = float(a.mean()), float(b.mean())
        pooled = float(pd.concat([a, b], ignore_index=True).std(ddof=1))
        if not math.isfinite(pooled) or pooled <= 1e-12:
            continue
        effect = (mb-ma)/pooled
        if abs(effect) < 0.6:
            continue
        out.append(_make_insight(
            dataset_id=dataset_id, version=version, category="change", severity="high" if abs(effect) >= 1.2 else "medium",
            title=f"Déplacement de distribution · {col}",
            statement=f"La moyenne de {col} est passée de {ma:.3g} à {mb:.3g} entre les deux versions (écart standardisé {effect:.2f}).",
            evidence={"column": str(col), "previous_mean": round(ma, 8), "current_mean": round(mb, 8), "standardized_mean_change": round(effect, 6), "previous_n": int(len(a)), "current_n": int(len(b)), "previous_version": int(previous_meta.get("version") or max(1, version-1))},
            method="version_standardized_mean_change", source_columns=[str(col)], confidence=0.92, impact=min(1.0, abs(effect)/1.5),
            explanation="Comparaison descriptive entre deux versions immuables du dataset. Le changement peut provenir des données source ou d'une transformation.",
            action_label="Inspecter les versions", action_view="prepare",
        ))
    return out


def _dedupe_and_rank(insights: list[dict[str, Any]], max_insights: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in insights:
        fp = str(item.get("fingerprint") or "")
        if not fp or fp in seen:
            continue
        seen.add(fp)
        rows.append(item)
    rows.sort(key=lambda x: (-float(x.get("priority_score") or 0), str(x.get("category") or ""), str(x.get("title") or "")))
    for rank, item in enumerate(rows[:max_insights], start=1):
        item["rank"] = rank
    return rows[:max_insights]


def _persist_snapshot(dataset_id: str, payload: dict[str, Any]) -> None:
    base = _base_dir(dataset_id)
    version = int(payload.get("dataset", {}).get("version") or 1)
    path = base / f"v{version}-latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    history = base / "history.jsonl"
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"generated_at": payload.get("generated_at"), "dataset": payload.get("dataset"), "summary": payload.get("summary"), "insight_ids": [x.get("id") for x in payload.get("insights", [])]}, ensure_ascii=False, default=str) + "\n")


def insight_history(dataset_id: str, limit: int = 50) -> dict[str, Any]:
    path = _base_dir(dataset_id) / "history.jsonl"
    if not path.exists():
        return {"history": [], "count": 0}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    rows.reverse()
    rows = rows[: max(1, min(int(limit), 200))]
    return {"history": rows, "count": len(rows)}


def generate_insights(dataset_id: str, df: pd.DataFrame, *, max_insights: int = 20, persist: bool = True) -> dict[str, Any]:
    if max_insights < 1 or max_insights > 100:
        raise ValueError("max_insights doit être compris entre 1 et 100")
    meta = get_meta(dataset_id)
    version = int(meta.get("version") or 1)
    numeric = _numeric_columns(df)
    categorical = _categorical_columns(df)
    collected: list[dict[str, Any]] = []
    collected.extend(_quality_insights(dataset_id, version, df))
    collected.extend(_version_change_insights(dataset_id, version, df))
    collected.extend(_anomaly_insights(dataset_id, version, df, numeric))
    collected.extend(_trend_insights(dataset_id, version, df, numeric))
    collected.extend(_segment_insights(dataset_id, version, df, numeric, categorical))
    collected.extend(_correlation_insights(dataset_id, version, df, numeric))
    ranked = _dedupe_and_rank(collected, max_insights)
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for item in ranked:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
    result = {
        "dataset": {"id": dataset_id, "root_id": meta.get("root_id") or dataset_id, "version": version, "name": meta.get("original_name") or meta.get("source_name")},
        "generated_at": _now(),
        "engine_version": "insight_engine_v1",
        "summary": {"count": len(ranked), "by_category": by_category, "by_severity": by_severity, "numeric_columns_analyzed": len(numeric), "categorical_columns_analyzed": len(categorical)},
        "insights": ranked,
        "provenance": {
            "engines": ["quality_rule_engine", "robust_z_mad", "time_aggregation_linear_trend", "segment_standardized_mean_difference", "pearson_correlation", "dataset_version_change"],
            "dataset_id": dataset_id,
            "dataset_version": version,
            "rows": int(len(df)),
            "columns": int(len(df.columns)),
            "deterministic": True,
            "llm_used_for_numeric_calculation": False,
        },
        "limitations": [
            "Les insights sont descriptifs et ne constituent pas des preuves de causalité.",
            "Les tendances dépendent de la dimension temporelle détectée et de la couverture historique.",
            "Les segments sont prioritaires pour l'exploration, pas des conclusions métier définitives.",
        ],
    }
    if persist:
        _persist_snapshot(dataset_id, result)
    return result
