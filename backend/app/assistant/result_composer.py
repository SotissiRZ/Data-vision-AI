from __future__ import annotations

from typing import Any

from .models import AgentTurnRun, AgentTurnStep


def compose_run_results(run: AgentTurnRun) -> str:
    successful = [step for step in run.steps if step.status == "succeeded"]

    if not successful:
        return "Aucun résultat calculé n'est disponible pour cette exécution."

    facts: list[str] = []

    for step in successful:
        result = step.result
        if not isinstance(result, dict):
            continue

        if step.tool == "profile_dataset":
            rows = result.get("rows", result.get("total_rows"))
            columns = result.get("columns_count")
            duplicates = result.get("duplicates")
            if rows is not None and columns is not None:
                facts.append(
                    f"le dataset contient {int(rows)} lignes et {int(columns)} variables"
                )
            if duplicates is not None:
                count = int(duplicates)
                facts.append(
                    "aucun doublon"
                    if count == 0
                    else f"{count} doublon{'s' if count > 1 else ''}"
                )

        elif step.tool == "inspect_missing_values":
            details = result.get("columns")
            if isinstance(details, list):
                total = sum(
                    int(item.get("missing") or 0)
                    for item in details
                    if isinstance(item, dict)
                )
                facts.append(
                    "aucune cellule manquante"
                    if total == 0
                    else f"{total} cellule{'s' if total > 1 else ''} manquante{'s' if total > 1 else ''}"
                )

        elif step.tool == "run_statistical_test":
            test = result.get("test") or result.get("name")
            p_value = result.get("p_value")
            statistic = result.get("statistic")
            bits = []
            if test:
                bits.append(f"test {test}")
            if statistic is not None:
                bits.append(f"statistique {format_number(statistic)}")
            if p_value is not None:
                bits.append(f"p-value {format_number(p_value)}")
            if bits:
                facts.append(", ".join(bits))

        elif step.tool == "run_regression":
            r2 = result.get("r_squared", result.get("r2"))
            if r2 is not None:
                facts.append(f"R² {format_number(r2)}")
            model_id = result.get("model_id")
            if model_id:
                facts.append(f"modèle créé {model_id}")

        elif step.tool == "run_automl":
            model_id = result.get("model_id")
            algorithm = result.get("algorithm") or result.get("best_algorithm")
            if algorithm:
                facts.append(f"meilleur modèle : {algorithm}")
            if model_id:
                facts.append(f"identifiant du modèle : {model_id}")

        elif step.tool == "create_visualization":
            chart_type = result.get("chart_type") or result.get("type")
            if chart_type:
                facts.append(f"visualisation créée : {chart_type}")

        elif step.tool == "generate_report":
            report_id = result.get("report_id")
            fmt = result.get("format")
            if report_id:
                facts.append(
                    f"rapport {fmt or ''} généré (ID {report_id})".strip()
                )

        elif step.tool in {
            "apply_reversible_transform",
            "merge_datasets",
            "delete_column",
        }:
            dataset_id = result.get("dataset_id")
            version = result.get("version")
            if dataset_id:
                suffix = f", version {version}" if version is not None else ""
                facts.append(f"nouvelle version de dataset : {dataset_id}{suffix}")

    if not facts:
        completed = len(successful)
        if completed == 1:
            return "L'étape a réussi. Le résultat détaillé est disponible dans le plan d'exécution."
        return (
            f"{completed} étapes ont réussi. "
            "Les résultats détaillés sont disponibles dans le plan d'exécution."
        )

    return "Résultats : " + "; ".join(facts) + "."


def compact_results(run: AgentTurnRun) -> dict[str, Any]:
    return {
        "turn_run_id": run.id,
        "status": run.status,
        "steps": [
            {
                "tool": step.tool,
                "label": step.label,
                "status": step.status,
                "result": step.result,
            }
            for step in run.steps
            if step.status == "succeeded"
        ],
    }


def format_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1000:
        return f"{number:,.2f}".replace(",", " ")
    if abs(number) < 0.001 and number != 0:
        return f"{number:.3e}"
    return f"{number:.4f}".rstrip("0").rstrip(".")
