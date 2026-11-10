"""llm_client.py 冒烟测试（不消耗 API 额度）。

覆盖：
- 无 Key 时给出明确的 ConfigError
- 非法 base_url 给出 ConfigError
- request_params 的供应商兼容逻辑（temperature / max_tokens 改名）
- _classify 重试分类
- _to_result 对空 choices 抛 ProtocolError

运行：
    python -m pytest tests/test_llm_client.py -v
    python tests/test_llm_client.py      # 无 pytest 时直接运行

    pytest 本质上做了三件事： 发现测试 → 收集测试 → 执行测试 。
    # 规则1：类名以 Test 开头
    # 规则2：方法名以 test_ 开头

"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

# 引入测试对应方法，用于测试异常情况
from shared.llm_client import (
    ConfigError,
    LLMClient,
    LLMConfig,
    ProtocolError,
    _backoff,
    _classify,
    load_config,
    request_params,
)

# ---------------------------------------------------------------------------
# 1. 无 Key → ConfigError
# ---------------------------------------------------------------------------


class TestMissingKey:
    """模拟干净环境（无 .env、无相关环境变量），验证报错信息明确。"""

    def setup_method(self):
        self._saved = {k: v for k, v in os.environ.items()}

    def teardown_method(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def _clean_env(self):
        os.environ.clear()
        for var in list(os.environ):
            if any(k in var for k in ("API_KEY", "BASE_URL", "MODEL", "LLM_PROVIDER")):
                del os.environ[var]

    def test_deepseek_missing_key(self):
        self._clean_env()
        os.environ["LLM_PROVIDER"] = "deepseek"
        with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY"):
            load_config("deepseek")

    def test_moonshot_missing_key(self):
        self._clean_env()
        with pytest.raises(ConfigError, match="MOONSHOT_API_KEY"):
            load_config("moonshot")

    def test_unknown_provider(self):
        self._clean_env()
        with pytest.raises(ConfigError, match="未知 provider"):
            load_config("nonexistent")


# ---------------------------------------------------------------------------
# 2. 非法 base_url → ConfigError
# ---------------------------------------------------------------------------


class TestInvalidBaseUrl:
    def test_not_http(self):
        with pytest.raises(ConfigError, match="base_url"):
            LLMConfig(base_url="ftp://bad", api_key="sk-test", model="m")

    def test_empty_api_key(self):
        with pytest.raises(ConfigError, match="API Key"):
            LLMConfig(base_url="https://ok.com", api_key="", model="m")


# ---------------------------------------------------------------------------
# 3. request_params 供应商兼容
# ---------------------------------------------------------------------------


def _cfg(**kw) -> LLMConfig:
    base = dict(base_url="https://api.test.com", api_key="sk-x", model="m")
    return LLMConfig(**{**base, **kw})


class TestRequestParams:
    def test_default_temperature(self):
        params = request_params(_cfg(), [{"role": "user", "content": "hi"}])
        assert params["temperature"] == 0.3
        assert params["model"] == "m"

    def test_explicit_temperature(self):
        params = request_params(_cfg(), [], temperature=0.9)
        assert params["temperature"] == 0.9

    def test_kimi_drops_temperature(self):
        """Kimi K3.1 Pro 不接受 temperature → 自动丢弃。"""
        cfg = _cfg(supports_temperature=False)
        params = request_params(cfg, [], temperature=0.9)
        assert "temperature" not in params

    def test_kimi_renames_max_tokens(self):
        """Kimi 用 max_completion_tokens → 自动改名。"""
        cfg = _cfg(max_tokens_field="max_completion_tokens")
        params = request_params(cfg, [], max_tokens=500)
        assert params["max_completion_tokens"] == 500
        assert "max_tokens" not in params

    def test_normal_provider_keeps_max_tokens(self):
        params = request_params(_cfg(), [], max_tokens=500)
        assert params["max_tokens"] == 500

    def test_extra_kwargs_pass_through(self):
        params = request_params(_cfg(), [], response_format={"type": "json_object"})
        assert params["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# 4. _classify 重试分类
# ---------------------------------------------------------------------------


class TestClassify:
    def test_retryable_names(self):
        for name in ("APITimeoutError", "APIConnectionError", "InternalServerError", "RateLimitError"):
            exc = type(name, (Exception,), {})()
            assert _classify(exc) is True

    def test_retryable_status_codes(self):
        exc = type("E", (Exception,), {"status_code": 429})()
        assert _classify(exc) is True
        exc = type("E", (Exception,), {"status_code": 500})()
        assert _classify(exc) is True

    def test_non_retryable_status(self):
        exc = type("E", (Exception,), {"status_code": 400})()
        assert _classify(exc) is False

    def test_generic_exception(self):
        assert _classify(ValueError("oops")) is False


# ---------------------------------------------------------------------------
# 5. _to_result 空 choices → ProtocolError
# ---------------------------------------------------------------------------


class TestToResult:
    def test_empty_choices_raises_protocol_error(self):
        client = LLMClient(config=_cfg(), client=MagicMock())
        resp = MagicMock()
        resp.choices = []
        with pytest.raises(ProtocolError, match="choices"):
            client._to_result(resp, 100)

    def test_normal_response(self):
        client = LLMClient(config=_cfg(), client=MagicMock())
        msg = MagicMock(content="hello", tool_calls=None)
        choice = MagicMock(message=msg, finish_reason="stop")
        resp = MagicMock(
            choices=[choice],
            model="m",
            usage=MagicMock(prompt_tokens=10, completion_tokens=5),
        )
        result = client._to_result(resp, 100)
        assert result.content == "hello"
        assert result.usage.prompt_tokens == 10
        assert result.latency_ms == 100


# ---------------------------------------------------------------------------
# 6. _backoff 递增且有上限
# ---------------------------------------------------------------------------


class TestBackoff:
    def test_increasing(self):
        d0, d1, d2 = _backoff(0), _backoff(1), _backoff(2)
        assert d0 < d1 < d2

    def test_capped(self):
        for _ in range(20):
            assert _backoff(10) <= 8.3  # cap 8.0 + 最大抖动 0.3


# ---------------------------------------------------------------------------
# 直接运行（无 pytest 时）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
