from app.assistant.models import AssistantContext, AssistantEvent, SelectedEntity
from app.assistant.privacy import AIDataPolicy, project_context_for_model


def test_external_projection_hides_column_name_when_disabled():
    context = AssistantContext(
        activeDatasetId="ds1",
        selectedEntity=SelectedEntity(
            type="column",
            id="salary",
            label="Salary",
        ),
        recentEvents=[
            AssistantEvent(type="dataset.loaded"),
            AssistantEvent(type="column.selected"),
        ],
    )

    projected = project_context_for_model(
        context,
        external=True,
        policy=AIDataPolicy(
            allow_external_ai=True,
            include_column_names_external=False,
        ),
    )

    assert projected["selected_entity"]["id"] is None
    assert projected["selected_entity"]["label"] is None


def test_projection_never_contains_row_data_or_ui_state():
    context = AssistantContext(
        uiState={"rows": [{"secret": 123}]},
        activeDatasetId="ds1",
    )

    projected = project_context_for_model(
        context,
        external=False,
        policy=AIDataPolicy(),
    )

    assert "uiState" not in projected
    assert "rows" not in projected
