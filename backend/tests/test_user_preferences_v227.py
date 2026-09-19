from app.core.config import get_settings
from app.services.user_preferences import (
    get_user_preferences,
    save_user_preferences,
)


def _configure(tmp_path, monkeypatch):
    import app.services.metadata_store as metadata_store

    settings = get_settings()
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(
        settings,
        "database_url",
        f"sqlite:///{tmp_path / 'metadata.db'}",
    )
    monkeypatch.setattr(settings, "metadata_fallback_sqlite", True)
    metadata_store._ENGINES.clear()
    metadata_store._SELECTED_BACKENDS.clear()


def test_preferences_are_persisted_and_sanitized(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)

    initial = get_user_preferences("user-1")
    assert initial["preferences"] == {}

    saved = save_user_preferences(
        "user-1",
        {
            "accessibility_mode": "large",
            "ui_zoom": 135,
            "compact_navigation": True,
            "unexpected": "ignored",
        },
    )
    assert saved["preferences"] == {
        "accessibility_mode": "large",
        "ui_zoom": 135,
        "compact_navigation": True,
    }

    loaded = get_user_preferences("user-1")
    assert loaded["preferences"] == saved["preferences"]
    assert loaded["storage"] == "profile"


def test_zoom_is_bounded_server_side(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    high = save_user_preferences("user-2", {"ui_zoom": 999})
    assert high["preferences"]["ui_zoom"] == 140
    low = save_user_preferences("user-2", {"ui_zoom": 1})
    assert low["preferences"]["ui_zoom"] == 90


def test_invalid_mode_is_not_persisted(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    saved = save_user_preferences(
        "user-3",
        {"accessibility_mode": "gigantic", "ui_zoom": 105},
    )
    assert "accessibility_mode" not in saved["preferences"]
    assert saved["preferences"]["ui_zoom"] == 105
