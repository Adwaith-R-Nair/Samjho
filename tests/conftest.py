import pytest


@pytest.fixture(autouse=True)
def no_network_llm(monkeypatch):
    """Tests never call Gemini, even if a developer's .env has a key."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
