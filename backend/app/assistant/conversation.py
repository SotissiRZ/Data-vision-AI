from __future__ import annotations

from dataclasses import dataclass

from .models import AgentIntent, AgentTurnResponse, AssistantContext
from .memory import SessionMemoryStore
from .result_composer import compose_run_results
from .turn_runs import AgentTurnRunStore


@dataclass
class ConversationalResponder:
    turn_store: AgentTurnRunStore
    memory: SessionMemoryStore | None = None

    def respond(
        self,
        *,
        session_id: str,
        message: str,
        intent: AgentIntent,
        context: AssistantContext,
    ) -> AgentTurnResponse | None:
        if intent.name == "show_results":
            latest = self.turn_store.latest_for_session(
                session_id,
                statuses={"completed", "partial"},
            )
            if latest is None:
                answer = (
                    "Je n'ai pas encore de résultat d'analyse dans cette session. "
                    "Demandez-moi par exemple d'analyser le dataset actif."
                )
            else:
                answer = compose_run_results(latest)
            return self._response(session_id, intent, answer)

        if intent.name == "dataset_assessment":
            facts = context.uiState or {}
            dataset_name = facts.get("datasetName") or "le dataset actif"
            rows = _to_int(facts.get("rowCount"))
            columns = _to_int(facts.get("columnCount"))
            missing = _to_int(facts.get("missingCells"))
            duplicates = _to_int(facts.get("duplicateCount"))
            quality = _to_float(facts.get("qualityScore"))
            issue_count = _to_int(facts.get("qualityIssuesCount"))
            numeric_count = _to_int(facts.get("numericColumnCount"))
            categorical_count = _to_int(facts.get("categoricalColumnCount"))

            if (
                rows is None
                and columns is None
                and quality is None
                and missing is None
                and duplicates is None
            ):
                answer = (
                    "Je vois qu'un dataset est actif, mais je n'ai pas encore assez "
                    "d'indicateurs de profilage pour donner un avis fondé. "
                    "Je peux le profiler et vérifier sa qualité si vous le souhaitez."
                )
                return self._response(session_id, intent, answer)

            parts: list[str] = []

            if quality is not None:
                if quality >= 90:
                    verdict = "très bonne"
                elif quality >= 80:
                    verdict = "bonne"
                elif quality >= 60:
                    verdict = "correcte mais perfectible"
                else:
                    verdict = "fragile et à corriger avant une analyse avancée"

                parts.append(
                    f"La qualité globale de {dataset_name} est {verdict} "
                    f"avec un score de {quality:g}/100."
                )
            else:
                parts.append(
                    f"Voici mon appréciation factuelle de {dataset_name}."
                )

            structure: list[str] = []
            if rows is not None:
                structure.append(f"{rows} lignes")
            if columns is not None:
                structure.append(f"{columns} variables")
            if structure:
                parts.append("Il contient " + " et ".join(structure) + ".")

            hygiene: list[str] = []
            if missing is not None:
                hygiene.append(
                    "aucune cellule manquante"
                    if missing == 0
                    else (
                        f"{missing} cellule{'s' if missing > 1 else ''} "
                        f"manquante{'s' if missing > 1 else ''}"
                    )
                )
            if duplicates is not None:
                hygiene.append(
                    "aucun doublon"
                    if duplicates == 0
                    else f"{duplicates} doublon{'s' if duplicates > 1 else ''}"
                )
            if hygiene:
                parts.append(
                    "Sur l'hygiène des données : "
                    + " et ".join(hygiene)
                    + "."
                )

            typing: list[str] = []
            if numeric_count is not None:
                typing.append(
                    f"{numeric_count} variable"
                    f"{'s' if numeric_count != 1 else ''} numérique"
                    f"{'s' if numeric_count != 1 else ''}"
                )
            if categorical_count is not None:
                typing.append(
                    f"{categorical_count} variable"
                    f"{'s' if categorical_count != 1 else ''} catégorielle"
                    f"{'s' if categorical_count != 1 else ''}"
                )
            if typing:
                parts.append("Structure : " + " et ".join(typing) + ".")

            if issue_count is not None and issue_count > 0:
                parts.append(
                    f"DataVision signale toutefois {issue_count} problème"
                    f"{'s' if issue_count > 1 else ''} de qualité à examiner."
                )
            elif (
                quality is not None
                and quality >= 80
                and missing == 0
                and duplicates == 0
            ):
                parts.append(
                    "C'est une base saine pour poursuivre l'exploration, "
                    "mais je vérifierais encore les distributions, les valeurs aberrantes "
                    "et la pertinence métier des variables avant de modéliser."
                )
            else:
                parts.append(
                    "Avant de modéliser, je recommande de vérifier les distributions, "
                    "les valeurs aberrantes et les variables potentiellement identifiantes."
                )

            answer = " ".join(parts)
            return self._response(session_id, intent, answer)


        if intent.name == "explain_previous":
            item = (
                self.memory.get_or_create(session_id)
                if self.memory is not None
                else None
            )
            latest = self.turn_store.latest_for_session(
                session_id,
                statuses={"completed", "partial"},
            )

            if item and item.last_result_summary:
                previous = item.last_result_summary
            elif latest is not None:
                previous = compose_run_results(latest)
            else:
                previous = None

            if not previous:
                answer = (
                    "Je n'ai pas assez de contexte précédent pour expliquer « pourquoi ». "
                    "Précisez le résultat ou l'observation que vous voulez comprendre."
                )
            else:
                answer = (
                    "Parce que mon appréciation repose uniquement sur les faits déjà calculés "
                    "par DataVision. Le point de départ était : "
                    f"{previous} "
                    "Si vous voulez une explication causale ou statistique plus profonde, "
                    "je peux lancer l'analyse appropriée au lieu de l'inventer."
                )

            return self._response(session_id, intent, answer)

        if intent.name == "capabilities":
            answer = (
                "Dans DataVision, je peux analyser les datasets chargés, lancer les moteurs "
                "statistiques et ML autorisés, créer des visualisations, préparer des rapports "
                "et agir via les connecteurs configurés. "
                "Je n'ai pas de navigation Internet générale dans cette version. "
                "Un accès externe n'est possible que via un provider ou un connecteur explicitement "
                "configuré et autorisé par les règles de confidentialité DataVision."
            )
            return self._response(session_id, intent, answer)

        if intent.name == "conversation":
            lower = message.lower().strip()
            if lower.startswith(("bonjour", "bonsoir", "salut", "hello", "hey")):
                answer = (
                    "Bonjour. Je suis DataVision AI. "
                    "Posez-moi une question sur le dataset actif ou demandez-moi une analyse précise."
                )
            elif "merci" in lower:
                answer = "Avec plaisir."
            elif "qui es" in lower:
                answer = (
                    "Je suis l'assistant DataVision AI. "
                    "Je travaille avec le contexte de l'application et les moteurs gouvernés de DataVision."
                )
            else:
                answer = "Je vous écoute."
            return self._response(session_id, intent, answer)

        return None

    @staticmethod
    def _response(
        session_id: str,
        intent: AgentIntent,
        answer: str,
    ) -> AgentTurnResponse:
        return AgentTurnResponse(
            session_id=session_id,
            intent=intent,
            message=answer,
            speak=True,
            status="completed",
            steps=[],
            metadata={"conversation_only": True},
        )


def _to_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
