import pytest


@pytest.fixture(autouse=True)
def disable_real_llm_calls(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

