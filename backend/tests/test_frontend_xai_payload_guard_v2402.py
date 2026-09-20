from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "app" / "page.tsx"


def test_counterfactual_payload_uses_api_contract_type():
    text = PAGE.read_text(encoding="utf-8")
    assert "const row=JSON.parse(rowText) as Record<string, unknown>" in text
    assert "const payload:Parameters<typeof runModelCounterfactuals>[1]" in text
    assert "const payload:AnyObj={row,max_changes:2,max_results:5}" not in text
    assert "runModelCounterfactuals(activeModel.model_id,payload)" in text
