from __future__ import annotations

from uuid import uuid4

from app.assistant.conversation import ConversationalResponder
from app.assistant.memory import SessionMemoryStore
from app.assistant.models import AgentIntent, AssistantContext, SelectedEntity
from app.assistant.persistent_memory import PersistentSessionMemoryStore
from app.assistant.reference_resolver import resolve_references
from app.assistant.turn_runs import AgentTurnRunStore
from app.services import metadata_store


def _context(dataset_id: str = "ds1", selected: str | None = None):
    return AssistantContext(
        workspaceId="ws1",
        activeDatasetId=dataset_id,
        activeDatasetVersionId="3",
        screen="quality",
        selectedEntity=(
            SelectedEntity(type="column", id=selected, label=selected)
            if selected
            else None
        ),
        uiState={
            "datasetName": f"{dataset_id}.csv",
            "datasetVersion": 3,
            "rowCount": 700,
            "columnCount": 3,
            "qualityScore": 92,
            "datasetSchema": [
                {"name": "Date", "dtype": "object"},
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
            ],
            "temporalCoverage": {
                "detected": True,
                "primary": {
                    "column": "Date",
                    "kind": "datetime_text",
                    "start": "2021-01-01T00:00:00+00:00",
                    "end": "2025-06-30T00:00:00+00:00",
                },
                "columns": [],
            },
        },
    )


def test_dataset_context_elliptical_period_followup_is_resolved():
    memory = SessionMemoryStore()
    memory.remember_turn(
        "s1",
        intent="dataset_context",
        entities={"dataset_id": "ds1"},
        result_summary="Le dataset actif est ds1.csv.",
    )
    context = _context()
    resolution = resolve_references(
        message="et sa période ?",
        intent=AgentIntent(name="unknown", confidence=0.2),
        context=context,
        memory=memory.get_or_create("s1"),
    )
    assert resolution.intent.name == "dataset_context"
    assert resolution.inherited is True

    response = ConversationalResponder(
        AgentTurnRunStore(), memory
    ).respond(
        session_id="s1",
        message="et sa période ?",
        intent=resolution.intent,
        context=resolution.context,
    )
    assert response is not None
    assert "2021-01-01" in response.message
    assert "2025-06-30" in response.message


def test_compare_with_named_column_reuses_recent_focus():
    memory = SessionMemoryStore()
    memory.remember_focus_column("s1", "Sales")
    resolution = resolve_references(
        message="compare avec Profit",
        intent=AgentIntent(name="unknown", confidence=0.2),
        context=_context(),
        memory=memory.get_or_create("s1"),
    )
    assert resolution.intent.name == "visualize"
    assert resolution.intent.entities["x"] == "Sales"
    assert resolution.intent.entities["y"] == "Profit"
    assert resolution.inherited is True


def test_persistent_memory_reloads_compact_semantic_state(monkeypatch):
    rows: dict[str, dict] = {}

    def fake_fetch_one(_sql, params=None):
        return rows.get((params or {}).get("session_id"))

    def fake_execute(_sql, params=None):
        payload = dict(params or {})
        sid = payload.get("session_id")
        if sid:
            rows[sid] = payload

    monkeypatch.setattr(metadata_store, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(metadata_store, "execute", fake_execute)

    session_id = f"test-{uuid4()}"
    first = PersistentSessionMemoryStore()
    first.sync_context(session_id, _context(selected="Sales"))
    first.remember_turn(
        session_id,
        intent="visualize",
        entities={"x": "Sales"},
        result_summary="Graphique Sales créé.",
    )

    second = PersistentSessionMemoryStore()
    restored = second.get_or_create(session_id, "ws1")
    assert restored.last_intent == "visualize"
    assert restored.last_result_summary == "Graphique Sales créé."
    assert restored.recent_columns[0] == "Sales"
    assert restored.facts["active_dataset_id"] == "ds1"


def test_dataset_switch_clears_dataset_specific_followup_memory(monkeypatch):
    rows: dict[str, dict] = {}

    def fake_fetch_one(_sql, params=None):
        return rows.get((params or {}).get("session_id"))

    def fake_execute(_sql, params=None):
        payload = dict(params or {})
        sid = payload.get("session_id")
        if sid:
            rows[sid] = payload

    monkeypatch.setattr(metadata_store, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(metadata_store, "execute", fake_execute)

    store = PersistentSessionMemoryStore()
    store.sync_context("s-switch", _context("ds1", selected="Sales"))
    store.remember_turn(
        "s-switch",
        intent="visualize",
        entities={"x": "Sales"},
        result_summary="Graphique Sales créé.",
    )
    switched = store.sync_context("s-switch", _context("ds2"))

    assert switched.facts["active_dataset_id"] == "ds2"
    assert switched.last_intent is None
    assert switched.last_result_summary is None
    assert switched.recent_columns == []
    assert "column" not in switched.active_entities


def test_metadata_schema_contains_assistant_session_memory_table():
    assert any(
        "assistant_session_memory" in ddl
        for ddl in metadata_store.SCHEMA_SQL
    )
