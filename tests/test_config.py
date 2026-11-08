"""配置层测试：不联网，只验证供应商差异被正确处理。"""

import pytest

from code.shared.llm_client import (
    ConfigError,
    LLMConfig,
    load_config,
    request_params,
)


def test_moonshot_config(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    monkeypatch.delenv("MOONSHOT_MODEL", raising=False)
    monkeypatch.delenv("MOONSHOT_BASE_URL", raising=False)

    cfg = load_config("moonshot")

    assert cfg.provider == "moonshot"
    assert cfg.base_url == "https://api.moonshot.cn/v1"
    assert cfg.model == "kimi-k3.1-pro"
    assert cfg.supports_temperature is False
    assert cfg.max_tokens_field == "max_completion_tokens"


def test_moonshot_model_override(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "sk-test")
    monkeypatch.setenv("MOONSHOT_MODEL", "kimi-k3.1-pro-highspeed")

    assert load_config("moonshot").model == "kimi-k3.1-pro-highspeed"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        load_config("moonshot")


def test_moonshot_request_params_drop_temperature():
    cfg = LLMConfig(
        provider="moonshot",
        base_url="https://api.moonshot.cn/v1",
        api_key="sk-test",
        model="kimi-k3.1-pro",
        supports_temperature=False,
        max_tokens_field="max_completion_tokens",
    )
    params = request_params(cfg, [{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=100)

    assert "temperature" not in params
    assert params["max_completion_tokens"] == 100
    assert "max_tokens" not in params


def test_deepseek_request_params_keep_temperature():
    cfg = LLMConfig(base_url="https://api.deepseek.com", api_key="sk-test", model="deepseek-chat")
    params = request_params(cfg, [{"role": "user", "content": "hi"}], temperature=0.2, max_tokens=100)

    assert params["temperature"] == 0.2
    assert params["max_tokens"] == 100
    assert "max_completion_tokens" not in params
