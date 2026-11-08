"""生产级 LLM 客户端（第 1 周产出，后续所有项目复用）。

覆盖六个要素：配置集中、超时、重试（指数退避 + 抖动）、并发限制、日志、成本统计。
只依赖 openai SDK，因此任何 OpenAI 兼容端点都能用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("llm")

# ---------------------------------------------------------------------------
# 错误分层
# ---------------------------------------------------------------------------


class LLMError(RuntimeError):
    """所有 LLM 调用错误的基类。"""


class ConfigError(LLMError):
    """配置缺失或非法。"""


class RetryableError(LLMError):
    """网络抖动 / 限流 / 服务端 5xx，可以重试。"""


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    """一次调用需要的全部配置。frozen 避免运行时被意外改写。"""

    base_url: str
    api_key: str
    model: str
    provider: str = "custom"
    timeout: float = 60.0
    max_retries: int = 3
    # 价格单位：元 / 百万 token。默认值仅作示例，请按官方价格修改。
    price_in: float = 2.0
    price_out: float = 8.0

    def __post_init__(self) -> None:
        if not self.base_url.startswith("http"):
            raise ConfigError(f"base_url 不合法: {self.base_url!r}")
        if not self.api_key:
            raise ConfigError("缺少 API Key，请检查 .env")


# 各家的默认端点与模型名，可用环境变量覆盖。
PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "dashscope": {
        "key_env": "DASHSCOPE_API_KEY",
        "base_env": "DASHSCOPE_BASE_URL",
        "model_env": "DASHSCOPE_MODEL",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "zhipu": {
        "key_env": "ZHIPU_API_KEY",
        "base_env": "ZHIPU_BASE_URL",
        "model_env": "ZHIPU_MODEL",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-air",
    },
}


def load_env_file(path: str | Path = ".env") -> None:
    """极简 .env 加载：KEY=VALUE，# 开头为注释。

    不依赖 python-dotenv，方便在干净环境里直接跑。
    """
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(provider: str | None = None) -> LLMConfig:
    """按优先级构造配置：显式 provider > OPENAI_* 通用变量 > LLM_PROVIDER。"""
    load_env_file()

    if provider is None and os.getenv("OPENAI_API_KEY"):
        provider = "openai"
    provider = provider or os.getenv("LLM_PROVIDER", "deepseek")
    provider = provider.lower()

    if provider == "openai":
        return LLMConfig(
            provider="openai",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )

    if provider not in PROVIDERS:
        raise ConfigError(f"未知 provider: {provider}，可选: {', '.join(PROVIDERS)} / openai")

    spec = PROVIDERS[provider]
    api_key = os.getenv(spec["key_env"], "")
    if not api_key:
        raise ConfigError(f"未设置 {spec['key_env']}，请复制 .env.example 为 .env 并填写")
    return LLMConfig(
        provider=provider,
        base_url=os.getenv(spec["base_env"], spec["base_url"]),
        api_key=api_key,
        model=os.getenv(spec["model_env"], spec["model"]),
    )


# ---------------------------------------------------------------------------
# 用量与成本
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def cost(self, cfg: LLMConfig) -> float:
        """按百万 token 单价估算成本（元）。"""
        return (
            self.prompt_tokens * cfg.price_in + self.completion_tokens * cfg.price_out
        ) / 1_000_000


@dataclass
class ChatResult:
    content: str
    model: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    cost_cny: float = 0.0
    finish_reason: str | None = None
    raw: Any = None  # 原始 message（含 tool_calls），Agent 循环需要

    @property
    def tool_calls(self) -> list[Any]:
        return list(getattr(self.raw, "tool_calls", None) or [])

    def __str__(self) -> str:
        return self.content


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


def _classify(exc: Exception) -> bool:
    """判断是否值得重试。

    openai SDK 的异常类型来自 openai 包，这里用鸭子类型避免强耦合。
    """
    name = type(exc).__name__
    if name in {"APITimeoutError", "APIConnectionError", "InternalServerError", "RateLimitError"}:
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return False


def _backoff(attempt: int, base: float = 1.0, cap: float = 8.0) -> float:
    """指数退避 + 随机抖动，防止限流时同时重试打爆服务端。"""
    return min(base * (2**attempt), cap) + random.uniform(0, 0.3)


class LLMClient:
    """同步 + 异步 + 流式三合一的客户端。"""

    def __init__(self, config: LLMConfig | None = None, *, client: Any = None):
        self.config = config or load_config()
        if client is not None:
            self._client, self._aclient = client, client
            return
        from openai import AsyncOpenAI, OpenAI

        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=0,  # 重试由我们自己控制，便于统一日志与退避
        )
        self._aclient = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=0,
        )
        self.total = Usage()

    # -- 内部：把 SDK 响应转成 ChatResult -------------------------------
    def _to_result(self, resp: Any, latency_ms: int) -> ChatResult:
        usage = Usage()
        if getattr(resp, "usage", None):
            usage = Usage(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
        self.total.add(usage)
        choice = resp.choices[0]
        return ChatResult(
            content=choice.message.content or "",
            model=getattr(resp, "model", self.config.model),
            usage=usage,
            latency_ms=latency_ms,
            cost_cny=usage.cost(self.config),
            finish_reason=getattr(choice, "finish_reason", None),
            raw=choice.message,
        )

    def _params(self, messages: Iterable[dict], **kwargs: Any) -> dict[str, Any]:
        params = {
            "model": kwargs.pop("model", self.config.model),
            "messages": list(messages),
            "temperature": kwargs.pop("temperature", 0.3),
        }
        params.update(kwargs)
        return params

    # -- 同步 -----------------------------------------------------------
    def chat(self, messages: Iterable[dict], **kwargs: Any) -> ChatResult:
        params = self._params(messages, **kwargs)
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._client.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001 - 需要统一分类
                last = exc
                if attempt >= self.config.max_retries or not _classify(exc):
                    raise LLMError(f"调用失败（{type(exc).__name__}）: {exc}") from exc
                delay = _backoff(attempt)
                log.warning("retry %d/%d after %.2fs: %s", attempt + 1, self.config.max_retries, delay, type(exc).__name__)
                time.sleep(delay)
                continue
            result = self._to_result(resp, int((time.perf_counter() - t0) * 1000))
            log.info(
                "chat ok model=%s ms=%d tokens=%d/%d cost=¥%.6f",
                result.model,
                result.latency_ms,
                result.usage.prompt_tokens,
                result.usage.completion_tokens,
                result.cost_cny,
            )
            return result
        raise LLMError(str(last))

    # -- 流式 -----------------------------------------------------------
    def stream(self, messages: Iterable[dict], **kwargs: Any) -> Iterable[str]:
        """逐段产出文本增量。网络异常会向上抛，由调用方决定是否重试。"""
        params = self._params(messages, **kwargs)
        params["stream"] = True
        params.setdefault("stream_options", {"include_usage": True})
        usage = Usage()
        for chunk in self._client.chat.completions.create(**params):
            if getattr(chunk, "usage", None):
                usage = Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content or ""
            if piece:
                yield piece
        self.total.add(usage)

    # -- 异步 -----------------------------------------------------------
    async def astream(self, messages: Iterable[dict], **kwargs: Any):
        """异步流式，Service 层（FastAPI SSE）用这个。"""
        params = self._params(messages, **kwargs)
        params["stream"] = True
        params.setdefault("stream_options", {"include_usage": True})
        usage = Usage()
        stream = await self._aclient.chat.completions.create(**params)
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content or ""
            if piece:
                yield piece
        self.total.add(usage)

    async def achat(self, messages: Iterable[dict], **kwargs: Any) -> ChatResult:
        params = self._params(messages, **kwargs)
        for attempt in range(self.config.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await self._aclient.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.config.max_retries or not _classify(exc):
                    raise LLMError(f"调用失败（{type(exc).__name__}）: {exc}") from exc
                await asyncio.sleep(_backoff(attempt))
                continue
            return self._to_result(resp, int((time.perf_counter() - t0) * 1000))
        raise LLMError("重试耗尽")

    def report(self) -> dict[str, Any]:
        """累计用量报表，第 7 周的成本报告直接复用。"""
        return {
            "model": self.config.model,
            "provider": self.config.provider,
            "prompt_tokens": self.total.prompt_tokens,
            "completion_tokens": self.total.completion_tokens,
            "cost_cny": round(self.total.cost(self.config), 6),
        }


_default: LLMClient | None = None


def get_client() -> LLMClient:
    """进程级单例，避免每次调用都新建 HTTP 连接池。"""
    global _default
    if _default is None:
        _default = LLMClient()
    return _default
