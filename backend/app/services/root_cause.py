from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


SUPPORTED_METRICS = {"mean", "sum", "count"}


def _json_value(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _safe_pct(delta: float, baseline: float) -> float | None:
    if not math.isfinite(delta) or not math.isfinite(baseline):
        return None
    if abs(baseline) <= 1e-12:
        return None
    return delta / abs(baseline) * 100.0


def _metric_value(frame: pd.DataFrame, target: str, metric: str) -> float:
    if metric == "count":
        return float(frame[target].notna().sum())

    values = pd.to_numeric(frame[target], errors="coerce").dropna()
    if values.empty:
        return float("nan")
    if metric == "sum":
        return float(values.sum())
    return float(values.mean())


def _resolve_comparison_values(
    series: pd.Series,
    baseline_value: Any | None,
    current_value: Any | None,
) -> tuple[Any, Any]:
    available = [value for value in series.dropna().drop_duplicates().tolist()]
    if baseline_value is not None and current_value is not None:
        return baseline_value, current_value

    if len(available) < 2:
        raise ValueError(
            "La variable de comparaison doit contenir au moins deux valeurs."
        )

    # Prefer chronological order for datetime-like variables.
    parsed = pd.to_datetime(pd.Series(available), errors="coerce", format="mixed")
    if parsed.notna().all():
        ordered = [
            value
            for _date, value in sorted(
                zip(parsed.tolist(), available),
                key=lambda item: item[0],
            )
        ]
    else:
        try:
            ordered = sorted(available)
        except Exception:
            ordered = available

    return (
        baseline_value if baseline_value is not None else ordered[-2],
        current_value if current_value is not None else ordered[-1],
    )


def _segment_metric(
    frame: pd.DataFrame,
    dimension: str,
    target: str,
    metric: str,
) -> pd.DataFrame:
    work = frame[[dimension, target]].copy()
    work[dimension] = work[dimension].where(
        work[dimension].notna(),
        "__MISSING__",
    )

    grouped = []
    for segment, part in work.groupby(dimension, dropna=False):
        numeric = pd.to_numeric(part[target], errors="coerce")
        count = int(numeric.notna().sum())
        total = float(numeric.sum()) if count else 0.0
        mean = float(numeric.mean()) if count else float("nan")
        grouped.append(
            {
                "segment": _json_value(segment),
                "count": count,
                "sum": total,
                "mean": mean,
            }
        )
    return pd.DataFrame(grouped)


def _decompose_dimension(
    baseline: pd.DataFrame,
    current: pd.DataFrame,
    *,
    dimension: str,
    target: str,
    metric: str,
    overall_delta: float,
    min_segment_size: int,
    top_n: int,
) -> dict[str, Any]:
    left = _segment_metric(
        baseline,
        dimension,
        target,
        metric,
    ).rename(
        columns={
            "count": "baseline_count",
            "sum": "baseline_sum",
            "mean": "baseline_mean",
        }
    )
    right = _segment_metric(
        current,
        dimension,
        target,
        metric,
    ).rename(
        columns={
            "count": "current_count",
            "sum": "current_sum",
            "mean": "current_mean",
        }
    )
    merged = left.merge(
        right,
        how="outer",
        on="segment",
    ).fillna(
        {
            "baseline_count": 0,
            "baseline_sum": 0.0,
            "current_count": 0,
            "current_sum": 0.0,
        }
    )

    baseline_total_count = max(
        int(pd.to_numeric(baseline[target], errors="coerce").notna().sum()),
        1,
    )
    current_total_count = max(
        int(pd.to_numeric(current[target], errors="coerce").notna().sum()),
        1,
    )

    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        bc = int(row["baseline_count"])
        cc = int(row["current_count"])
        if max(bc, cc) < min_segment_size:
            continue

        bsum = float(row["baseline_sum"] or 0.0)
        csum = float(row["current_sum"] or 0.0)
        bmean = (
            float(row["baseline_mean"])
            if pd.notna(row.get("baseline_mean"))
            else 0.0
        )
        cmean = (
            float(row["current_mean"])
            if pd.notna(row.get("current_mean"))
            else 0.0
        )

        if metric == "sum":
            contribution = csum - bsum
            mix_effect = None
            rate_effect = None
        elif metric == "count":
            contribution = float(cc - bc)
            mix_effect = None
            rate_effect = None
        else:
            w0 = bc / baseline_total_count
            w1 = cc / current_total_count
            # Symmetric Oaxaca-style decomposition.
            mix_effect = 0.5 * (w1 - w0) * (cmean + bmean)
            rate_effect = 0.5 * (cmean - bmean) * (w1 + w0)
            contribution = mix_effect + rate_effect

        rows.append(
            {
                "segment": _json_value(row["segment"]),
                "baseline_count": bc,
                "current_count": cc,
                "baseline_mean": round(bmean, 8),
                "current_mean": round(cmean, 8),
                "baseline_sum": round(bsum, 8),
                "current_sum": round(csum, 8),
                "contribution": round(float(contribution), 8),
                "mix_effect": (
                    None
                    if mix_effect is None
                    else round(float(mix_effect), 8)
                ),
                "rate_effect": (
                    None
                    if rate_effect is None
                    else round(float(rate_effect), 8)
                ),
            }
        )

    rows.sort(
        key=lambda item: abs(float(item["contribution"])),
        reverse=True,
    )
    absolute_total = sum(
        abs(float(item["contribution"]))
        for item in rows
    )
    concentration = (
        abs(float(rows[0]["contribution"])) / absolute_total
        if rows and absolute_total > 1e-12
        else 0.0
    )
    net = sum(float(item["contribution"]) for item in rows)
    reconciliation_error = (
        net - overall_delta
        if rows
        else -overall_delta
    )

    return {
        "dimension": dimension,
        "segments_analyzed": len(rows),
        "top_segments": rows[:top_n],
        "absolute_contribution": round(absolute_total, 8),
        "top_contribution_share": round(concentration, 8),
        "net_contribution": round(net, 8),
        "reconciliation_error": round(float(reconciliation_error), 8),
    }


def _numeric_shift(
    baseline: pd.Series,
    current: pd.Series,
) -> dict[str, Any] | None:
    left = pd.to_numeric(baseline, errors="coerce").dropna()
    right = pd.to_numeric(current, errors="coerce").dropna()
    if len(left) < 3 or len(right) < 3:
        return None

    bmean = float(left.mean())
    cmean = float(right.mean())
    pooled = math.sqrt(
        max(
            (
                float(left.var(ddof=1))
                + float(right.var(ddof=1))
            )
            / 2.0,
            0.0,
        )
    )
    standardized = (
        (cmean - bmean) / pooled
        if pooled > 1e-12
        else 0.0
    )
    return {
        "type": "numeric",
        "baseline_mean": round(bmean, 8),
        "current_mean": round(cmean, 8),
        "delta": round(cmean - bmean, 8),
        "standardized_shift": round(
            float(standardized),
            8,
        ),
        "score": round(abs(float(standardized)), 8),
    }


def _categorical_shift(
    baseline: pd.Series,
    current: pd.Series,
) -> dict[str, Any] | None:
    left = (
        baseline.fillna("__MISSING__")
        .astype(str)
        .value_counts(normalize=True)
    )
    right = (
        current.fillna("__MISSING__")
        .astype(str)
        .value_counts(normalize=True)
    )
    categories = sorted(set(left.index) | set(right.index))
    if not categories:
        return None

    tvd = 0.5 * sum(
        abs(float(right.get(cat, 0.0)) - float(left.get(cat, 0.0)))
        for cat in categories
    )
    changes = sorted(
        [
            {
                "value": cat,
                "baseline_share": round(float(left.get(cat, 0.0)), 8),
                "current_share": round(float(right.get(cat, 0.0)), 8),
                "delta_share": round(
                    float(right.get(cat, 0.0) - left.get(cat, 0.0)),
                    8,
                ),
            }
            for cat in categories
        ],
        key=lambda item: abs(item["delta_share"]),
        reverse=True,
    )[:8]
    return {
        "type": "categorical",
        "tvd": round(float(tvd), 8),
        "top_share_changes": changes,
        "score": round(float(tvd), 8),
    }



def _prepare_comparison(
    df: pd.DataFrame,
    comparison_column: str,
    time_grain: str,
) -> tuple[pd.DataFrame, str, str]:
    work = df.copy()
    if time_grain not in {
        "auto", "raw", "day", "week", "month", "quarter", "year"
    }:
        raise ValueError(
            "time_grain doit être auto, raw, day, week, month, quarter ou year."
        )

    if time_grain == "raw":
        return work, comparison_column, "raw"

    series = work[comparison_column]
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = pd.to_datetime(series, errors="coerce")
    else:
        parsed = pd.to_datetime(
            series,
            errors="coerce",
            format="mixed",
        )

    if parsed.notna().mean() < 0.8:
        return work, comparison_column, "raw"

    grain = time_grain
    if grain == "auto":
        clean = parsed.dropna()
        if clean.empty:
            return work, comparison_column, "raw"
        span_days = max(
            float(
                (clean.max() - clean.min()).total_seconds()
                / 86400.0
            ),
            0.0,
        )
        if span_days <= 45:
            grain = "day"
        elif span_days <= 730:
            grain = "month"
        elif span_days <= 3650:
            grain = "quarter"
        else:
            grain = "year"

    aliases = {
        "day": "D",
        "week": "W",
        "month": "M",
        "quarter": "Q",
        "year": "Y",
    }
    internal = "__datavision_comparison_period__"
    work[internal] = parsed.dt.to_period(aliases[grain]).astype("string")
    work.loc[parsed.isna(), internal] = pd.NA
    return work, internal, grain

def root_cause_analysis(
    df: pd.DataFrame,
    *,
    target: str,
    comparison_column: str,
    baseline_value: Any | None = None,
    current_value: Any | None = None,
    metric: str = "mean",
    dimensions: list[str] | None = None,
    time_grain: str = "auto",
    min_segment_size: int = 5,
    top_n: int = 8,
) -> dict[str, Any]:
    if target not in df.columns:
        raise ValueError(f"Variable cible inconnue: {target}")
    if comparison_column not in df.columns:
        raise ValueError(
            f"Variable de comparaison inconnue: {comparison_column}"
        )
    if metric not in SUPPORTED_METRICS:
        raise ValueError(
            f"Métrique invalide. Valeurs: {sorted(SUPPORTED_METRICS)}"
        )

    work, effective_comparison, resolved_grain = _prepare_comparison(
        df,
        comparison_column,
        time_grain,
    )

    baseline_value, current_value = _resolve_comparison_values(
        work[effective_comparison],
        baseline_value,
        current_value,
    )

    baseline = work[work[effective_comparison] == baseline_value].copy()
    current = work[work[effective_comparison] == current_value].copy()
    if baseline.empty or current.empty:
        raise ValueError(
            "Les groupes baseline/current doivent tous deux contenir des lignes."
        )

    baseline_metric = _metric_value(
        baseline,
        target,
        metric,
    )
    current_metric = _metric_value(
        current,
        target,
        metric,
    )
    if not math.isfinite(baseline_metric) or not math.isfinite(current_metric):
        raise ValueError(
            "Impossible de calculer la métrique cible sur les groupes comparés."
        )

    delta = current_metric - baseline_metric

    if dimensions is None:
        candidate_dimensions = [
            column
            for column in df.columns
            if column not in {
                target,
                comparison_column,
                effective_comparison,
            }
            and (
                not pd.api.types.is_numeric_dtype(df[column])
                or df[column].nunique(dropna=True) <= 30
            )
            and 2 <= df[column].nunique(dropna=True) <= 50
        ][:12]
    else:
        candidate_dimensions = [
            column
            for column in dimensions
            if column in df.columns
            and column not in {
                target,
                comparison_column,
                effective_comparison,
            }
        ][:20]

    decompositions = [
        _decompose_dimension(
            baseline,
            current,
            dimension=dimension,
            target=target,
            metric=metric,
            overall_delta=delta,
            min_segment_size=max(1, int(min_segment_size)),
            top_n=max(1, min(int(top_n), 20)),
        )
        for dimension in candidate_dimensions
    ]

    decompositions.sort(
        key=lambda item: (
            item["top_contribution_share"],
            item["absolute_contribution"],
        ),
        reverse=True,
    )

    shift_rows: list[dict[str, Any]] = []
    for feature in df.columns:
        if feature in {target, comparison_column}:
            continue

        if pd.api.types.is_numeric_dtype(df[feature]):
            info = _numeric_shift(
                baseline[feature],
                current[feature],
            )
        else:
            info = _categorical_shift(
                baseline[feature],
                current[feature],
            )

        if info is not None:
            shift_rows.append(
                {
                    "feature": feature,
                    **info,
                }
            )

    shift_rows.sort(
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )

    strongest_dimension = decompositions[0] if decompositions else None
    strongest_shift = shift_rows[0] if shift_rows else None

    evidence = []
    review_priorities: list[dict[str, Any]] = []

    if strongest_dimension and strongest_dimension.get("top_segments"):
        for rank, segment in enumerate(
            strongest_dimension["top_segments"][:3],
            start=1,
        ):
            evidence.append(
                {
                    "type": "segment_contribution",
                    "dimension": strongest_dimension["dimension"],
                    "segment": segment["segment"],
                    "contribution": segment["contribution"],
                }
            )
            review_priorities.append(
                {
                    "rank": rank,
                    "kind": "segment_review",
                    "title": (
                        f"Examiner {strongest_dimension['dimension']} = "
                        f"{segment['segment']}"
                    ),
                    "evidence": {
                        "contribution": segment["contribution"],
                        "baseline_count": segment["baseline_count"],
                        "current_count": segment["current_count"],
                        "baseline_mean": segment["baseline_mean"],
                        "current_mean": segment["current_mean"],
                    },
                    "reason": (
                        "Segment parmi les plus fortes contributions descriptives "
                        "à l'écart observé."
                    ),
                }
            )

    if strongest_shift:
        evidence.append(
            {
                "type": "distribution_shift",
                "feature": strongest_shift["feature"],
                "score": strongest_shift["score"],
            }
        )
        review_priorities.append(
            {
                "rank": len(review_priorities) + 1,
                "kind": "distribution_review",
                "title": (
                    f"Vérifier le changement de distribution de "
                    f"{strongest_shift['feature']}"
                ),
                "evidence": {
                    "type": strongest_shift["type"],
                    "score": strongest_shift["score"],
                },
                "reason": (
                    "La distribution de cette variable diffère fortement entre "
                    "la baseline et la période/groupe actuel."
                ),
            }
        )

    sample_floor = min(len(baseline), len(current))
    confidence = (
        "high"
        if sample_floor >= 100
        else "medium"
        if sample_floor >= 30
        else "low"
    )

    return {
        "status": "ok",
        "target": target,
        "metric": metric,
        "comparison_column": comparison_column,
        "comparison_time_grain": resolved_grain,
        "baseline": {
            "value": _json_value(baseline_value),
            "rows": len(baseline),
            "metric": round(float(baseline_metric), 8),
        },
        "current": {
            "value": _json_value(current_value),
            "rows": len(current),
            "metric": round(float(current_metric), 8),
        },
        "delta": round(float(delta), 8),
        "delta_pct": (
            None
            if _safe_pct(delta, baseline_metric) is None
            else round(
                float(_safe_pct(delta, baseline_metric)),
                8,
            )
        ),
        "dimension_decompositions": decompositions,
        "feature_shifts": shift_rows[:20],
        "evidence": evidence,
        "review_priorities": review_priorities,
        "evidence_strength": {
            "level": confidence,
            "baseline_rows": len(baseline),
            "current_rows": len(current),
            "note": (
                "Niveau indicatif basé sur la taille minimale des groupes; "
                "ce n'est pas un score de causalité."
            ),
        },
        "interpretation_policy": (
            "descriptive_root_cause_candidates_not_causal_proof"
        ),
        "caveat": (
            "Cette analyse identifie des segments et changements de distribution "
            "associés à l'écart observé. Elle ne démontre pas qu'ils causent cet écart."
        ),
    }
