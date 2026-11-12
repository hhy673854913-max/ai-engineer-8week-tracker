"""结构化输出工具：从"模型自由发挥"到"程序可消费"的最后一公里。

包含三件事：
1. extract_json: 从带解释/代码块的输出里抠出 JSON
2. loads_lenient: 容忍尾逗号等小毛病
3. model_from_text: 解析 + Pydantic 校验 + 带错误重试的修复闭环
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger("structured")

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class StructuredOutputError(RuntimeError):
    """多次修复后仍然无法得到合法结构。"""


def extract_json(text: str) -> str:
    """从模型输出里提取 JSON 文本。

    处理三类常见污染：markdown 代码块、前后解释、多个对象（取第一个完整对象）。
    """
    # 前后去空
    text = text.strip()
    # 去除markdown 代码块、前后解释
    fence = _FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"找不到 JSON 对象，原始输出前 200 字: {text[:200]!r}")
    return text[start : end + 1]


def loads_lenient(text: str) -> dict[str, Any]:
    """先严格解析，失败后修掉尾逗号再试一次。"""
    try:
        return json.loads(text)
    # 不符合标准 JSON 规范，尝试修掉尾逗号
    except json.JSONDecodeError:
        fixed = _TRAILING_COMMA.sub(r"\1", text)
        return json.loads(fixed)


def model_from_text(raw: str, model: type[T]) -> T:
    """解析并校验，失败抛 ValidationError（由上层决定是否重试）。"""
    return model.model_validate(loads_lenient(extract_json(raw)))


def repair_messages(original: str, error: ValidationError | ValueError, *, max_errors: int = 3) -> list[dict]:
    """构造"带错误回传"的修复消息。

    比"重新生成一次"有效得多：模型能定位到具体字段。
    """
    if isinstance(error, ValidationError):
        detail = error.errors()[:max_errors]
    else:
        detail = str(error)
    return [
        {"role": "assistant", "content": original},
        {
            "role": "user",
            "content": (
                f"上面的输出不符合要求：{detail}。\n"
                "只输出修正后的 JSON，不要解释，不要 markdown 代码块。"
            ),
        },
    ]


def generate_with_repair(
    chat_fn: Callable[..., Any],
    prompt: str,
    model: type[T],
    *,
    max_repair: int = 2,
    **chat_kwargs: Any,
) -> tuple[T, int]:
    """生成 → 解析 → 校验 → 失败带错误重试，最多 max_repair 次修复。

    返回 (解析结果, 实际调用次数)。调用次数 = 1 + 修复次数。
    chat_fn 需返回 ChatResult（有 .content 属性）或 str。
    """
    messages: list[dict] = [{"role": "user", "content": prompt}]
    last_error: Exception | None = None
    for attempt in range(max_repair + 1):
        result = chat_fn(messages, **chat_kwargs)
        raw = getattr(result, "content", result)
        try:
            return model_from_text(raw, model), attempt + 1
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            log.warning("结构化解析失败（第 %d 次）: %s", attempt + 1, exc)
            if attempt >= max_repair:
                break
            messages += repair_messages(raw, exc)  # type: ignore[arg-type]
    raise StructuredOutputError(f"修复 {max_repair} 次后仍失败: {last_error}")
