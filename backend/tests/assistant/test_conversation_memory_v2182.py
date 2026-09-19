from app.assistant.host_bridge import (
    DataVisionHostBridges,
    bind_registry_to_host,
)
from app.assistant.models import AgentTurnRequest, AssistantContext, SelectedEntity
from app.assistant.runtime import build_orchestrator
from app.assistant.tools import build_default_registry


class FakeVisualizationBridge:
    def create_visualization(self, *, context, chart_type, x=None, y=None, **kwargs):
        return {
            "status": "ok",
            "chart_type": chart_type,
            "x": x,
            "y": y,
            "chart_id": f"chart-{x}-{y or 'single'}",
        }

    def diagnose_visualization(self, *, context, **kwargs):
        return {"status": "ok"}


def runtime():
    registry = build_default_registry()
    bind_registry_to_host(
        registry,
        DataVisionHostBridges(
            visualization=FakeVisualizationBridge(),
        ),
    )
    return build_orchestrator(registry=registry)


def ctx(selected=None):
    return AssistantContext(
        activeDatasetId="ds1",
        selectedEntity=(
            SelectedEntity(type="column", id=selected, label=selected)
            if selected
            else None
        ),
        uiState={
            "datasetSchema": [
                {"name": "Sales", "dtype": "float64"},
                {"name": "Profit", "dtype": "float64"},
                {"name": "Country", "dtype": "object"},
            ],
            "datasetName": "Financial Sample.xlsx",
            "rowCount": 700,
            "columnCount": 8,
            "missingCells": 0,
            "duplicateCount": 0,
            "qualityScore": 80,
        },
    )


def test_visual_followup_reuses_previous_operation_with_new_column():
    orchestrator = runtime()

    first = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="fais un graphique de Sales",
            context=ctx("Sales"),
        )
    )
    assert first.status == "completed"
    assert first.steps[0].args["x"] == "Sales"

    second = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="fais pareil avec Profit",
            context=ctx(),
        )
    )
    assert second.status == "completed"
    assert second.intent.name == "visualize"
    assert second.steps[0].args["x"] == "Profit"


def test_show_this_as_chart_uses_recent_focus():
    orchestrator = runtime()

    first = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="fais un graphique de Sales",
            context=ctx("Sales"),
        )
    )
    assert first.status == "completed"

    second = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="montre-moi ça en graphique",
            context=ctx(),
        )
    )
    assert second.status == "completed"
    assert second.steps[0].args["x"] == "Sales"


def test_why_after_dataset_assessment_uses_previous_answer():
    orchestrator = runtime()

    assessment = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="comment tu trouves le dataset ?",
            context=ctx(),
        )
    )
    assert assessment.status == "completed"
    assert "80/100" in assessment.message

    followup = orchestrator.run_turn(
        AgentTurnRequest(
            session_id="s1",
            message="et pourquoi ?",
            context=ctx(),
        )
    )
    assert followup.status == "completed"
    assert followup.intent.name == "explain_previous"
    assert "faits déjà calculés" in followup.message
    assert "80/100" in followup.message
