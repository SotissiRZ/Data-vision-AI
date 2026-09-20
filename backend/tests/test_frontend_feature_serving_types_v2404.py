from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURE_SERVING = ROOT / "frontend" / "components" / "FeatureServingView.tsx"


def test_feature_store_column_names_are_strictly_typed():
    text = FEATURE_SERVING.read_text(encoding="utf-8")
    assert "const columns: AnyObj[]" in text
    assert "const columnNames: string[]" in text
    assert text.count("columnNames.map((name: string) =>") == 3
    assert "columnNames.map(name =>" not in text
