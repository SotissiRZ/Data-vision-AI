import pandas as pd

from app.assistant.conversation import ConversationalResponder
from app.assistant.intent import resolve_intent
from app.assistant.memory import SessionMemoryStore
from app.assistant.models import AgentIntent, AssistantContext
from app.assistant.turn_runs import AgentTurnRunStore
from app.services.profiling import profile_dataframe


def _responder():
    return ConversationalResponder(AgentTurnRunStore(), SessionMemoryStore())


def test_period_question_routes_to_dataset_context():
    intent = resolve_intent(
        "à quelle période remonte ce dataset ?",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "dataset_context"


def test_profile_detects_string_date_range():
    df = pd.DataFrame({
        "Date": ["2021-01-03", "2022-05-06", "2023-12-31"],
        "Sales": [10, 20, 30],
    })
    profile = profile_dataframe(df)
    temporal = profile["temporal"]
    assert temporal["detected"] is True
    assert temporal["primary"]["column"] == "Date"
    assert temporal["primary"]["start"].startswith("2021-01-03")
    assert temporal["primary"]["end"].startswith("2023-12-31")


def test_dataset_period_answer_uses_context_without_llm():
    intent = AgentIntent(name="dataset_context", confidence=0.99)
    context = AssistantContext(
        activeDatasetId="ds1",
        activeDatasetVersionId="3",
        uiState={
            "datasetName": "ventes.xlsx",
            "datasetVersion": 3,
            "rowCount": 300,
            "columnCount": 8,
            "datasetSchema": [{"name": "Date", "dtype": "object"}],
            "temporalCoverage": {
                "detected": True,
                "primary": {
                    "column": "Date",
                    "kind": "datetime_text",
                    "start": "2020-01-01T00:00:00+00:00",
                    "end": "2024-12-31T00:00:00+00:00",
                    "confidence": 0.98,
                },
                "columns": [],
            },
        },
    )
    response = _responder().respond(
        session_id="s1",
        message="à quelle période remonte ce dataset ?",
        intent=intent,
        context=context,
    )
    assert response is not None
    assert response.status == "completed"
    assert "2020-01-01" in response.message
    assert "2024-12-31" in response.message
    assert "Date" in response.message


def test_dataset_rows_answer_uses_context_without_tools():
    intent = resolve_intent(
        "combien de lignes contient ce dataset ?",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "dataset_context"
    response = _responder().respond(
        session_id="s2",
        message="combien de lignes contient ce dataset ?",
        intent=intent,
        context=AssistantContext(
            activeDatasetId="ds1",
            uiState={"datasetName": "sample.csv", "rowCount": 700},
        ),
    )
    assert response is not None
    assert "700 lignes" in response.message


def test_arbitrary_question_stays_unknown_even_with_dataset():
    intent = resolve_intent(
        "Pourquoi le ciel est bleu ?",
        AssistantContext(activeDatasetId="ds1"),
    )
    assert intent.name == "unknown"
