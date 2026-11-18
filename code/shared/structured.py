"""结构化输出工具：从"模型自由发挥"到"程序可消费"的最后一公里。

大模型天生喜欢"自由发挥"——加解释、套 markdown、偶尔格式跑偏。
但程序要的是"能 json.loads 的对象"。这个模块就是中间的"翻译官 + 质检员"。

包含四件事：
1. extract_json:    从带解释/代码块的输出里"抠"出纯 JSON 文本
2. loads_lenient:   容忍尾逗号等小毛病，先严格后宽松
3. model_from_text: 解析 + Pydantic 校验，一步到位得到类型安全对象
4. generate_with_repair: 上面三步失败时，把错误回传给模型让它自己改（修复闭环）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

# 模块级 logger，方便上层通过 logging.getLogger("structured") 控制级别
log = logging.getLogger("structured")

# 泛型 T 限定为 Pydantic BaseModel 的子类，
# 这样 model_from_text 返回的对象既有 .model_dump() 又有类型校验
T = TypeVar("T", bound=BaseModel)

# 预编译正则，避免每次调用重复编译（性能小细节）
# 匹配 ```json ... ``` 或 ``` ... ``` 的 markdown 代码块
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
# 匹配 }, 或 ], 前面的尾逗号（JSON 标准不允许，但模型常犯）
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class StructuredOutputError(RuntimeError):
    """多次修复后仍然无法得到合法结构。

    抛出这个异常说明：
    - 模型第一轮输出格式不对
    - 带着错误信息重试了 max_repair 次还是不行
    此时应该人工介入检查，或换更强的模型。
    """


def extract_json(text: str) -> str:
    """从模型输出里提取 JSON 文本。

    处理三类常见污染：
    - markdown 代码块：```json {...} ``` → 只保留 {...}
    - 前后解释："好的，这是结果：{...} 希望帮到你" → 只保留 {...}
    - 多个对象：取第一个完整的 {...}（从第一个 { 到最后一个 }）

    参数:
        text: 模型的原始字符串输出

    返回:
        纯 JSON 文本（可被 json.loads 解析）

    异常:
        ValueError: 找不到任何 JSON 对象时抛出，带原始输出前 200 字方便调试
    """
    # 前后去空白，避免 strip 影响后续查找
    text = text.strip()

    # 第一步：尝试去掉 markdown 代码块
    # 如果模型听话用了 ```json，这里直接取出中间内容
    fence = _FENCE.search(text)
    if fence:
        text = fence.group(1).strip()

    # 第二步：定位第一个 { 和最后一个 }
    # 这样能跳过 "... 结果是：" 之类的前缀，以及 "希望对你有帮助" 之类的后缀
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        # 连花括号都找不到，说明模型完全没按格式输出
        raise ValueError(f"找不到 JSON 对象，原始输出前 200 字: {text[:200]!r}")

    # 截取第一个 { 到最后一个 } 之间的内容（含两端）
    return text[start : end + 1]


def loads_lenient(text: str) -> dict[str, Any]:
    """先严格解析 JSON，失败后修掉尾逗号再试一次。

    为什么要"宽容"？因为大模型生成的 JSON 经常有尾逗号：
        {"a": 1, "b": 2,}   ← 最后这个逗号不标准，但 json.loads 会报错

    策略：先按标准来（快），失败了再修（慢但兼容）。
    这样正常情况零开销，异常情况也能救回来。

    参数:
        text: JSON 字符串

    返回:
        解析后的 Python dict

    异常:
        json.JSONDecodeError: 修完尾逗号仍然解析失败
    """
    try:
        # 第一次：严格模式，大多数情况应该成功
        return json.loads(text)
    except json.JSONDecodeError:
        # 第二次：修掉尾逗号再试
        # ",}" → "}", ",]" → "]"
        fixed = _TRAILING_COMMA.sub(r"\1", text)
        return json.loads(fixed)


def model_from_text(raw: str, model: type[T]) -> T:
    """一步到位：提取 JSON → 解析 → Pydantic 校验 → 返回类型安全对象。

    这是"单发版"，只尝试一次，失败抛异常。
    如果要自动重试，请用下面的 generate_with_repair。

    参数:
        raw:   模型的原始输出（可能带 markdown、解释等）
        model: Pydantic 模型类（如 ImageDesc）

    返回:
        校验通过的 Pydantic 实例

    异常:
        ValueError / ValidationError: 格式不对或校验失败
    """
    return model.model_validate(loads_lenient(extract_json(raw)))


def repair_messages(original: str, error: ValidationError | ValueError, *, max_errors: int = 3) -> list[dict]:
    """构造"带错误回传"的修复消息。

    核心思想：与其让模型"重新生成一次"（它可能犯同样的错），
    不如明确告诉它"你刚才哪里错了"，让它针对性修正。

    消息结构（多轮对话）：
        [..., assistant: 原始错误输出, user: 错误详情 + 修正要求]

    参数:
        original:   模型刚才的原始输出（作为 assistant 消息回传）
        error:      解析/校验错误（Pydantic ValidationError 或 ValueError）
        max_errors: 最多显示几条错误，避免 prompt 过长

    返回:
        两条消息（assistant + user），可直接 append 到 messages 列表
    """
    if isinstance(error, ValidationError):
        # Pydantic 的 errors() 返回结构化错误列表，如：
        # [{'loc': ('main_objects',), 'msg': 'List should have at least 1 item', ...}]
        # 只取前 max_errors 条，避免 prompt 被错误信息淹没
        detail = error.errors()[:max_errors]
    else:
        # ValueError（如 extract_json 找不到 JSON）直接转字符串
        detail = str(error)

    return [
        # assistant 消息：把模型刚才的"错误答案"原样回传
        # 这样模型能看到自己输出了什么，而不是凭空猜
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

    这是"自动修复版"，核心循环：
        第 1 轮：正常调用 → 解析 → 失败则带错误重试
        第 2 轮：带着历史消息再调用 → 解析 → 失败则再重试
        ...
        第 max_repair+1 轮：最后一次机会 → 失败则抛 StructuredOutputError

    参数:
        chat_fn:    调用大模型的函数，签名为 chat_fn(messages, **kwargs) -> ChatResult|str
        prompt:     首轮发给模型的 prompt
        model:      Pydantic 模型类，用于校验输出
        max_repair: 最多修复几次（默认 2，即最多调用 3 次）
        **chat_kwargs: 传给 chat_fn 的额外参数（如 temperature、max_tokens）

    返回:
        (解析结果, 实际调用次数)。调用次数 = 1 + 修复次数。

    异常:
        StructuredOutputError: 修复 max_repair 次后仍失败
    """
    # 初始消息：只有一条 user prompt
    messages: list[dict] = [{"role": "user", "content": prompt}]
    last_error: Exception | None = None

    # 循环最多 max_repair + 1 次（首轮 + 修复轮）
    for attempt in range(max_repair + 1):
        # 调用模型（首轮只有 prompt，修复轮会带上历史消息）
        result = chat_fn(messages, **chat_kwargs)
        # 兼容两种返回：ChatResult 对象（有 .content）或纯字符串
        raw = getattr(result, "content", result)

        try:
            # 尝试解析 + 校验，成功则直接返回
            return model_from_text(raw, model), attempt + 1
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            # 失败：记录错误，进入修复流程
            last_error = exc
            log.warning("结构化解析失败（第 %d 次）: %s", attempt + 1, exc)

            # 已用完所有修复次数，放弃
            if attempt >= max_repair:
                break

            # 构造修复消息，追加到对话历史
            # 下一轮模型能看到：自己的错误输出 + 具体错误信息
            messages += repair_messages(raw, exc)  # type: ignore[arg-type]

    # 循环结束仍未成功，抛出带最后错误的异常
    raise StructuredOutputError(f"修复 {max_repair} 次后仍失败: {last_error}")
