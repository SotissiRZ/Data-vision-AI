from __future__ import annotations

from .models import (
    AssistantAction,
    AssistantContext,
    AssistantEvent,
    ProactiveAlert,
)


def evaluate_proactive_event(
    event: AssistantEvent,
    context: AssistantContext,
) -> list[ProactiveAlert]:
    """
    Deterministic first-pass advisor.

    High-risk signals must not depend solely on an LLM. The AI layer may later
    enrich the explanation, but these guardrails remain deterministic.
    """
    alerts: list[ProactiveAlert] = []

    if event.type == "ml.leakage.detected":
        target = event.payload.get("target", "la cible")
        feature = event.payload.get("feature", "une variable d'entrée")
        alerts.append(
            ProactiveAlert(
                title="Risque de fuite de données",
                message=(
                    f"{feature} semble contenir de l'information directement liée à {target}. "
                    "La performance du modèle pourrait être artificiellement élevée."
                ),
                severity="critical",
                speak=True,
                actionLabel="Examiner",
                action=AssistantAction(
                    tool="inspect_data_leakage",
                    label="Examiner la fuite potentielle",
                    risk="read",
                    args=event.payload,
                ),
            )
        )

    elif event.type == "analysis.failed":
        reason = event.payload.get("reason") or "L'analyse a échoué."
        alerts.append(
            ProactiveAlert(
                title="Analyse interrompue",
                message=str(reason),
                severity="warning",
                speak=False,
                action=AssistantAction(
                    tool="diagnose_analysis_failure",
                    label="Diagnostiquer",
                    risk="read",
                    args=event.payload,
                ),
            )
        )

    elif event.type == "dataset.quality.issue":
        rule = event.payload.get("rule")
        column = event.payload.get("column")
        value = event.payload.get("value")

        if rule == "missing_ratio" and isinstance(value, (int, float)):
            if value >= 0.50:
                severity = "critical"
                message = (
                    f"La colonne {column or 'sélectionnée'} contient environ "
                    f"{value:.0%} de valeurs manquantes."
                )
            elif value >= 0.10:
                severity = "warning"
                message = (
                    f"La colonne {column or 'sélectionnée'} contient environ "
                    f"{value:.1%} de valeurs manquantes."
                )
            else:
                severity = "suggestion"
                message = (
                    f"La colonne {column or 'sélectionnée'} contient environ "
                    f"{value:.1%} de valeurs manquantes."
                )

            alerts.append(
                ProactiveAlert(
                    title="Qualité des données",
                    message=message,
                    severity=severity,
                    speak=severity == "critical",
                    action=AssistantAction(
                        tool="inspect_missing_values",
                        label="Examiner les valeurs manquantes",
                        risk="read",
                        args=event.payload,
                    ),
                )
            )

    elif event.type == "transform.previewed":
        removed_ratio = event.payload.get("removed_ratio")
        if isinstance(removed_ratio, (int, float)) and removed_ratio >= 0.30:
            alerts.append(
                ProactiveAlert(
                    title="Transformation à fort impact",
                    message=(
                        f"Cette transformation supprimerait environ {removed_ratio:.0%} "
                        "des observations. Vérifiez l'impact avant application."
                    ),
                    severity="critical",
                    speak=True,
                )
            )

    elif event.type == "visualization.error":
        alerts.append(
            ProactiveAlert(
                title="Problème de visualisation",
                message=str(
                    event.payload.get("reason")
                    or "Le graphique ne peut pas être construit avec la configuration actuelle."
                ),
                severity="warning",
                speak=False,
                action=AssistantAction(
                    tool="diagnose_visualization",
                    label="Corriger le graphique",
                    risk="read",
                    args=event.payload,
                ),
            )
        )

    return alerts
