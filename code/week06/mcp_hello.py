"""Day 26 · 最小 MCP Server：一个工具 + 一个资源 + 一个提示模板。

调试：
    uv run mcp dev code/week06/mcp_hello.py
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello")


@mcp.tool()
def add(a: int, b: int) -> int:
    """两数相加。

    Args:
        a: 第一个数
        b: 第二个数
    """
    return a + b


@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """返回一句问候。"""
    return f"你好，{name}！"


@mcp.prompt()
def summarize(text: str) -> str:
    """摘要提示模板。"""
    return f"请用 3 句话总结下面的内容：\n{text}"


if __name__ == "__main__":
    mcp.run()  # 默认 stdio
