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


        elif step.tool == "evaluate_model_fairness":
            rows = result.get("rows_evaluated")
            views = result.get("reports") or []
            used = result.get("protected_feature_usage") or []
            text = f"audit Responsible AI calculé sur {rows} lignes" if rows is not None else "audit Responsible AI calculé"
            if views:
                text += f", {len(views)} vue(s) de groupe"
            if used:
                text += f", attention : {len(used)} variable(s) d’audit utilisée(s) comme feature"
            facts.append(text)

        elif step.tool == "assess_model_risk":
            level = result.get("risk_level")
            factors = result.get("factors") or []
            if level:
                facts.append(f"risque modèle : {level}, {len(factors)} facteur(s) à examiner")

        elif step.tool == "responsible_ai_publication_gate":
            allowed = result.get("allowed")
            blockers = result.get("blockers") or []
            if allowed is not None:
                facts.append(
                    "publication gate Responsible AI ouvert"
                    if allowed
                    else f"publication gate Responsible AI bloqué par {len(blockers)} contrôle(s)"
                )

        elif step.tool == "get_model_registry_status":
            stage = result.get("stage")
            role = result.get("role")
            version = result.get("version_no")
            if stage:
                facts.append(
                    f"Model Registry : stage {stage}, rôle {role or '—'}, "
                    f"version v{version or '—'}"
                )

        elif step.tool == "monitor_model_health":
            status = result.get("status")
            degradation = result.get("degradation") or {}
            metric = degradation.get("relative_metric_degradation")
            drift = degradation.get("max_feature_drift_score")
            bits = [f"monitoring modèle : {status or 'terminé'}"]
            if metric is not None:
                bits.append(f"dégradation relative {format_number(float(metric) * 100)}%")
            if drift is not None:
                bits.append(f"drift feature max {format_number(drift)}")
            facts.append(", ".join(bits))

        elif step.tool in {"check_model_retraining", "request_model_retraining"}:
            recommended = bool(result.get("retraining_recommended"))
            created = bool(result.get("request_created"))
            if created:
                facts.append("réentraînement recommandé ; demande traçable créée")
            elif recommended:
                facts.append("réentraînement recommandé selon la politique MLOps")
            else:
                facts.append("aucun réentraînement recommandé selon la politique actuelle")

        elif step.tool == "transition_model_stage":
            stage = result.get("stage")
            role = result.get("role")
            facts.append(f"modèle déplacé vers {stage or 'le stage demandé'} ({role or 'rôle mis à jour'})")

        elif step.tool == "run_root_cause_analysis":
            target = result.get("target")
            delta = result.get("delta")
            delta_pct = result.get("delta_pct")
            baseline = result.get("baseline") or {}
            current = result.get("current") or {}
            bits = []
            if target:
                bits.append(f"écart de {target}")
            if baseline.get("metric") is not None and current.get("metric") is not None:
                bits.append(
                    f"{format_number(baseline['metric'])} → "
                    f"{format_number(current['metric'])}"
                )
            if delta is not None:
                delta_text = format_number(delta)
                if float(delta) >= 0:
                    delta_text = f"+{delta_text}"
                bits.append(f"delta {delta_text}")
            if delta_pct is not None:
                pct = format_number(delta_pct)
                if float(delta_pct) >= 0:
                    pct = f"+{pct}"
                bits.append(f"{pct}%")
            dimensions = result.get("dimension_decompositions") or []
            if dimensions:
                bits.append(
                    f"dimension prioritaire : {dimensions[0].get('dimension')}"
                )
            if bits:
                facts.append(", ".join(bits))

        elif step.tool == "optimize_decision_scenarios":
            scenarios = result.get("recommended_scenarios") or []
            objective = result.get("objective")
            if scenarios:
                best = scenarios[0]
                prediction = best.get("prediction")
                probability = best.get("target_probability")
                text = f"meilleur scénario pour l'objectif {objective or 'défini'}"
                if prediction is not None:
                    text += f", prédiction {format_number(prediction)}"
                if probability is not None:
                    text += f", probabilité cible {format_number(probability)}"
                facts.append(text)
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
