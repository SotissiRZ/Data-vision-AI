from app.assistant.intent import resolve_intent
from app.assistant.models import AssistantContext


def test_predict_intent():
    intent = resolve_intent(
        "Je veux faire une classification et prédire la cible churn",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "predict_target"
    assert intent.entities["target"] == "churn"


def test_gis_intent():
    intent = resolve_intent(
        "Fais une analyse SIG avec cette couche",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "geospatial_analysis"


def test_greeting_is_conversation():
    intent = resolve_intent("Bonjour", AssistantContext())
    assert intent.name == "conversation"


def test_unknown_without_context():
    intent = resolve_intent(
        "Pourquoi le ciel est bleu ?",
        AssistantContext(),
    )
    assert intent.name == "unknown"


def test_predict_without_task_does_not_invent_task():
    intent = resolve_intent(
        "Je veux prédire la cible revenu",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "predict_target"
    assert intent.entities["target"] == "revenu"
    assert "ml_task" not in intent.entities
