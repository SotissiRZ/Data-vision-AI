from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_assistant_window_has_three_size_presets_and_manual_resize_handle():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    assert 'COMPACT_ASSISTANT_WINDOW_SIZE' in component
    assert 'DEFAULT_ASSISTANT_WINDOW_SIZE' in component
    assert 'LARGE_ASSISTANT_WINDOW_SIZE' in component
    assert 'aria-label="Réduire la fenêtre"' in component
    assert 'aria-label="Rétablir la taille normale"' in component
    assert 'aria-label="Agrandir la fenêtre"' in component
    assert 'onPointerDown={beginAssistantWindowResize}' in component
    assert 'aria-label="Redimensionner la fenêtre de l’assistant"' in component


def test_assistant_window_size_is_clamped_and_persisted():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    assert 'ASSISTANT_WINDOW_STORAGE_KEY = "datavision.assistant.window.size"' in component
    assert 'MIN_ASSISTANT_WIDTH = 340' in component
    assert 'MIN_ASSISTANT_HEIGHT = 420' in component
    assert 'MAX_ASSISTANT_WIDTH = 960' in component
    assert 'MAX_ASSISTANT_HEIGHT = 980' in component
    assert 'window.localStorage.getItem(ASSISTANT_WINDOW_STORAGE_KEY)' in component
    assert 'window.localStorage.setItem(ASSISTANT_WINDOW_STORAGE_KEY' in component
    assert 'window.addEventListener("resize", keepInsideViewport)' in component


def test_manual_resize_grows_from_top_left_for_bottom_right_anchored_panel():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    assert 'width: start.width + (startX - moveEvent.clientX)' in component
    assert 'height: start.height + (startY - moveEvent.clientY)' in component
    assert 'window.addEventListener("pointermove", onPointerMove)' in component
    assert 'window.addEventListener("pointerup", finishResize' in component
    assert 'window.addEventListener("pointercancel", finishResize' in component


def test_responsive_css_keeps_resized_panel_inside_viewport():
    css = read("frontend/components/assistant/FloatingDataVisionAssistant.module.css")
    assert 'max-width: calc(100vw - 32px)' in css
    assert 'max-height: calc(100vh - 112px)' in css
    assert 'touch-action: none' in css
    assert 'cursor: nwse-resize' in css
    assert '@container (max-width: 430px)' in css
    assert 'max-width: calc(100vw - 16px)' in css


def test_panel_uses_dynamic_inline_dimensions_and_compact_content_reflow():
    component = read("frontend/components/assistant/FloatingDataVisionAssistant.tsx")
    css = read("frontend/components/assistant/FloatingDataVisionAssistant.module.css")
    assert 'style={{ width: assistantWindowSize.width, height: assistantWindowSize.height }}' in component
    assert 'container-type: inline-size' in css
    assert '.logo,' in css and '.status {' in css and 'display: none' in css


def test_resize_animation_is_disabled_during_drag_and_reduced_motion():
    css = read("frontend/components/assistant/FloatingDataVisionAssistant.module.css")
    assert '.panelResizing' in css
    assert 'transition: none' in css
    assert '@media (prefers-reduced-motion: reduce)' in css
