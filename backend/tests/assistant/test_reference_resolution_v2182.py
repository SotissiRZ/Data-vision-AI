from app.assistant.memory import SessionMemoryStore
from app.assistant.models import AgentIntent, AssistantContext, SelectedEntity
from app.assistant.reference_resolver import resolve_references


def context_with_schema():
    return AssistantContext(
        activeDatasetId="ds1",
        uiState={
            "datasetSchema": [
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
                {"name": "Country", "dtype": "object"},
            ]
        },
    )


def test_same_as_with_new_column_inherits_visualization():
    store = SessionMemoryStore()
    store.remember_turn(
        "s1",
        intent="visualize",
        entities={"column": "Sales", "x": "Sales"},
        result_summary="Visualisation créée.",
    )
    store.remember_focus_column("s1", "Sales")

    resolved = resolve_references(
        message="fais pareil avec Profit",
        intent=AgentIntent(name="unknown", confidence=0.2),
        context=context_with_schema(),
        memory=store.get_or_create("s1"),
    )

    assert resolved.intent.name == "visualize"
    assert resolved.intent.entities["x"] == "Profit"
    assert resolved.context.selectedEntity.id == "Profit"
    assert resolved.inherited is True


def test_show_this_as_chart_inherits_recent_focus():
    store = SessionMemoryStore()
    store.remember_focus_column("s1", "Profit")

    resolved = resolve_references(
        message="montre-moi ça en graphique",
        intent=AgentIntent(name="visualize", confidence=0.88),
        context=context_with_schema(),
        memory=store.get_or_create("s1"),
    )

    assert resolved.intent.name == "visualize"
    assert resolved.intent.entities["x"] == "Profit"
    assert resolved.context.selectedEntity.id == "Profit"


def test_why_followup_becomes_explain_previous():
    store = SessionMemoryStore()
    store.remember_turn(
        "s1",
        intent="dataset_assessment",
        entities={},
        result_summary="La qualité est bonne avec un score de 80/100.",
    )

    resolved = resolve_references(
        message="et pourquoi ?",
        intent=AgentIntent(name="unknown", confidence=0.2),
        context=context_with_schema(),
        memory=store.get_or_create("s1"),
    )

    assert resolved.intent.name == "explain_previous"
    assert resolved.inherited is True


def test_compare_with_other_is_not_guessed_without_two_columns():
    store = SessionMemoryStore()
    store.remember_focus_column("s1", "Sales")

    resolved = resolve_references(
        message="compare-le avec l'autre",
        intent=AgentIntent(name="unknown", confidence=0.2),
        context=context_with_schema(),
        memory=store.get_or_create("s1"),
    )

    assert resolved.clarification is not None
    assert "deuxième variable" in resolved.clarification


def test_compare_with_other_uses_two_recent_known_columns():
    store = SessionMemoryStore()
    store.remember_focus_column("s1", "Sales")
    store.remember_focus_column("s1", "Profit")

    resolved = resolve_references(
        message="compare-le avec l'autre",
        intent=AgentIntent(name="unknown", confidence=0.2),
        context=context_with_schema(),
        memory=store.get_or_create("s1"),
    )

    assert resolved.clarification is None
    assert resolved.intent.name == "visualize"
    assert resolved.intent.entities["x"] == "Profit"
    assert resolved.intent.entities["y"] == "Sales"
