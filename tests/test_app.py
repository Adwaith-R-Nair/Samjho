import pytest
from fastapi.testclient import TestClient

from app.main import app

KEYS = [
    "SARVAM_API_KEY",
    "GOOGLE_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
    "PUBLIC_BASE_URL",
    "JUDGE_TOKEN",
    "CALLS_ENABLED",
]


@pytest.fixture
def no_keys(monkeypatch):
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)


def test_health_and_main_screen_without_keys(no_keys):
    client = TestClient(app)
    assert client.get("/healthz").json() == {"ok": True}
    page = client.get("/")
    assert page.status_code == 200
    assert "Samjho" in page.text
    assert client.get("/static/app.js").status_code == 200


def test_status_names_missing_keys_and_keeps_text_and_replay_on(no_keys):
    status = TestClient(app).get("/api/status").json()
    assert status["voice"] == {"ready": False, "reason": "SARVAM_API_KEY not set"}
    assert status["phone"]["ready"] is False
    assert status["text"]["ready"] is True
    assert status["replay"]["ready"] is True


def test_status_never_echoes_a_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_secret_value_123")
    body = TestClient(app).get("/api/status").text
    assert "sk_secret_value_123" not in body
    assert '"voice":{"ready":true' in body.replace(" ", "")
