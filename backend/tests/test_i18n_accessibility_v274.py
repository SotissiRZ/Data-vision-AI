from pathlib import Path
import re

from app.core.config import get_settings
from app.services.user_preferences import get_user_preferences, save_user_preferences

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PAGE = (FRONTEND / "app" / "page.tsx").read_text(encoding="utf-8")
CSS = (FRONTEND / "app" / "globals.css").read_text(encoding="utf-8")
I18N = (FRONTEND / "lib" / "i18n.ts").read_text(encoding="utf-8")
API = (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")


def _configure(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'metadata.db'}")
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def _dictionary_keys(name: str) -> set[str]:
    match = re.search(rf"const {name}: Record<string,string> = \{{(.*?)\n\}};", I18N, re.S)
    assert match, name
    return set(re.findall(r"'([^']+)'\s*:", match.group(1)))


def test_four_locales_have_complete_shell_catalogs():
    assert "export type Locale = 'fr' | 'en' | 'es' | 'ar'" in I18N
    french = _dictionary_keys("fr")
    assert len(french) >= 90
    for locale in ("en", "es", "ar"):
        assert _dictionary_keys(locale) == french
    assert "locale==='ar'?'rtl':'ltr'" not in I18N  # direction is catalog-driven, not hard-coded in page
    assert "dir:'rtl'" in I18N


def test_user_preferences_persist_locale_and_accessibility_flags(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    saved = save_user_preferences(
        "v274-user",
        {
            "locale": "ar",
            "high_contrast": True,
            "reduce_motion": True,
            "accessibility_mode": "large",
            "ui_zoom": 125,
        },
    )
    assert saved["preferences"] == {
        "accessibility_mode": "large",
        "ui_zoom": 125,
        "locale": "ar",
        "high_contrast": True,
        "reduce_motion": True,
    }
    assert get_user_preferences("v274-user")["preferences"]["locale"] == "ar"


def test_invalid_locale_is_rejected_server_side(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    saved = save_user_preferences("v274-invalid", {"locale": "xx", "high_contrast": False})
    assert "locale" not in saved["preferences"]
    assert saved["preferences"]["high_contrast"] is False


def test_preferences_api_contract_includes_i18n_and_accessibility():
    routes = (ROOT / "backend/app/api/routes/enterprise.py").read_text(encoding="utf-8")
    assert 'pattern="^(fr|en|es|ar)$"' in routes
    assert "high_contrast: bool | None" in routes
    assert "reduce_motion: bool | None" in routes
    assert "locale?:'fr'|'en'|'es'|'ar'" in API
    assert "high_contrast?:boolean" in API and "reduce_motion?:boolean" in API


def test_document_language_direction_and_profile_sync_are_applied():
    assert "root.lang=locale" in PAGE
    assert "root.dir=localeDirection(locale)" in PAGE
    assert "localStorage.setItem('dv_locale', locale)" in PAGE
    assert "saveEnterprisePreferences(token,{accessibility_mode:uiMode,ui_zoom:uiZoom,locale,high_contrast:highContrast,reduce_motion:reduceMotion})" in PAGE
    assert "if(isLocale(preferredLocale))setLocale(preferredLocale)" in PAGE


def test_keyboard_and_screen_reader_landmarks_exist():
    assert 'className="skip-link" href="#main-content"' in PAGE
    assert 'role="status" aria-live="polite" aria-atomic="true"' in PAGE
    assert 'id="main-content" ref={mainContentRef} tabIndex={-1}' in PAGE
    assert "mainContentRef.current?.focus({preventScroll:true})" in PAGE
    assert 'aria-label={tr(\'a11y.primaryNavigation\')}' in PAGE
    assert 'aria-label={tr(\'a11y.contextNavigation\')}' in PAGE
    assert 'role="alert"' in PAGE
    assert 'aria-keyshortcuts="Control+K Meta+K"' in PAGE


def test_display_controls_expose_accessibility_states_semantically():
    assert "aria-expanded={displayToolsOpen}" in PAGE
    assert 'role="dialog" aria-label={tr(\'display.title\')}' in PAGE
    assert "aria-pressed={uiMode==='normal'}" in PAGE
    assert 'type="checkbox" checked={highContrast}' in PAGE
    assert 'type="checkbox" checked={reduceMotion}' in PAGE
    assert "LOCALES.map" in PAGE


def test_css_contains_focus_contrast_motion_and_rtl_guardrails():
    assert ".skip-link:focus{transform:translateY(0)}" in CSS
    assert ":where(button,a,input,select,textarea,[tabindex]):focus-visible" in CSS
    assert 'html[data-dv-contrast="high"]' in CSS
    assert 'html[data-dv-motion="reduced"]' in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS
    assert 'html[dir="rtl"] .area-item' in CSS
