"""嵌入配置测试：验证 EMBED_* 优先、以及"该厂商没有 embedding"时的明确报错。"""

import pytest

from code.week03.mini_rag.embeddings import (
    EmbedConfigError,
    load_embed_settings,
)


def test_explicit_embed_env(monkeypatch):
    monkeypatch.setenv("EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("EMBED_API_KEY", "sk-embed")
    monkeypatch.setenv("EMBED_MODEL", "qwen3.7-text-embedding")
    monkeypatch.setenv("EMBED_DIMENSIONS", "1024")

    settings = load_embed_settings()
    assert settings.api_key == "sk-embed"
    assert settings.model == "qwen3.7-text-embedding"
    assert settings.dimensions == 1024


def test_default_model_for_dashscope(monkeypatch):
    monkeypatch.setenv("EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setenv("EMBED_API_KEY", "sk-embed")
    monkeypatch.delenv("EMBED_MODEL", raising=False)

    assert load_embed_settings().model == "qwen3.7-text-embedding"


def test_moonshot_without_embed_config_raises(monkeypatch):
    """聊天用 Kimi、又没配 EMBED_* 时，要给出可行动的提示而不是 404。"""
    monkeypatch.delenv("EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "moonshot")
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")

    with pytest.raises(EmbedConfigError, match="EMBED_BASE_URL"):
        load_embed_settings()


def test_fallback_to_supporting_provider(monkeypatch):
    monkeypatch.delenv("EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("EMBED_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = load_embed_settings()
    assert settings.base_url.startswith("https://api.openai.com")
    assert settings.model == "text-embedding-3-small"
