from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable

from .models import (
    AssistantAction,
    AssistantContext,
    AssistantEvent,
    ProactiveAlert,
)


def _stable_payload(payload: dict) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(sorted((str(k), str(v)) for k, v in payload.items()))


def decorate_proactive_alerts(
    alerts: Iterable[ProactiveAlert],
    event: AssistantEvent,
) -> list[ProactiveAlert]:
    decorated: list[ProactiveAlert] = []
    for alert in alerts:
        tool = alert.action.tool if alert.action else ""
        raw = f"{event.type}|{tool}|{alert.title}|{_stable_payload(event.payload)}"
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        cooldown = 20 if alert.severity == "critical" else 60 if alert.severity == "warning" else 180
        decorated.append(
            alert.model_copy(
                update={
                    "fingerprint": fingerprint,
                    "sourceEventId": event.id,
                    "cooldownSeconds": cooldown,
                }
            )
        )
    return decorated


class ProactiveAlertGate:
    """Workspace-local anti-spam gate for deterministic proactive alerts.

    The gate never suppresses a *different* diagnosis. It only throttles exact
    semantic repeats (same fingerprint) for the alert-defined cooldown.
    """

    def __init__(self) -> None:
        self._last_emitted: dict[str, datetime] = {}

    def filter(
        self,
        alerts: Iterable[ProactiveAlert],
        *,
        now: datetime | None = None,
    ) -> list[ProactiveAlert]:
        now = now or datetime.now(timezone.utc)
        emitted: list[ProactiveAlert] = []
        for alert in alerts:
            key = alert.fingerprint or alert.id
            last = self._last_emitted.get(key)
            if last is not None:
                age = (now - last).total_seconds()
                if age < alert.cooldownSeconds:
                    continue
            self._last_emitted[key] = now
            emitted.append(alert)
        # Keep memory bounded in long-running workspaces.
        stale_before = now.timestamp() - 7200
        self._last_emitted = {
            key: value
            for key, value in self._last_emitted.items()
            if value.timestamp() >= stale_before
        }
        return emitted


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

    elif event.type == "ml.overfit.detected":
        train_score = event.payload.get("train_score")
        validation_score = event.payload.get("validation_score")
        details = ""
        if isinstance(train_score, (int, float)) and isinstance(validation_score, (int, float)):
            details = f" (entraînement {train_score:.3f} vs validation {validation_score:.3f})"
        alerts.append(
            ProactiveAlert(
                title="Surapprentissage probable",
                message=(
                    "Le modèle semble nettement meilleur sur les données d'entraînement que sur la validation"
                    f"{details}. Vérifiez le split, les variables et la régularisation."
                ),
                severity="warning",
                speak=False,
                action=AssistantAction(
                    tool="monitor_model_health",
                    label="Examiner la généralisation",
                    risk="read",
                    args={k: v for k, v in event.payload.items() if k in {"model_id", "train_score", "validation_score"}},
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

    elif event.type == "query.slow":
        duration = event.payload.get("duration_seconds")
        suffix = f" ({float(duration):.1f} s)" if isinstance(duration, (int, float)) else ""
        alerts.append(
            ProactiveAlert(
                title="Requête lente",
                message=(
                    f"Cette requête prend plus de temps que prévu{suffix}. "
                    "Je peux examiner le plan ou réduire le volume traité."
                ),
                severity="suggestion",
                speak=False,
                action=AssistantAction(
                    tool="diagnose_analysis_failure",
                    label="Analyser la requête",
                    risk="read",
                    args={"signal": "slow_query", **event.payload},
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

    elif event.type == "dataset.schema.changed":
        removed = event.payload.get("removed_columns") or []
        changed = event.payload.get("type_changes") or []
        if removed or changed:
            alerts.append(
                ProactiveAlert(
                    title="Schéma du dataset modifié",
                    message=(
                        f"{len(removed)} colonne(s) supprimée(s) et {len(changed)} changement(s) de type détecté(s). "
                        "Les analyses ou modèles liés peuvent devoir être revalidés."
                    ),
                    severity="warning",
                    speak=False,
                    action=AssistantAction(
                        tool="profile_dataset",
                        label="Reprofiler le dataset",
                        risk="read",
                        args={},
                    ),
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
