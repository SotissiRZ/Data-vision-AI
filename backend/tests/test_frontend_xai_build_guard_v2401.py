from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "app" / "page.tsx"


def test_xai_callbacks_capture_non_null_model_reference():
    text = PAGE.read_text(encoding="utf-8")
    assert "const activeModel=model;" in text
    assert "if(activeModel.task==='regression')" in text
    assert "runModelCounterfactuals(activeModel.model_id" in text
    assert "if(model.task==='regression')" not in text
