"""Day 22 · 工具注册表：schema、校验、错误语义、副作用声明。

统一返回结构 {ok, data|error_code, message, retryable}，让模型能"读懂失败"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

SideEffect = Literal["read", "write", "dangerous"]

_SAFE_EXPR = re.compile(r"^[\d\s+\-*/().%]+$")


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    side_effect: SideEffect = "read"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"重复注册工具: {spec.name}")
        self._tools[spec.name] = spec

    def schemas(self, allow_dangerous: bool = False) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values() if allow_dangerous or t.side_effect != "dangerous"]

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {"ok": False, "error_code": "UNKNOWN_TOOL", "message": f"没有工具 {name}", "retryable": False}
        missing = [k for k in spec.parameters.get("required", []) if k not in args]
        if missing:
            return {"ok": False, "error_code": "BAD_ARGS", "message": f"缺少参数: {missing}", "retryable": True}
        try:
            return {"ok": True, "data": spec.func(**args)}
        except Exception as exc:  # noqa: BLE001 - 工具失败要转成模型可读的信息
            return {"ok": False, "error_code": "TOOL_ERROR", "message": str(exc), "retryable": True}


# ---------------------------------------------------------------------------
# 三个示例工具
# ---------------------------------------------------------------------------

_WEATHER = {"厦门": {"temp": 24, "text": "多云"}, "北京": {"temp": 8, "text": "晴"}}


def get_weather(city: str) -> dict[str, Any]:
    data = _WEATHER.get(city)
    if data is None:
        raise ValueError(f"未收录城市：{city}，可尝试：{'、'.join(_WEATHER)}")
    return {"city": city, **data}


def calculator(expression: str) -> dict[str, Any]:
    """只允许四则运算字符，避免 eval 注入。"""
    if not _SAFE_EXPR.match(expression):
        raise ValueError("只支持数字与 + - * / ( ) . % 运算")
    return {"expression": expression, "result": eval(expression, {"__builtins__": {}}, {})}  # noqa: S307


def search_notes(keyword: str, limit: int = 3) -> list[str]:
    notes = [
        "活动页交付从 3 天压缩到 1 天，靠的是模板化 + 自动化检查",
        "RAG 检索不准，先看分块，再看混合检索，最后才调阈值",
        "Agent 一定要有最大步数，否则会烧钱",
    ]
    return [n for n in notes if keyword in n][:limit]


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="get_weather",
            description="查询指定城市的实时天气。仅用于当前天气，不用于历史天气或预报。城市必须是中文名。",
            parameters={"type": "object", "properties": {"city": {"type": "string", "description": "城市中文名，如 厦门"}}, "required": ["city"]},
            func=get_weather,
        )
    )
    registry.register(
        ToolSpec(
            name="calculator",
            description="计算四则运算表达式。用于任何需要精确计算的场景，不要自己心算。",
            parameters={"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
            func=calculator,
        )
    )
    registry.register(
        ToolSpec(
            name="search_notes",
            description="在本地学习笔记中按关键词检索。",
            parameters={
                "type": "object",
                "properties": {"keyword": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 5}},
                "required": ["keyword"],
            },
            func=search_notes,
        )
    )
    return registry


if __name__ == "__main__":
    reg = default_registry()
    print(json.dumps(reg.call("get_weather", {"city": "厦门"}), ensure_ascii=False))
    print(json.dumps(reg.call("get_weather", {"city": "拉萨"}), ensure_ascii=False))
    print(json.dumps(reg.call("calculator", {"expression": "24-8"}), ensure_ascii=False))
    print(json.dumps(reg.call("missing_tool", {}), ensure_ascii=False))
