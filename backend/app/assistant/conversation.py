from __future__ import annotations

from dataclasses import dataclass

from .models import AgentIntent, AgentTurnResponse, AssistantContext
from .result_composer import compose_run_results
from .turn_runs import AgentTurnRunStore


@dataclass
class ConversationalResponder:
    turn_store: AgentTurnRunStore

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
