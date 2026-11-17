"""Day 24 · LangGraph 状态机 Agent：节点 + 条件边 + 检查点。

理论要点：
1. 状态是唯一的真相源，节点是纯函数
2. add_conditional_edges 按状态路由，比 while 循环更可观测
3. MemorySaver 让进程挂了能恢复（生产换 SqliteSaver）

用法：
    python -m code.week05.langgraph_agent "厦门天气如何"
    python -m code.week05.langgraph_agent --graph  # 打印 mermaid 状态图
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client
from code.week05.tools import default_registry, ToolRegistry

SYSTEM = """你是一个严谨的助手。需要事实（天气、计算、笔记）时必须调用工具，不要凭记忆回答。
信息足够后直接给出最终答案，不要多余解释。"""

# LangGraph 可选依赖
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    from langgraph.checkpoint.memory import MemorySaver
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    question: str
    tool_calls_count: int
    final_answer: str | None


class LangGraphAgent:
    """用 LangGraph 重写 Day 22 的多工具 Agent。"""

    def __init__(self, llm: Any, registry: ToolRegistry, max_steps: int = 8):
        self.llm = llm
        self.registry = registry
        self.max_steps = max_steps
        if not HAS_LANGGRAPH:
            raise ImportError("缺少 langgraph，请执行: uv pip install langgraph")

    # -- 节点：纯函数 ---------------------------------------------------
    @staticmethod
    def _to_openai_messages(messages: list[Any]) -> list[dict[str, Any]]:
        """LangGraph state 里的消息可能是 BaseMessage / dict / tuple，统一转成 OpenAI dict。"""
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, dict):
                out.append(m)
                continue
            if isinstance(m, tuple) and len(m) == 2:
                out.append({"role": m[0], "content": m[1]})
                continue
            role = getattr(m, "type", None) or getattr(m, "role", None)
            # langchain BaseMessage.type: human/assistant/system/tool/...
            mapping = {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}
            role = mapping.get(str(role), str(role))
            content = getattr(m, "content", "") or ""
            msg: dict[str, Any] = {"role": role, "content": content}
            tool_calls = getattr(m, "tool_calls", None)
            if tool_calls:
                msg["tool_calls"] = [
                    {"id": c.get("id"), "type": "function",
                     "function": {"name": c.get("name"), "arguments": c.get("args")}}
                    if isinstance(c, dict) else
                    {"id": getattr(c, "id", ""), "type": "function",
                     "function": {"name": getattr(getattr(c, "function", None), "name", ""),
                                  "arguments": getattr(getattr(c, "function", None), "arguments", "")}}
                    for c in tool_calls
                ]
            tool_call_id = getattr(m, "tool_call_id", None)
            if tool_call_id:
                msg["tool_call_id"] = tool_call_id
            out.append(msg)
        return out

    def call_model(self, state: AgentState) -> dict[str, Any]:
        """调用 LLM，看它是想调工具还是直接回答。"""
        messages = self._to_openai_messages(state["messages"])
        resp = self.llm.chat(messages, tools=self.registry.schemas(), temperature=0)
        # LangGraph 的 add_messages reducer 只认 dict / BaseMessage，
        # 原始 openai SDK 对象（role=None）会导致下游 400，这里转成标准消息 dict。
        msg: dict[str, Any] = {"role": "assistant", "content": resp.content or ""}
        if resp.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in resp.tool_calls
            ]
        return {"messages": [msg]}

    @staticmethod
    def _extract_tool_calls(last: Any) -> list[tuple[str, str, str]]:
        """从消息里提取 (id, name, arguments)，兼容 dict / AIMessage / SDK 对象。"""
        raw = last.get("tool_calls") if isinstance(last, dict) else getattr(last, "tool_calls", None)
        calls: list[tuple[str, str, str]] = []
        for c in raw or []:
            if isinstance(c, dict):
                cid = c.get("id", "")
                if "function" in c:
                    fn = c.get("function") or {}
                    name, args = fn.get("name", ""), fn.get("arguments", "")
                else:
                    # langchain AIMessage tool_call 格式: {id, name, args}
                    name = c.get("name", "")
                    args_dict = c.get("args", {})
                    args = json.dumps(args_dict, ensure_ascii=False) if isinstance(args_dict, dict) else str(args_dict)
            else:
                cid = getattr(c, "id", "")
                fn = getattr(c, "function", None)
                name = getattr(fn, "name", "") if fn else ""
                args = getattr(fn, "arguments", "") if fn else ""
            calls.append((cid, name, args or "{}"))
        return calls

    def run_tools(self, state: AgentState) -> dict[str, Any]:
        """执行工具调用，把结果回传。"""
        results = []
        tool_calls = self._extract_tool_calls(state["messages"][-1])
        for cid, name, arguments in tool_calls:
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {}
            res = self.registry.call(name, args)
            results.append({
                "role": "tool",
                "tool_call_id": cid,
                "name": name,
                "content": json.dumps(res, ensure_ascii=False),
            })
        return {"messages": results, "tool_calls_count": state["tool_calls_count"] + len(results)}

    def finalize(self, state: AgentState) -> dict[str, Any]:
        """提取最终答案。"""
        last = state["messages"][-1]
        content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
        return {"final_answer": content or ""}

    # -- 条件路由 -------------------------------------------------------
    def should_continue(self, state: AgentState) -> str:
        """有 tool_calls 就去 tools 节点，否则 finalize。"""
        if self._extract_tool_calls(state["messages"][-1]):
            return "tools"
        return "finalize"

    # -- 组装 -----------------------------------------------------------
    def build(self):
        graph = StateGraph(AgentState)
        graph.add_node("agent", self.call_model)
        graph.add_node("tools", self.run_tools)
        graph.add_node("finalize", self.finalize)

        graph.add_edge(START, "agent")
        graph.add_conditional_edges("agent", self.should_continue, {"tools": "tools", "finalize": "finalize"})
        graph.add_edge("tools", "agent")
        graph.add_edge("finalize", END)

        checkpointer = MemorySaver()
        return graph.compile(checkpointer=checkpointer)

    def run(self, question: str, thread_id: str = "default") -> str:
        app = self.build()
        config = {"configurable": {"thread_id": thread_id}}
        result = app.invoke(
            {"messages": [("system", SYSTEM), ("user", question)], "question": question, "tool_calls_count": 0, "final_answer": None},
            config,
        )
        return result.get("final_answer") or "未获得答案"


def print_graph() -> None:
    """打印 mermaid 状态图。"""
    if not HAS_LANGGRAPH:
        print("缺少 langgraph")
        return
    dummy = LangGraphAgent.__new__(LangGraphAgent)
    dummy.registry = default_registry()
    dummy.llm = None
    app = LangGraphAgent.build(dummy)
    print(app.get_graph().draw_mermaid())


def main() -> int:
    parser = argparse.ArgumentParser(description="LangGraph 状态机 Agent")
    parser.add_argument("question", nargs="?", default="厦门天气如何")
    parser.add_argument("--graph", action="store_true", help="打印 mermaid 状态图")
    parser.add_argument("--thread-id", default="user-001", help="会话 ID（checkpoint 隔离）")
    args = parser.parse_args()

    if args.graph:
        print_graph()
        return 0

    if not HAS_LANGGRAPH:
        print("缺少 langgraph，请执行: uv pip install langgraph")
        return 1

    client = get_client()
    registry = default_registry()
    agent = LangGraphAgent(client, registry)
    answer = agent.run(args.question, thread_id=args.thread_id)
    print(f"\n=== 最终答案 ===")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
