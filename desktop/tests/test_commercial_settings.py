import os

from backend.services import settings


def test_commercial_preferences_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETAI_DATA_DIR", str(tmp_path))
    saved = settings.save_preferences({
        "default_origin_country": "FR",
        "default_destination_country": "BR",
        "default_margin_percent": 27.5,
        "first_run_completed": True,
    })
    assert saved["default_origin_country"] == "FR"
    assert saved["default_margin_percent"] == 27.5
    assert settings.load_preferences()["first_run_completed"] is True


def test_secret_storage_never_returns_plain_value(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETAI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MARKETAI_ENV_PATH", raising=False)
    secret = "super-secret-marketai-test"
    presence = settings.save_secrets({"SERPAPI_KEY": secret})
    assert presence["SERPAPI_KEY"] is True
    raw = settings.secrets_path().read_bytes()
    assert secret.encode() not in raw
    assert settings.load_secrets()["SERPAPI_KEY"] == secret


def test_clear_secret_removes_runtime_value(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETAI_DATA_DIR", str(tmp_path))
    settings.save_secrets({"OPENAI_API_KEY": "abc123"})
    assert os.getenv("OPENAI_API_KEY") == "abc123"
    settings.save_secrets({}, ["OPENAI_API_KEY"])
    assert os.getenv("OPENAI_API_KEY") is None
    assert settings.secret_presence()["OPENAI_API_KEY"] is False
