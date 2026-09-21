from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
GLOBAL = (FRONTEND / "app" / "globals.css").read_text(encoding="utf-8")
CSS_FILES = sorted(FRONTEND.rglob("*.css"))


def _font_bases(text: str) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px", text):
        values.append(float(match.group(1)))
    for match in re.finditer(
        r"font-size\s*:\s*calc\(\s*([0-9]+(?:\.[0-9]+)?)px\s*\*\s*var\(--dv-font-scale",
        text,
    ):
        values.append(float(match.group(1)))
    return values


def test_all_platform_stylesheets_are_in_scope():
    expected = {
        "frontend/app/globals.css",
        "frontend/components/ModelRegistryView.module.css",
        "frontend/components/NotebookStudio.module.css",
        "frontend/components/ComplianceCenter.module.css",
        "frontend/components/ResponsibleAIView.module.css",
        "frontend/components/FeatureServingView.module.css",
        "frontend/components/assistant/AIProviderControlCenter.module.css",
        "frontend/components/assistant/FloatingDataVisionAssistant.module.css",
    }
    actual = {str(path.relative_to(ROOT)).replace("\\", "/") for path in CSS_FILES}
    assert expected <= actual


def test_no_explicit_font_base_is_below_12px():
    offenders = []
    for path in CSS_FILES:
        for value in _font_bases(path.read_text(encoding="utf-8")):
            if value < 12:
                offenders.append((str(path.relative_to(ROOT)), value))
    assert offenders == []


def test_reading_modes_have_distinct_scales():
    assert 'html[data-dv-mode="normal"]{--dv-font-scale:1;' in GLOBAL
    assert 'html[data-dv-mode="comfortable"]{--dv-font-scale:1.10;' in GLOBAL
    assert 'html[data-dv-mode="large"]{--dv-font-scale:1.22;' in GLOBAL
    assert '--dv-space-scale:1.06' in GLOBAL
    assert '--dv-space-scale:1.12' in GLOBAL


def test_platform_typography_guardrails_exist():
    assert "v2.53.3 — platform-wide typography and readability baseline" in GLOBAL
    assert "--dv-readable-line-height:1.48" in GLOBAL
    assert "button,input,select,textarea{line-height:1.35}" in GLOBAL
    assert ".table-scroll th,.table-scroll td{padding-top:10px;padding-bottom:10px}" in GLOBAL


def test_model_registry_legacy_microcopy_is_readable():
    css = (FRONTEND / "components" / "ModelRegistryView.module.css").read_text(encoding="utf-8")
    assert "font-size:7px" not in css
    assert "font-size:8px" not in css
    assert "font-size:9px" not in css
    assert ".registryList small" in css
    assert "var(--dv-font-scale" in css


def test_assistant_styles_share_global_scale():
    for rel in (
        "components/assistant/FloatingDataVisionAssistant.module.css",
        "components/assistant/AIProviderControlCenter.module.css",
    ):
        css = (FRONTEND / rel).read_text(encoding="utf-8")
        assert "var(--dv-font-scale" in css
        assert all(v >= 12 for v in _font_bases(css))


def test_large_mode_is_responsive_on_small_screens():
    assert '@media(max-width:780px){html[data-dv-mode="large"]{--dv-font-scale:1.16;' in GLOBAL


def test_display_control_still_exposes_three_modes():
    page = (FRONTEND / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "Normal</button>" in page
    assert "Confort</button>" in page
    assert "Grand texte</button>" in page
    assert "root.dataset.dvMode = uiMode" in page
