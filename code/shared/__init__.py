"""共享基础设施：LLM 客户端、结构化输出工具。

设计原则：
- 只依赖 openai SDK + 标准库，不引入框架
- 配置从环境变量/`.env` 读取，换供应商只改配置
- 所有对外方法都带重试、超时、日志、成本统计
"""

from .structured import StructuredOutputError, extract_json, loads_lenient, model_from_text
from .llm_client import (
    ChatResult,
    ConfigError,
    LLMClient,
    LLMConfig,
    LLMError,
    RetryableError,
    Usage,
    get_client,
    load_config,
)

__all__ = [
    "ChatResult",
    "ConfigError",
    "LLMClient",
    "LLMConfig",
    "LLMError",
    "RetryableError",
    "StructuredOutputError",
    "Usage",
    "extract_json",
    "get_client",
    "loads_lenient",
    "load_config",
    "model_from_text",
]
