"""生产级 LLM 客户端（第 1 周产出，后续所有项目复用）。

设计目标：一套代码跑通所有 OpenAI 兼容端点（DeepSeek / 阿里百炼 / 智谱 / Kimi / OpenAI）。

覆盖六个生产要素：
1. 配置集中：LLMConfig dataclass 统管所有参数，一处修改全局生效
2. 超时：OpenAI SDK 层设置 timeout，避免无限等待
3. 重试：指数退避 + 随机抖动，只重试"网络抖动/限流/5xx"
4. 并发：异步接口 astream/achat 支持高并发场景
5. 日志：logging 模块记录每次调用的 model/tokens/cost
6. 成本统计：Usage dataclass 累计 token，按单价估算成本

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


# 模块级 logger，上层可通过 logging.getLogger("llm") 控制级别
log = logging.getLogger("llm")

# ---------------------------------------------------------------------------
# 错误分层
# ---------------------------------------------------------------------------
# 为什么分层？因为不同错误需要不同处理策略：
# - ConfigError: 配置错了，重试无意义，直接报错让人改
# - RetryableError: 网络问题，可以重试
# - ProtocolError: 供应商 bug，重试也无意义，应该告警或切换供应商


class LLMError(RuntimeError):
    """所有 LLM 调用错误的基类。

    上层捕获这个异常就能处理所有 LLM 相关问题。
    """


class ConfigError(LLMError):
    """配置缺失或非法。

    例如：.env 里没填 API Key，或 base_url 格式不对。
    抛出即说明需要人工介入修改配置。
    """


class RetryableError(LLMError):
    """网络抖动 / 限流 / 服务端 5xx，可以重试。

    注意：当前代码里实际重试逻辑在 chat/achat 内部，
    这个类主要作为"可重试"的语义标记。
    """


class ProtocolError(LLMError):
    """供应商返回 200 但响应体不符合 OpenAI 协议规范（如 choices 为空）。

    属于供应商侧的 bug，重试无意义，应由调用方决定是否告警/切换供应商。
    """


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    """一次调用需要的全部配置。

    frozen=True 表示实例创建后不可修改，避免运行时被意外改写导致难以排查的 bug。

    字段说明：
        base_url: API 端点地址，如 https://api.deepseek.com
        api_key:  认证密钥，从 .env 读取
        model:    模型名，如 deepseek-chat / qwen-plus / gpt-4o-mini
        provider: 供应商标识，用于日志和成本报表
        timeout:  单次请求超时时间（秒）
        max_retries: 失败时的最大重试次数（不含首次调用）
        price_in/out: token 单价（元/百万 token），用于成本估算
        supports_temperature: 兼容性开关，False 时丢弃 temperature 参数
        max_tokens_field: 输出上限字段名，Kimi 用 max_completion_tokens
    """

    base_url: str
    api_key: str
    model: str
    provider: str = "custom"
    timeout: float = 60.0
    max_retries: int = 3
    # 价格单位：元 / 百万 token。默认值仅作示例，请按官方价格修改（或设 LLM_PRICE_IN/OUT）。
    price_in: float = 2.0
    price_out: float = 8.0
    # 兼容性开关：Kimi K3.1 Pro 的 temperature/top_p 是固定值，不能显式传；
    # 它的输出上限字段叫 max_completion_tokens 而不是 max_tokens。
    supports_temperature: bool = True
    max_tokens_field: str = "max_tokens"

    def __post_init__(self) -> None:
        """dataclass 的"后置校验"钩子，创建实例后自动调用。

        这里做两个最基本的检查：
        - base_url 必须以 http 开头
        - api_key 不能为空

        检查不通过立即抛 ConfigError，避免等到真正调用时才报错。
        """
        if not self.base_url.startswith("http"):
            raise ConfigError(f"base_url 不合法: {self.base_url!r}")
        if not self.api_key:
            raise ConfigError("缺少 API Key，请检查 .env")


# 各家的默认端点与模型名，可用环境变量覆盖。
# 结构：key_env 是 API Key 的环境变量名，base_env 是 base_url 的环境变量名，
#       model_env 是模型名的环境变量名，后两个是默认值。
PROVIDERS: dict[str, dict[str, object]] = {
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
    # Kimi（Moonshot）：OpenAI 兼容；K3.1 Pro 固定 temperature/top_p，且用 max_completion_tokens
    "moonshot": {
        "key_env": "MOONSHOT_API_KEY",
        "base_env": "MOONSHOT_BASE_URL",
        "model_env": "MOONSHOT_MODEL",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k3.1-pro",
        "supports_temperature": False,       # K3.1 Pro 固定温度，显式传会报错
        "max_tokens_field": "max_completion_tokens",  # 字段名不同
    },
}

# 追求极简依赖，或 .env 格式简单且固定在当前目录
# 不使用load_dotenv（减少一个第三方依赖）
def load_env_file(path: str | Path = ".env") -> None:
    """极简 .env 加载：KEY=VALUE，# 开头为注释。

    不依赖 python-dotenv，方便在干净环境里直接跑。

    解析规则：
    - 空行跳过
    - # 开头是注释，跳过
    - 按第一个 = 分割，左边是 key，右边是 value
    - value 去掉首尾空白，再去掉首尾引号（单双引号都支持）
    - 用 setdefault 写入环境变量，避免覆盖已有的环境变量
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
    """按优先级构造配置：显式 provider > OPENAI_* 通用变量 > LLM_PROVIDER。

    参数:
        provider: 可选，指定供应商名（如 "deepseek"）。不传则自动推断。

    返回:
        LLMConfig 实例（frozen，不可修改）

    优先级逻辑：
    1. 如果显式传了 provider，用它
    2. 否则如果环境变量有 OPENAI_API_KEY，认为要用 OpenAI
    3. 否则读 LLM_PROVIDER，默认 "deepseek"
    """
    load_env_file()

    # 自动推断：有 OpenAI 的 key 就用 OpenAI
    if provider is None and os.getenv("OPENAI_API_KEY"):
        provider = "openai"
    provider = provider or os.getenv("LLM_PROVIDER", "deepseek")
    provider = provider.lower()

    # token 单价可以从环境变量覆盖
    price_in = float(os.getenv("LLM_PRICE_IN", "2.0"))
    price_out = float(os.getenv("LLM_PRICE_OUT", "8.0"))

    # OpenAI 单独处理（因为端点结构不同）
    if provider == "openai":
        return LLMConfig(
            provider="openai",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            price_in=price_in,
            price_out=price_out,
        )

    # 其他供应商从 PROVIDERS 表里取配置
    if provider not in PROVIDERS:
        raise ConfigError(f"未知 provider: {provider}，可选: {', '.join(PROVIDERS)} / openai")

    spec = PROVIDERS[provider]
    api_key = os.getenv(str(spec["key_env"]), "")
    if not api_key:
        raise ConfigError(f"未设置 {spec['key_env']}，请复制 .env.example 为 .env 并填写")
    return LLMConfig(
        provider=provider,
        base_url=os.getenv(str(spec["base_env"]), str(spec["base_url"])),
        api_key=api_key,
        model=os.getenv(str(spec["model_env"]), str(spec["model"])),
        price_in=price_in,
        price_out=price_out,
        supports_temperature=bool(spec.get("supports_temperature", True)),
        max_tokens_field=str(spec.get("max_tokens_field", "max_tokens")),
    )


# ---------------------------------------------------------------------------
# 用量与成本
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """token 用量统计。

    可变的 dataclass，用于累计多次调用的 token 数。
    """

    prompt_tokens: int = 0      # 输入 token 数（你发给模型的）
    completion_tokens: int = 0  # 输出 token 数（模型返回的）

    def add(self, other: "Usage") -> None:
        """累加另一次调用的用量。用于 LLMClient.total 累计所有调用。"""
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens

    @property
    def total_tokens(self) -> int:
        """输入 + 输出的总 token 数。"""
        return self.prompt_tokens + self.completion_tokens

    def cost(self, cfg: LLMConfig) -> float:
        """按百万 token 单价估算成本（元）。

        公式：prompt_tokens × 输入单价 + completion_tokens × 输出单价，再除以 1_000_000
        因为 price_in/out 的单位是"元/百万 token"。
        """
        return (
            self.prompt_tokens * cfg.price_in + self.completion_tokens * cfg.price_out
        ) / 1_000_000


@dataclass
class ChatResult:
    """一次 LLM 调用的完整结果。

    比 openai SDK 返回的对象更"好用"：
    - 直接有 .content 字符串，不用 choices[0].message.content
    - 直接有 .cost_cny，不用自己算
    - 保留 .raw 原始 message，Agent 循环需要拿 tool_calls
    """

    content: str                    # 模型返回的文本内容
    model: str                      # 实际使用的模型名（供应商可能返回不同名）
    usage: Usage = field(default_factory=Usage)  # token 用量
    latency_ms: int = 0             # 耗时（毫秒）
    cost_cny: float = 0.0           # 估算成本（元）
    finish_reason: str | None = None  # 结束原因：stop / length / tool_calls 等
    raw: Any = None                 # 原始 message 对象（含 tool_calls），Agent 循环需要

    @property
    def tool_calls(self) -> list[Any]:
        """提取 tool_calls，供 Agent 循环使用。

        用 getattr 做防御性编程：有些供应商返回的 message 可能没有 tool_calls 字段。
        """
        return list(getattr(self.raw, "tool_calls", None) or [])

    def __str__(self) -> str:
        """打印时直接显示 content，方便调试。"""
        return self.content


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------


def _classify(exc: Exception) -> bool:
    """判断异常是否值得重试。

    用鸭子类型（看异常名和 status_code 属性）而不是 isinstance，
    避免强耦合 openai SDK 的具体异常类。

    可重试的条件：
    - 异常名是 APITimeoutError / APIConnectionError / InternalServerError / RateLimitError
    - 或 HTTP 状态码是 429（限流）或 >= 500（服务端错误）
    """
    name = type(exc).__name__
    if name in {"APITimeoutError", "APIConnectionError", "InternalServerError", "RateLimitError"}:
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return False


def _backoff(attempt: int, base: float = 1.0, cap: float = 8.0) -> float:
    """指数退避 + 随机抖动，防止限流时同时重试打爆服务端。

    公式：min(base × 2^attempt, cap) + random(0, 0.3)
    - attempt=0 → 约 1 秒
    - attempt=1 → 约 2 秒
    - attempt=2 → 约 4 秒
    - attempt=3 → 约 8 秒（cap 上限）

    随机抖动：避免多个客户端同时重试形成"重试风暴"。
    """
    return min(base * (2**attempt), cap) + random.uniform(0, 0.3)


def request_params(config: LLMConfig, messages: Iterable[dict], **kwargs: Any) -> dict[str, Any]:
    """按供应商差异组装请求参数。

    各家 API 有细微差异，这里统一处理：
    - Kimi K3.1 Pro 的 temperature/top_p 是固定值，显式传会被拒绝 → 直接丢弃
    - Kimi 用 max_completion_tokens 表示输出上限 → 自动改名

    参数:
        config:   LLMConfig 实例
        messages: 对话消息列表
        **kwargs: 其他参数（temperature/max_tokens 等）

    返回:
        可直接传给 openai SDK 的字典
    """
    params: dict[str, Any] = {
        "model": kwargs.pop("model", config.model),  # 默认用配置里的模型，也可临时覆盖
        "messages": list(messages),                   # 转成 list，避免迭代器被消耗
    }
    # temperature 处理：支持的供应商传值，不支持的丢弃
    if config.supports_temperature:
        params["temperature"] = kwargs.pop("temperature", 0.3)  # 默认 0.3
    else:
        kwargs.pop("temperature", None)  # 丢弃，避免报错

    # max_tokens 字段名兼容：Kimi 用 max_completion_tokens
    if config.max_tokens_field != "max_tokens" and "max_tokens" in kwargs:
        kwargs[config.max_tokens_field] = kwargs.pop("max_tokens")

    # 其他参数原样传入（如 top_p, presence_penalty 等）
    params.update(kwargs)
    return params


class LLMClient:
    """同步 + 异步 + 流式三合一的客户端。

    使用方式：
        client = LLMClient()           # 自动从 .env 加载配置
        result = client.chat([...])    # 同步调用
        async for piece in client.astream([...]):  # 异步流式
    """

    def __init__(self, config: LLMConfig | None = None, *, client: Any = None):
        """初始化客户端。

        参数:
            config: LLMConfig 实例。不传则自动调用 load_config() 从 .env 加载。
            client: 可选，传入已有的 OpenAI client（用于测试 mock）。
        """
        self.config = config or load_config()
        self.total = Usage()  # 累计用量，用于成本报表
        if client is not None:
            # 测试时传入 mock client，避免真实网络请求
            self._client, self._aclient = client, client
            return
        from openai import AsyncOpenAI, OpenAI

        # max_retries=0：关闭 SDK 自带的重试，由我们自己控制重试逻辑
        # 这样日志和退避策略都统一，不会出现"SDK 重试 3 次 + 我们重试 3 次 = 9 次"的情况
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=0,
        )
        self._aclient = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=0,
        )

    # -- 内部：把 SDK 响应转成 ChatResult -------------------------------
    def _to_result(self, resp: Any, latency_ms: int) -> ChatResult:
        """把 openai SDK 的响应对象转换成我们的 ChatResult。

        做三件事：
        1. 提取 usage（token 用量），累加到 self.total
        2. 检查 choices 是否为空（防御性编程）
        3. 打印学习日志（model、finish_reason、content 前 500 字）
        """
        # 提取 token 用量：有些供应商可能不返回 usage，用 getattr 防御
        usage = Usage()
        if getattr(resp, "usage", None):
            usage = Usage(resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
        self.total.add(usage)  # 累加到客户端级别的总用量

        # 检查 choices：正常情况下 choices 至少有一个，为空说明供应商 bug
        if not getattr(resp, "choices", None):
            raise ProtocolError(f"供应商返回 200 但 choices 为空: model={getattr(resp, 'model', '?')}")

        choice = resp.choices[0]
        content = choice.message.content or ""
        # 学习用：打印模型返回的原始内容，方便观察结构化输出/修复闭环
        print(f"\n[LLM 返回] model={getattr(resp, 'model', self.config.model)} finish={getattr(choice, 'finish_reason', '?')}")
        print(f"[LLM 返回] {content[:500]}")

        return ChatResult(
            content=content,
            model=getattr(resp, "model", self.config.model),
            usage=usage,
            latency_ms=latency_ms,
            cost_cny=usage.cost(self.config),  # 按当前配置的单价估算成本
            finish_reason=getattr(choice, "finish_reason", None),
            raw=choice.message,  # 保留原始 message，Agent 循环需要 tool_calls
        )

    def _params(self, messages: Iterable[dict], **kwargs: Any) -> dict[str, Any]:
        """组装请求参数的快捷方法，代理到模块级 request_params 函数。"""
        return request_params(self.config, messages, **kwargs)

    @staticmethod
    def _print_messages(tag: str, params: dict[str, Any]) -> None:
        """学习用：打印发给模型的 messages，图片 content 只显示前缀避免刷屏。

        参数:
            tag:    标签（如 "chat"、"achat"），用于区分调用来源
            params: request_params 返回的字典，包含 model 和 messages
        """
        print(f"\n[LLM 请求:{tag}] model={params.get('model')} messages={len(params['messages'])}条")
        for i, m in enumerate(params["messages"]):
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, list):
                # 多模态 content：[{type:text}, {type:image_url, ...}]
                # 图片 base64 太长，只显示前 40 字符
                parts = []
                for c in content:
                    if c.get("type") == "text":
                        parts.append(f"text({len(c.get('text',''))}字)")
                    elif c.get("type") == "image_url":
                        url = c.get("image_url", {}).get("url", "")
                        parts.append(f"image({url[:40]}…)" if len(url) > 40 else f"image({url})")
                    else:
                        parts.append(str(c.get("type", "?")))
                print(f"  [{i}] {role}: {' + '.join(parts)}")
            else:
                # 纯文本 content：超过 200 字截断，避免刷屏
                text = str(content)
                display = text[:200] + "…" if len(text) > 200 else text
                print(f"  [{i}] {role}: {display}")

    # -- 同步 -----------------------------------------------------------
    def chat(self, messages: Iterable[dict], **kwargs: Any) -> ChatResult:
        """同步对话调用（最常用）。

        流程：
        1. 组装参数（model/messages/temperature/max_tokens）
        2. 打印学习日志（发给模型的内容）
        3. 循环尝试（最多 max_retries + 1 次）：
           - 成功：返回 ChatResult
           - 失败：判断是否可重试，是则退避等待后重试，否则抛异常
        4. 记录 info 日志（model/tokens/cost）

        参数:
            messages: 对话消息列表，如 [{"role": "user", "content": "你好"}]
            **kwargs: 其他参数（temperature/max_tokens/model 等）

        返回:
            ChatResult 实例
        """
        params = self._params(messages, **kwargs)
        # 学习用：打印发给模型的 messages（图片类 content 只显示前缀避免刷屏）
        self._print_messages("chat", params)
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._client.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001 - 需要统一分类
                last = exc
                # 判断：已用完重试次数 或 错误不可重试 → 直接抛
                if attempt >= self.config.max_retries or not _classify(exc):
                    raise LLMError(f"调用失败（{type(exc).__name__}）: {exc}") from exc
                # 可重试：计算退避时间，等待后 continue
                delay = _backoff(attempt)
                log.warning("retry %d/%d after %.2fs: %s", attempt + 1, self.config.max_retries, delay, type(exc).__name__)
                time.sleep(delay)
                continue
            # 成功：转换为 ChatResult，记录日志，返回
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
        # 理论上不会走到这里（循环里要么 return 要么 raise），防御性兜底
        raise LLMError(str(last))

    # -- 流式 -----------------------------------------------------------
    def stream(self, messages: Iterable[dict], **kwargs: Any) -> Iterable[str]:
        """逐段产出文本增量（同步流式）。

        用于"打字机效果"场景：用户看到的是一个字一个字蹦出来，而不是等半天一次性显示。

        网络异常会向上抛，由调用方决定是否重试。

        兼容旧用法：默认只产出文本字符串。
        传入 with_seq=True 时产出 (seq, text) 元组，seq 从 0 递增，
        供调用方做断点续传时的去重与排序。
        """
        with_seq = kwargs.pop("with_seq", False)
        params = self._params(messages, **kwargs)
        # 设置流式
        params["stream"] = True
        params.setdefault("stream_options", {"include_usage": True})
        usage = Usage()
        seq = 0
        # SDK 返回的是一个迭代器，每次 yield 一个 chunk（数据块）
        for chunk in self._client.chat.completions.create(**params):
            # 最后一个 chunk 可能包含 usage 信息（token 统计）
            if getattr(chunk, "usage", None):
                usage = Usage(chunk.usage.prompt_tokens or 0, chunk.usage.completion_tokens or 0)
            # choices 为空可能是心跳包，跳过
            if not chunk.choices:
                continue
            # delta.content 是本次新增的文本片段（可能为空字符串）
            piece = chunk.choices[0].delta.content or ""
            if piece:
                if with_seq:
                    yield seq, piece
                    seq += 1
                else:
                    yield piece
        # 流式结束后，把 usage 累加到 total
        self.total.add(usage)

    # -- 异步 -----------------------------------------------------------
    async def astream(self, messages: Iterable[dict], **kwargs: Any):
        """异步流式，Service 层（FastAPI SSE）用这个。

        与 stream() 逻辑相同，只是用 async/await 语法。
        在异步上下文中不会阻塞事件循环，其他协程可以趁机执行。
        """
        params = self._params(messages, **kwargs)
        params["stream"] = True
        params.setdefault("stream_options", {"include_usage": True})
        usage = Usage()
        # await 创建流对象，然后 async for 逐块读取
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
        """异步对话调用（与 chat() 逻辑相同，只是用 async/await）。

        关键区别：重试等待用 asyncio.sleep 而不是 time.sleep。
        - time.sleep(5)    → 阻塞整个线程，别的任务都别想跑
        - asyncio.sleep(5) → 只是"这个协程"等 5 秒，事件循环可以趁机去跑其他协程
        """
        params = self._params(messages, **kwargs)
        self._print_messages("achat", params)
        for attempt in range(self.config.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await self._aclient.chat.completions.create(**params)
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.config.max_retries or not _classify(exc):
                    raise LLMError(f"调用失败（{type(exc).__name__}）: {exc}") from exc
                # time.sleep(5)       # 阻塞：整个线程卡死 5 秒，别的任务都别想跑
                # asyncio.sleep(5)    # 异步：只是"这个协程"等 5 秒，事件循环可以趁机去跑其他协程
                await asyncio.sleep(_backoff(attempt))
                continue
            return self._to_result(resp, int((time.perf_counter() - t0) * 1000))
        raise LLMError("重试耗尽")

    def report(self) -> dict[str, Any]:
        """累计用量报表，第 7 周的成本报告直接复用。

        返回:
            包含 model/provider/prompt_tokens/completion_tokens/cost_cny 的字典
        """
        return {
            "model": self.config.model,
            "provider": self.config.provider,
            "prompt_tokens": self.total.prompt_tokens,
            "completion_tokens": self.total.completion_tokens,
            "cost_cny": round(self.total.cost(self.config), 6),
        }


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------
# 为什么要单例？因为每个 LLMClient 实例都会创建一个 HTTP 连接池。
# 如果每次调用都新建 client，连接池无法复用，性能很差。
# 单例保证整个进程共享一个连接池。


_default: LLMClient | None = None


def get_client() -> LLMClient:
    """进程级单例，避免每次调用都新建 HTTP 连接池。

    使用方式：
        client = get_client()  # 第一次调用时创建，后续直接返回同一个实例

    注意：这不是线程安全的（多线程并发首次调用可能创建多个实例），
    但对于我们的使用场景（单进程异步）足够了。
    """
    global _default
    if _default is None:
        _default = LLMClient()
    return _default
