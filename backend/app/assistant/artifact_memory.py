from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import AgentTurnRun

ARTIFACT_FACT_KEY = "recent_artifacts"
MAX_ARTIFACTS = 12

_KIND_LABELS = {
    "chart": "Graphique",
    "model": "Modèle",
    "report": "Rapport",
    "explanation": "Explication",
    "statistical_result": "Résultat statistique",
    "root_cause": "Analyse causale",
    "decision_scenario": "Scénario",
    "analysis_result": "Analyse",
}


def extract_run_artifacts(run: AgentTurnRun) -> list[dict[str, Any]]:
    """Extract compact semantic references from succeeded deterministic steps.

    The payload is intentionally small: it stores IDs, columns, metrics and a
    short summary, never an unrestricted raw result dump.
    """
    artifacts: list[dict[str, Any]] = []
    for index, step in enumerate(run.steps):
        if step.status != "succeeded":
            continue
        result = step.result if isinstance(step.result, dict) else {}
        artifact = _artifact_from_step(run, step.tool, step.args, result, index)
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


def remember_run_artifacts(memory_store: Any, session_id: str, run: AgentTurnRun) -> list[dict[str, Any]]:
    item = memory_store.get_or_create(session_id)
    existing = _clean_artifacts(item.facts.get(ARTIFACT_FACT_KEY))
    existing, counters = _ensure_reference_metadata(existing)
    created = extract_run_artifacts(run)
    if not created:
        return existing

    for artifact in created:
        kind = str(artifact.get("kind") or "analysis_result")
        counters[kind] = counters.get(kind, 0) + 1
        artifact["kind_sequence"] = counters[kind]
        artifact["reference_name"] = _reference_name(artifact)
        artifact["aliases"] = _aliases(artifact)

    dataset_id = run.context.activeDatasetId
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact in [*created, *existing]:
        artifact_id = str(artifact.get("id") or "")
        if not artifact_id or artifact_id in seen:
            continue
        # Never retain dataset-bound artifacts across a dataset switch.
        bound_dataset = artifact.get("dataset_id")
        if dataset_id and bound_dataset and bound_dataset != dataset_id:
            continue
        seen.add(artifact_id)
        merged.append(artifact)
        if len(merged) >= MAX_ARTIFACTS:
            break
    memory_store.remember_fact(session_id, ARTIFACT_FACT_KEY, merged)
    return merged


def recent_artifacts(memory: Any, *, kind: str | None = None) -> list[dict[str, Any]]:
    items, _ = _ensure_reference_metadata(_clean_artifacts(memory.facts.get(ARTIFACT_FACT_KEY)))
    if kind is None:
        return items
    return [item for item in items if item.get("kind") == kind]


def compact_artifacts(memory: Any, limit: int = 5) -> list[dict[str, Any]]:
    return [
        {
            key: item.get(key)
            for key in (
                "id", "kind", "kind_sequence", "reference_name", "label", "tool",
                "dataset_id", "model_id", "chart_id", "report_id", "columns",
                "summary", "metrics", "created_at",
            )
            if item.get(key) not in (None, "", [], {})
        }
        for item in recent_artifacts(memory)[:limit]
    ]


def project_artifacts_for_model(
    memory: Any,
    *,
    external: bool,
    include_column_names_external: bool,
    limit: int = 5,
) -> list[dict[str, Any]]:
    items = compact_artifacts(memory, limit=limit)
    if not external or include_column_names_external:
        return items
    projected: list[dict[str, Any]] = []
    for item in items:
        clean = dict(item)
        clean.pop("columns", None)
        # Summaries can contain schema names, so external providers receive a
        # structural summary rebuilt from non-row metadata and metrics only.
        bits = [str(clean.get("kind") or "résultat analytique"), str(clean.get("tool") or "outil déterministe")]
        metrics = clean.get("metrics")
        if isinstance(metrics, dict) and metrics:
            bits.append(", ".join(f"{k}={_fmt(float(v))}" for k, v in list(metrics.items())[:4] if isinstance(v, (int, float))))
        clean["summary"] = " · ".join(bit for bit in bits if bit)
        projected.append(clean)
    return projected


def _artifact_from_step(run: AgentTurnRun, tool: str, args: dict[str, Any], result: dict[str, Any], index: int) -> dict[str, Any] | None:
    kind = "analysis_result"
    label = str(getattr(run.steps[index], "label", None) or tool)
    model_id = result.get("model_id") or args.get("model_id")
    chart_id = result.get("visualization_id") or result.get("chart_id")
    report_id = result.get("report_id")

    if tool == "create_visualization":
        kind = "chart"
        label = f"Graphique {result.get('chart_type') or result.get('type') or args.get('chart_type') or ''}".strip()
    elif tool in {"run_regression", "run_automl", "benchmark_models", "train_model"} or model_id:
        kind = "model"
        label = f"Modèle {result.get('algorithm') or result.get('best_algorithm') or model_id or ''}".strip()
    elif tool == "generate_report" or report_id:
        kind = "report"
        label = f"Rapport {result.get('format') or ''}".strip()
    elif tool in {"explain_model", "run_model_shap", "run_model_pdp", "run_model_counterfactuals"}:
        kind = "explanation"
    elif tool == "run_statistical_test":
        kind = "statistical_result"
        label = f"Test {result.get('test') or result.get('name') or 'statistique'}"
    elif tool == "run_root_cause_analysis":
        kind = "root_cause"
        label = "Analyse des causes racines"
    elif tool == "optimize_decision_scenarios":
        kind = "decision_scenario"
        label = "Scénario de décision"

    columns = _columns(args, result)
    metrics = _metrics(result)
    summary = _summary(tool, result, columns, metrics, model_id, chart_id, report_id)
    if not summary and not any((model_id, chart_id, report_id, columns, metrics)):
        return None

    display_name = _display_name(args, result)
    if display_name:
        label = display_name

    return {
        "id": f"{run.id}:{index}",
        "turn_run_id": run.id,
        "step_id": run.steps[index].id,
        "kind": kind,
        "label": label,
        "display_name": display_name,
        "tool": tool,
        "dataset_id": run.context.activeDatasetId,
        "model_id": model_id,
        "chart_id": chart_id,
        "report_id": report_id,
        "columns": columns,
        "metrics": metrics,
        "summary": summary or label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "params": _safe_params(args),
    }


def _columns(args: dict[str, Any], result: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (args, result):
        for key in ("column", "x", "y", "target", "time_column", "group", "metric"):
            value = source.get(key)
            if isinstance(value, str) and value.strip() and value not in values:
                values.append(value.strip())
    return values[:8]


def _metrics(result: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key in ("p_value", "statistic", "r2", "r_squared", "accuracy", "f1", "rmse", "mae", "auc", "score", "delta", "delta_pct"):
        value = result.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[key] = float(value)
    nested = result.get("metrics")
    if isinstance(nested, dict):
        for key, value in nested.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                metrics[str(key)] = float(value)
    return dict(list(metrics.items())[:12])


def _safe_params(args: dict[str, Any]) -> dict[str, Any]:
    """Keep only compact replayable parameters; never persist raw input rows."""
    safe: dict[str, Any] = {}
    scalar_keys = (
        "column", "x", "y", "target", "chart_type", "test", "algorithm",
        "task", "metric", "name", "title", "group", "comparison_column",
        "time_column", "outcome", "alpha", "alternative", "kind", "regularization",
        "validation", "max_models", "explain", "baseline_value", "current_value", "format",
        "include_methodology", "include_provenance", "include_visualizations",
        "positive_label", "mode", "min_group_size",
    )
    for key in scalar_keys:
        value = args.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    for key in ("dimensions", "protected_columns", "variables", "features"):
        value = args.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value[:8]):
            safe[key] = value[:8]
    return safe


def _display_name(args: dict[str, Any], result: dict[str, Any]) -> str | None:
    for source in (result, args):
        for key in ("display_name", "name", "title"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    return None


def _summary(tool: str, result: dict[str, Any], columns: list[str], metrics: dict[str, float], model_id: Any, chart_id: Any, report_id: Any) -> str:
    bits: list[str] = []
    if tool == "create_visualization":
        chart_type = result.get("chart_type") or result.get("type")
        bits.append(f"visualisation {chart_type}" if chart_type else "visualisation créée")
    elif tool == "run_statistical_test":
        name = result.get("test") or result.get("name") or "test statistique"
        bits.append(str(name))
    elif model_id:
        algorithm = result.get("algorithm") or result.get("best_algorithm")
        bits.append(f"modèle {algorithm}" if algorithm else "modèle calculé")
    elif report_id:
        bits.append("rapport généré")
    else:
        bits.append(str(getattr(tool, "replace", lambda *_: tool)("_", " ")))
    if columns:
        bits.append("variables " + ", ".join(columns[:4]))
    if metrics:
        shown = list(metrics.items())[:4]
        bits.append(", ".join(f"{k}={_fmt(v)}" for k, v in shown))
    if model_id:
        bits.append(f"model_id={model_id}")
    if chart_id:
        bits.append(f"chart_id={chart_id}")
    if report_id:
        bits.append(f"report_id={report_id}")
    return " · ".join(bits)


def _fmt(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.2f}".replace(",", " ")
    return f"{value:.5g}"


def _clean_artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict) and item.get("id")]


def _ensure_reference_metadata(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Backfill stable per-kind ordinals for memories created before v2.35."""
    copies = [dict(item) for item in items]
    counters: dict[str, int] = {}

    # Existing memory is newest-first. Walk it oldest-first so #1 keeps the
    # intuitive meaning "first created" even after newer artifacts arrive.
    for item in reversed(copies):
        kind = str(item.get("kind") or "analysis_result")
        sequence = item.get("kind_sequence")
        if isinstance(sequence, int) and sequence > 0:
            counters[kind] = max(counters.get(kind, 0), sequence)
        else:
            counters[kind] = counters.get(kind, 0) + 1
            item["kind_sequence"] = counters[kind]
        item["reference_name"] = str(item.get("reference_name") or _reference_name(item))
        item["aliases"] = item.get("aliases") if isinstance(item.get("aliases"), list) else _aliases(item)
    return copies, counters


def _reference_name(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "analysis_result")
    label = _KIND_LABELS.get(kind, "Résultat")
    sequence = item.get("kind_sequence")
    if isinstance(sequence, int) and sequence > 0:
        return f"{label} #{sequence}"
    return label


def _aliases(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for value in (
        item.get("reference_name"), item.get("display_name"), item.get("label"),
        item.get("model_id"), item.get("chart_id"), item.get("report_id"),
    ):
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    for key in ("algorithm", "target", "chart_type", "name", "title"):
        value = params.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    for value in item.get("columns") or []:
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    return values[:16]
