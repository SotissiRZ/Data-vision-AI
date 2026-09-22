from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services import metadata_store

from .memory import SessionMemory, SessionMemoryStore
from .models import AssistantContext


class PersistentSessionMemoryStore(SessionMemoryStore):
    """
    Compact persistent working memory for the conversational assistant.

    Only semantic state is persisted: active dataset/model references, recent
    columns, recent intents, entities and the latest deterministic result
    summary. Raw chat transcripts and the current user objective are not
    persisted here.
    """

    def _load_from_metadata(
        self,
        session_id: str,
        workspace_id: str | None = None,
    ) -> SessionMemory | None:
        row = metadata_store.fetch_one(
            """
            SELECT session_id, workspace_id, active_entities_json, facts_json,
                   decisions_json, last_intent, last_entities_json,
                   recent_columns_json, recent_intents_json,
                   last_result_summary, updated_at
            FROM assistant_session_memory
            WHERE session_id = :session_id
            """,
            {"session_id": session_id},
        )
        if row is None:
            return None
        stored_workspace = row.get("workspace_id")
        if workspace_id is not None and stored_workspace not in {None, workspace_id}:
            # A browser session must never inherit semantic state from another
            # tenant/workspace.
            return None
        return SessionMemory(
            session_id=session_id,
            workspace_id=workspace_id or stored_workspace,
            active_entities=metadata_store.json_loads(row.get("active_entities_json"), {}) or {},
            facts=metadata_store.json_loads(row.get("facts_json"), {}) or {},
            decisions=metadata_store.json_loads(row.get("decisions_json"), []) or [],
            last_intent=row.get("last_intent"),
            last_entities=metadata_store.json_loads(row.get("last_entities_json"), {}) or {},
            recent_columns=metadata_store.json_loads(row.get("recent_columns_json"), []) or [],
            recent_intents=metadata_store.json_loads(row.get("recent_intents_json"), []) or [],
            last_result_summary=row.get("last_result_summary"),
            updated_at=_parse_dt(row.get("updated_at")),
        )

    def _persist(self, item: SessionMemory) -> None:
        now = datetime.now(timezone.utc).isoformat()
        params: dict[str, Any] = {
            "session_id": item.session_id,
            "workspace_id": item.workspace_id,
            "active_entities_json": metadata_store.json_dumps(item.active_entities),
            "facts_json": metadata_store.json_dumps(item.facts),
            "decisions_json": metadata_store.json_dumps(item.decisions[-30:]),
            "last_intent": item.last_intent,
            "last_entities_json": metadata_store.json_dumps(item.last_entities),
            "recent_columns_json": metadata_store.json_dumps(item.recent_columns[:8]),
            "recent_intents_json": metadata_store.json_dumps(item.recent_intents[:10]),
            "last_result_summary": item.last_result_summary,
            "updated_at": now,
        }
        metadata_store.execute(
            """
            INSERT INTO assistant_session_memory (
                session_id, workspace_id, active_entities_json, facts_json,
                decisions_json, last_intent, last_entities_json,
                recent_columns_json, recent_intents_json,
                last_result_summary, created_at, updated_at
            ) VALUES (
                :session_id, :workspace_id, :active_entities_json, :facts_json,
                :decisions_json, :last_intent, :last_entities_json,
                :recent_columns_json, :recent_intents_json,
                :last_result_summary, :updated_at, :updated_at
            )
            ON CONFLICT(session_id) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                active_entities_json = excluded.active_entities_json,
                facts_json = excluded.facts_json,
                decisions_json = excluded.decisions_json,
                last_intent = excluded.last_intent,
                last_entities_json = excluded.last_entities_json,
                recent_columns_json = excluded.recent_columns_json,
                recent_intents_json = excluded.recent_intents_json,
                last_result_summary = excluded.last_result_summary,
                updated_at = excluded.updated_at
            """,
            params,
        )

    def get_or_create(
        self,
        session_id: str,
        workspace_id: str | None = None,
    ) -> SessionMemory:
        with self._lock:
            item = self._items.get(session_id)
            if item is None:
                try:
                    item = self._load_from_metadata(session_id, workspace_id)
                except Exception:
                    # Metadata availability must not make the assistant unusable.
                    item = None
                if item is not None:
                    self._items[session_id] = item
            item = super().get_or_create(session_id, workspace_id)
            return item

    def sync_context(
        self,
        session_id: str,
        context: AssistantContext,
    ) -> SessionMemory:
        with self._lock:
            item = self.get_or_create(session_id, context.workspaceId)
            previous_dataset = item.facts.get("active_dataset_id")
            current_dataset = context.activeDatasetId

            if previous_dataset and current_dataset and previous_dataset != current_dataset:
                # Prevent cross-dataset pronoun/follow-up leakage.
                item.last_intent = None
                item.last_entities = {}
                item.recent_columns = []
                item.recent_intents = []
                item.last_result_summary = None
                item.facts.pop("recent_artifacts", None)
                item.facts.pop("last_project_recall", None)
                item.active_entities.pop("column", None)

            item.facts["active_dataset_id"] = current_dataset
            item.facts["active_dataset_version_id"] = context.activeDatasetVersionId
            item.facts["active_model_id"] = context.activeModelId
            item.facts["screen"] = context.screen or context.route
            if context.uiState:
                for key in (
                    "areaKey",
                    "areaLabel",
                    "workspaceName",
                    "workspaceRole",
                    "datasetName",
                    "datasetVersion",
                    "datasetCreatedAt",
                    "rowCount",
                    "columnCount",
                    "duplicateCount",
                    "missingCells",
                    "qualityScore",
                    "qualityIssuesCount",
                    "numericColumnCount",
                    "categoricalColumnCount",
                    "temporalCoverage",
                    "accessMode",
                    "accessGoverned",
                    "accessRole",
                    "accessPolicyCount",
                    "target",
                    "algorithm",
                    "modelTask",
                    "modelAlgorithm",
                    "modelPrimaryMetric",
                    "modelFeatureCount",
                    "trustScore",
                    "trustGrade",
                ):
                    if key in context.uiState:
                        item.facts[key] = context.uiState.get(key)
            if context.selectedEntity and context.selectedEntity.id:
                item.active_entities[context.selectedEntity.type] = context.selectedEntity.id
                if context.selectedEntity.type in {"column", "variable"}:
                    self.remember_focus_column(session_id, context.selectedEntity.id)
                    item = self.get_or_create(session_id, context.workspaceId)
            item.updated_at = datetime.now(timezone.utc)
            try:
                self._persist(item)
            except Exception:
                pass
            return item

    def set_objective(self, session_id: str, objective: str) -> SessionMemory:
        item = super().set_objective(session_id, objective)
        # Raw user objective stays in process memory only by design.
        return item

    def remember_fact(self, session_id: str, key: str, value: Any) -> SessionMemory:
        item = super().remember_fact(session_id, key, value)
        try:
            self._persist(item)
        except Exception:
            pass
        return item

    def remember_focus_column(self, session_id: str, column: str | None) -> SessionMemory:
        item = super().remember_focus_column(session_id, column)
        try:
            self._persist(item)
        except Exception:
            pass
        return item

    def remember_turn(
        self,
        session_id: str,
        *,
        intent: str,
        entities: dict[str, Any] | None = None,
        result_summary: str | None = None,
    ) -> SessionMemory:
        item = super().remember_turn(
            session_id,
            intent=intent,
            entities=entities,
            result_summary=result_summary,
        )
        try:
            self._persist(item)
        except Exception:
            pass
        return item

    def record_decision(
        self,
        session_id: str,
        *,
        action: str,
        result: str,
        reversible: bool,
    ) -> SessionMemory:
        item = super().record_decision(
            session_id,
            action=action,
            result=result,
            reversible=reversible,
        )
        try:
            self._persist(item)
        except Exception:
            pass
        return item


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except Exception:
            pass
    return datetime.now(timezone.utc)
