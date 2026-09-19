from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .action_runs import ActionLifecycleManager
from .critic import DeterministicCritic
from .conversation import ConversationalResponder
from .result_composer import compose_run_results, compact_results
from .settings_intent import SettingsAwareIntentResolver
from .grounded_conversation import SettingsAwareConversationEngine
from .intent import resolve_intent
from .memory import SessionMemoryStore
from .models import (
    AgentIntent,
    AgentTurnRequest,
    AgentTurnResponse,
    AgentTurnRun,
    AgentTurnStep,
    AssistantAction,
)
from .plan import validate_agent_plan
from .planner_runtime import PlannerProvider
from .recovery import RecoveryPolicy
from .reference_resolver import resolve_references
from .tools import AssistantToolRegistry
from .executor import HostAuthorization
from .turn_runs import AgentTurnRunStore


@dataclass
class AgentOrchestrator:
    registry: AssistantToolRegistry
    authorization: HostAuthorization
    action_lifecycle: ActionLifecycleManager
    memory: SessionMemoryStore
    planner: PlannerProvider
    critic: DeterministicCritic
    recovery: RecoveryPolicy
    turn_store: AgentTurnRunStore

    def run_turn(self, request: AgentTurnRequest) -> AgentTurnResponse:
        context = request.context.model_copy(deep=True)
        memory_item = self.memory.get_or_create(
            request.session_id,
            context.workspaceId,
        )

        # The selected object is always the strongest grounding signal.
        if (
            context.selectedEntity
            and context.selectedEntity.type in {"column", "variable"}
            and context.selectedEntity.id
        ):
            self.memory.remember_focus_column(
                request.session_id,
                context.selectedEntity.id,
            )
            memory_item = self.memory.get_or_create(request.session_id)

        intent = resolve_intent(request.message, context)

        reference = resolve_references(
            message=request.message,
            intent=intent,
            context=context,
            memory=memory_item,
        )
        intent = reference.intent
        context = reference.context

        if reference.clarification:
            response = AgentTurnResponse(
                session_id=request.session_id,
                intent=intent,
                message=reference.clarification,
                speak=True,
                status="needs_clarification",
                steps=[],
                metadata={
                    "reference_resolution": "ambiguous",
                    "safe_fallback": True,
                },
            )
            self.memory.remember_turn(
                request.session_id,
                intent=intent.name,
                entities=intent.entities,
                result_summary=response.message,
            )
            return response

        for column in reference.resolved_columns:
            self.memory.remember_focus_column(request.session_id, column)

        self.memory.set_objective(request.session_id, request.message)

        original_intent = intent
        if intent.name == "unknown":
            intent = SettingsAwareIntentResolver().resolve(
                message=request.message,
                context=context,
                current=intent,
            )

        # Deterministic conversational answers remain first choice for results,
        # capabilities, dataset assessment and short follow-ups.
        conversational = ConversationalResponder(
            self.turn_store,
            self.memory,
        ).respond(
            session_id=request.session_id,
            message=request.message,
            intent=intent,
            context=context,
        )

        # If hybrid NLU reclassified an otherwise unknown request as a
        # conversation, ask the configured explanation model to answer using
        # only governed semantic context + deterministic prior results.
        if (
            original_intent.name == "unknown"
            and intent.name == "conversation"
        ):
            grounded = SettingsAwareConversationEngine(
                self.turn_store
            ).answer(
                session_id=request.session_id,
                message=request.message,
                context=context,
            )
            if grounded:
                response = AgentTurnResponse(
                    session_id=request.session_id,
                    intent=intent,
                    message=grounded,
                    speak=True,
                    status="completed",
                    steps=[],
                    metadata={
                        "conversation_only": True,
                        "grounded_model_answer": True,
                    },
                )
                self.memory.remember_turn(
                    request.session_id,
                    intent=intent.name,
                    entities=intent.entities,
                    result_summary=grounded,
                )
                return response

        if conversational is not None:
            self.memory.remember_turn(
                request.session_id,
                intent=intent.name,
                entities=intent.entities,
                result_summary=conversational.message,
            )
            return conversational

        if intent.name == "unknown":
            response = AgentTurnResponse(
                session_id=request.session_id,
                intent=intent,
                message=(
                    "Je ne veux pas transformer votre question en analyse par défaut ni deviner votre intention. "
                    "Précisez ce que vous voulez savoir ou faire. "
                    "Vous pouvez aussi utiliser une relance comme « et pourquoi ? », "
                    "« montre-moi ça en graphique » ou « fais pareil avec Profit »."
                ),
                speak=True,
                status="needs_clarification",
                metadata={"safe_fallback": True},
            )
            self.memory.remember_turn(
                request.session_id,
                intent=intent.name,
                entities=intent.entities,
                result_summary=response.message,
            )
            return response

        plan = self.planner.plan(
            message=request.message,
            intent=intent,
            context=context,
            attachment_ids=request.attachment_ids,
        )

        if not plan:
            return AgentTurnResponse(
                session_id=request.session_id,
                intent=intent,
                message=self._missing_context_message(intent.name),
                speak=True,
                status="needs_clarification",
                metadata={},
            )

        validated = validate_agent_plan(
            steps=plan,
            context=context,
            registry=self.registry,
            authorization=self.authorization,
        )

        turn_steps: list[AgentTurnStep] = []
        for source, validation in zip(plan, validated.steps):
            turn_steps.append(
                AgentTurnStep(
                    id=source.id,
                    tool=source.tool,
                    label=source.label,
                    reason=source.reason,
                    args=source.args,
                    status=(
                        "ready"
                        if validation.status == "ready"
                        else "waiting_confirmation"
                        if validation.status == "confirmation_required"
                        else "failed"
                    ),
                    error=validation.reason if validation.status == "deny" else None,
                )
            )

        if not validated.valid:
            critic = self.critic.review(turn_steps)
            return AgentTurnResponse(
                session_id=request.session_id,
                intent=intent,
                message="Le plan contient une étape qui ne peut pas être exécutée en sécurité.",
                speak=True,
                status="failed",
                steps=turn_steps,
                critic=critic,
                metadata={},
            )

        turn_run = self.turn_store.create(
            AgentTurnRun(
                session_id=request.session_id,
                request_message=request.message,
                context=context,
                attachment_ids=request.attachment_ids,
                intent=intent,
                steps=turn_steps,
                status="running",
            )
        )

        return self._advance(
            turn_run.id,
            auto_execute_safe_steps=request.auto_execute_safe_steps,
        )

    def continue_turn(
        self,
        turn_run_id: str,
        *,
        confirmed_action_run_id: str | None = None,
        auto_execute_safe_steps: bool = True,
    ) -> AgentTurnResponse:
        run = self._require_turn(turn_run_id)

        if run.status in {"completed", "failed", "cancelled"}:
            return self._response_from_run(run)

        step = self._current_step(run)
        if step and step.status == "waiting_confirmation":
            if not confirmed_action_run_id:
                return self._response_from_run(run)

            if step.action_run_id != confirmed_action_run_id:
                raise ValueError("La confirmation ne correspond pas à l'étape courante.")

            action_run = self.action_lifecycle.store.get(confirmed_action_run_id)
            if action_run is None:
                raise KeyError("Action à confirmer introuvable.")

            if action_run.status == "waiting_confirmation":
                raise ValueError(
                    "L'action doit d'abord être confirmée via /actions/{id}/confirm."
                )

            if action_run.status == "cancelled":
                step.status = "skipped"
                run.status = "cancelled"
                run.final_message = "L'action a été annulée par l'utilisateur."
                run.critic = self.critic.review(run.steps)
                self.turn_store.save(run)
                return self._response_from_run(run)

            if action_run.status != "ready":
                raise ValueError(
                    f"L'action confirmée est dans l'état inattendu {action_run.status}."
                )

            executed = self.action_lifecycle.execute(action_run.id)
            if executed.status == "succeeded":
                step.status = "succeeded"
                step.result = executed.result
                self._record_success(run.session_id, step, executed.reversible)
                run.current_step_index += 1
            else:
                step.status = "failed"
                step.error = executed.error or executed.reason
                run.status = "failed"
                run.final_message = self._failure_message(run.steps)
                run.critic = self.critic.review(run.steps)
                self.turn_store.save(run)
                return self._response_from_run(run)

            self.turn_store.save(run)

        return self._advance(
            run.id,
            auto_execute_safe_steps=auto_execute_safe_steps,
        )

    def cancel_turn(self, turn_run_id: str, reason: str | None = None) -> AgentTurnResponse:
        run = self._require_turn(turn_run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return self._response_from_run(run)

        step = self._current_step(run)
        if step and step.action_run_id:
            action_run = self.action_lifecycle.store.get(step.action_run_id)
            if action_run and action_run.status == "waiting_confirmation":
                self.action_lifecycle.confirm(action_run.id, False)
                step.status = "skipped"

        run.status = "cancelled"
        run.final_message = reason or "Le plan a été annulé."
        run.critic = self.critic.review(run.steps)
        self.turn_store.save(run)
        return self._response_from_run(run)

    def get_turn(self, turn_run_id: str) -> AgentTurnRun:
        return self._require_turn(turn_run_id)

    def _advance(
        self,
        turn_run_id: str,
        *,
        auto_execute_safe_steps: bool,
    ) -> AgentTurnResponse:
        run = self._require_turn(turn_run_id)
        run.status = "running"

        while run.current_step_index < len(run.steps):
            step = run.steps[run.current_step_index]

            if step.status == "succeeded":
                run.current_step_index += 1
                continue

            action = AssistantAction(
                tool=step.tool,
                label=step.label,
                description=step.reason,
                args=step.args,
                risk="read",
            )

            if not step.action_run_id:
                action_run = self.action_lifecycle.propose(
                    action=action,
                    context=run.context,
                    session_id=run.session_id,
                )
                step.action_run_id = action_run.id
            else:
                action_run = self.action_lifecycle.store.get(step.action_run_id)
                if action_run is None:
                    step.status = "failed"
                    step.error = "ActionRun manquant."
                    run.status = "failed"
                    break

            if action_run.status == "waiting_confirmation":
                step.status = "waiting_confirmation"
                run.status = "waiting_confirmation"
                run.final_message = (
                    f"L'étape « {step.label} » nécessite votre confirmation avant de continuer."
                )
                # Critical invariant: stop the plan here. No downstream step may run.
                break

            if action_run.status == "failed":
                step.status = "failed"
                step.error = action_run.error or action_run.reason
                run.status = "failed"
                break

            if not auto_execute_safe_steps:
                step.status = "ready"
                run.status = "partial"
                run.final_message = "Le plan est validé et prêt à être exécuté."
                break

            if action_run.status == "ready":
                step.status = "running"
                self.turn_store.save(run)
                executed = self.action_lifecycle.execute(action_run.id)
            elif action_run.status == "succeeded":
                executed = action_run
            else:
                step.status = "failed"
                step.error = f"État d'action inattendu : {action_run.status}"
                run.status = "failed"
                break

            if executed.status == "succeeded":
                step.status = "succeeded"
                step.result = executed.result
                self._record_success(run.session_id, step, executed.reversible)
                run.current_step_index += 1
                self.turn_store.save(run)
                continue

            step.status = "failed"
            step.error = executed.error or executed.reason
            recovery = self.recovery.decide(step)

            if recovery.action == "retry_once":
                retry_run = self.action_lifecycle.propose(
                    action=action,
                    context=run.context,
                    session_id=run.session_id,
                )
                step.action_run_id = retry_run.id
                if retry_run.status == "ready":
                    retry_result = self.action_lifecycle.execute(retry_run.id)
                    if retry_result.status == "succeeded":
                        step.status = "succeeded"
                        step.result = retry_result.result
                        step.error = None
                        self._record_success(
                            run.session_id,
                            step,
                            retry_result.reversible,
                        )
                        run.current_step_index += 1
                        self.turn_store.save(run)
                        continue

            run.status = "failed"
            break

        if run.current_step_index >= len(run.steps):
            run.status = "completed"
            run.final_message = compose_run_results(run)
            self.memory.remember_fact(
                run.session_id,
                "last_results",
                compact_results(run),
            )
            self.memory.remember_turn(
                run.session_id,
                intent=run.intent.name,
                entities=run.intent.entities,
                result_summary=run.final_message,
            )
            for key in ("column", "x", "y", "target"):
                value = run.intent.entities.get(key)
                if isinstance(value, str) and value:
                    self.memory.remember_focus_column(
                        run.session_id,
                        value,
                    )
            for step in run.steps:
                for key in ("x", "y", "target"):
                    value = step.args.get(key)
                    if isinstance(value, str) and value:
                        self.memory.remember_focus_column(
                            run.session_id,
                            value,
                        )
        elif run.status == "failed":
            run.final_message = self._failure_message(run.steps)

        run.critic = self.critic.review(run.steps)
        self.turn_store.save(run)
        return self._response_from_run(run)

    def _response_from_run(self, run: AgentTurnRun) -> AgentTurnResponse:
        pending = [
            step.action_run_id
            for step in run.steps
            if step.status == "waiting_confirmation" and step.action_run_id
        ]

        status_map = {
            "completed": "completed",
            "waiting_confirmation": "waiting_confirmation",
            "partial": "partial",
            "failed": "failed",
            "cancelled": "partial",
            "created": "partial",
            "running": "partial",
        }

        return AgentTurnResponse(
            session_id=run.session_id,
            intent=run.intent,
            message=run.final_message or "Traitement en cours.",
            speak=True,
            status=status_map[run.status],
            steps=run.steps,
            critic=run.critic,
            pending_action_run_ids=pending,
            metadata={
                "turn_run_id": run.id,
                "planner": self.planner.__class__.__name__,
                "critic": self.critic.__class__.__name__,
                "current_step_index": run.current_step_index,
            },
        )

    def _record_success(self, session_id: str, step: AgentTurnStep, reversible: bool):
        self.memory.record_decision(
            session_id,
            action=step.tool,
            result="succeeded",
            reversible=reversible,
        )

    def _require_turn(self, turn_run_id: str) -> AgentTurnRun:
        run = self.turn_store.get(turn_run_id)
        if run is None:
            raise KeyError(f"Turn run introuvable : {turn_run_id}")
        return run

    @staticmethod
    def _current_step(run: AgentTurnRun) -> AgentTurnStep | None:
        if run.current_step_index >= len(run.steps):
            return None
        return run.steps[run.current_step_index]

    @staticmethod
    def _missing_context_message(intent_name: str) -> str:
        mapping = {
            "predict_target": "Précisez la variable cible et le type de tâche : classification, régression ou forecasting.",
            "compare_groups": "Sélectionnez les variables ou groupes à comparer.",
            "geospatial_analysis": "Sélectionnez les couches SIG et l'opération souhaitée.",
            "visualize": "Sélectionnez au moins une variable à visualiser.",
            "explain_model": "Sélectionnez d'abord un modèle.",
        }
        return mapping.get(
            intent_name,
            "Je dois disposer d'un contexte plus précis avant de construire un plan sûr.",
        )

    @staticmethod
    def _success_message(intent_name: str, steps: list[AgentTurnStep]) -> str:
        completed = sum(1 for step in steps if step.status == "succeeded")
        if completed == 1:
            return "Analyse terminée. 1 étape exécutée et validée."
        return f"Analyse terminée. {completed} étapes exécutées et validées."

    @staticmethod
    def _failure_message(steps: list[AgentTurnStep]) -> str:
        failed = next((step for step in steps if step.status == "failed"), None)
        if failed:
            return f"L'exécution s'est arrêtée à l'étape « {failed.label} » : {failed.error or 'erreur inconnue'}"
        return "L'exécution n'a pas pu être terminée."
