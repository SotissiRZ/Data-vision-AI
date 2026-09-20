from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend" / "app" / "page.tsx"
API = ROOT / "frontend" / "lib" / "api.ts"


def test_preparation_studio_exposes_v242_feature_engineering():
    text = PAGE.read_text(encoding="utf-8")
    for operation in ("bin_numeric", "lag_feature", "rolling_feature"):
        assert operation in text
    assert "Variables à agréger" in text
    assert "selected2.length?selected2:[column]" in text


def test_multikey_join_is_sent_as_arrays():
    text = PAGE.read_text(encoding="utf-8")
    assert ".split(',').map((x:string)=>x.trim()).filter(Boolean)" in text
    assert "left_on:leftKeys,right_on:rightKeys" in text
    assert "même nombre de colonnes" in text.lower()


def test_saved_pipeline_can_validate_and_bind_dependencies():
    page = PAGE.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    assert "validateSavedPipeline" in page
    assert "pipelineBindings" in page
    assert "p.multi_dataset?'multi-dataset · ':''" in page
    assert "export async function validatePipeline" in api
    assert "body: JSON.stringify({ bindings })" in api
