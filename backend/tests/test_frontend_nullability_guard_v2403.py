from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "app" / "page.tsx"
COMPLIANCE = ROOT / "frontend" / "components" / "ComplianceCenter.tsx"
RESPONSIBLE = ROOT / "frontend" / "components" / "ResponsibleAIView.tsx"


def test_connector_form_captures_null_safe_options():
    text = PAGE.read_text(encoding="utf-8")
    assert "const connectorOptions=connectorSpec?.options??[];" in text
    assert "connectorOptions.length>0" in text
    assert "connectorOptions.join(' · ')" in text
    assert "connectorSpec.options??[]" not in text


def test_compliance_center_captures_signoff_list_before_jsx():
    text = COMPLIANCE.read_text(encoding="utf-8")
    assert "const signoffRequired = acceptance?.signoff_required ?? [];" in text
    assert "signoffRequired.map" in text
    assert "acceptance.signoff_required.map" not in text


def test_responsible_ai_async_callbacks_capture_non_null_model():
    text = RESPONSIBLE.read_text(encoding="utf-8")
    assert "const activeModel = model;" in text
    for call in (
        "runModelFairnessAudit(activeModel.model_id",
        "runModelResponsibleAIRisk(activeModel.model_id",
        "runModelResponsibleAIGate(activeModel.model_id",
        "runModelPopulationDrift(activeModel.model_id",
    ):
        assert call in text
    for unsafe in (
        "runModelFairnessAudit(model.model_id",
        "runModelResponsibleAIRisk(model.model_id",
        "runModelResponsibleAIGate(model.model_id",
        "runModelPopulationDrift(model.model_id",
    ):
        assert unsafe not in text
