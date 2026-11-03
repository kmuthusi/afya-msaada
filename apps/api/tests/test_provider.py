import pytest

from apps.api.afya.models.provider import chat_json


def test_hosted_provider_requires_explicit_model_and_key(monkeypatch):
    monkeypatch.setenv("AFYA_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        chat_json("Return JSON", "hello")


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("AFYA_LLM_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="Unsupported"):
        chat_json("Return JSON", "hello")
