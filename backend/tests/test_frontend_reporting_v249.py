from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_v249_frontend_exposes_composable_report_builder():
    page = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "lib" / "api.ts").read_text(encoding="utf-8")
    for token in ["Blocs composables", "addReportBlock", "custom_blocks", "block_order", "validateReport", "report-custom-block"]:
        assert token in page or token in api
    for block_type in ["text", "kpi", "table", "insight", "model", "code", "methodology", "visualization"]:
        assert f"'{block_type}'" in page


def test_v249_report_preview_renders_new_block_types():
    page = (ROOT / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    for block_type in ["text", "kpi", "insight", "model", "code"]:
        assert f"block.type==='{block_type}'" in page
