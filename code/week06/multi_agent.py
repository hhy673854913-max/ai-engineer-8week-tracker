"""Day 29 · 多智能体协作：研究员 + 审稿员两角色流水线。

用 LangGraph 实现"研究员产出初稿 → 审稿员评分 → 研究员修订 → 终稿"，
演示多智能体的真实成本与收益。

用法：
    python -m code.week06.multi_agent "AI 在活动页生成中的应用"
    python -m code.week06.multi_agent "AI 在活动页生成中的应用" --rounds 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client

# LangGraph 可选依赖
try:
    from langgraph.graph import StateGraph, START, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 角色契约（Day 29 核心：每个角色必须有可验收的输出）
# ---------------------------------------------------------------------------


class Draft(BaseModel):
    """研究员的输出契约。"""
    title: str
    sections: list[dict]  # [{heading, content}]
    citations: list[str]  # 引用的资料编号


class Review(BaseModel):
    """审稿员的输出契约。"""
    scores: dict[str, int]  # {clarity, accuracy, completeness}
    issues: list[str]
    verdict: str  # "pass" | "revise"


class WriterState(TypedDict):
    topic: str
    draft: dict | None
    review: dict | None
    round: int
    history: list[str]  # 每轮审稿意见摘要


MAX_ROUNDS = 2

RESEARCH_PROMPT = """你是一位技术研究员。请围绕主题「{topic}」撰写一份结构化的研究报告初稿。

要求：
1. 标题清晰，包含 3-5 个章节，每个章节有 heading 和 content
2. 内容要具体，避免空泛的套话
3. 每个章节末尾标注资料来源编号（如 [资料1]）
4. 只输出 JSON，格式：
   {{"title": "...", "sections": [{{"heading": "...", "content": "..."}}], "citations": ["资料1", "资料2"]}}

{feedback}"""

REVIEW_PROMPT = """你是一位严格的审稿员。请审阅下面的研究报告初稿，从三个维度打分（1-5）：
- clarity（清晰度）：结构是否清晰、语言是否流畅
- accuracy（准确性）：内容是否可信、有无明显错误
- completeness（完整性）：是否覆盖了主题的关键方面

同时列出具体的问题（issues），每条问题要指出所在章节和修改建议。

只输出 JSON，格式：
{{"scores": {{"clarity": 4, "accuracy": 3, "completeness": 4}}, "issues": ["章节2缺少具体数据支撑"], "verdict": "revise"}}

verdict 只能是 "pass"（可以发布）或 "revise"（需要修订）。

待审初稿：
{draft}"""


# ---------------------------------------------------------------------------
# 多智能体图
# ---------------------------------------------------------------------------


class MultiAgentWriter:
    """研究员 + 审稿员两角色协作。"""

    def __init__(self, llm: Any, max_rounds: int = MAX_ROUNDS):
        self.llm = llm
        self.max_rounds = max_rounds
        if not HAS_LANGGRAPH:
            raise ImportError("缺少 langgraph，请执行: uv pip install langgraph")

    # -- 节点 -----------------------------------------------------------

    def researcher(self, state: WriterState) -> dict[str, Any]:
        """研究员：根据主题和审稿反馈产出/修订初稿。"""
        feedback = ""
        if state.get("review") and state["review"].get("issues"):
            issues = "\n".join(f"- {i}" for i in state["review"]["issues"])
            feedback = f"上一轮审稿意见：\n{issues}\n\n请针对以上意见修订初稿。"

        prompt = RESEARCH_PROMPT.format(topic=state["topic"], feedback=feedback)
        raw = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        draft = json.loads(raw.content)
        return {"draft": draft, "round": state["round"] + 1}

    def reviewer(self, state: WriterState) -> dict[str, Any]:
        """审稿员：对初稿评分并给出修改意见。"""
        draft_text = json.dumps(state["draft"], ensure_ascii=False, indent=2)
        prompt = REVIEW_PROMPT.format(draft=draft_text)
        raw = self.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0,
        )
        review = json.loads(raw.content)
        return {"review": review}

    # -- 路由 -----------------------------------------------------------

    def should_revise(self, state: WriterState) -> str:
        if state["review"]["verdict"] == "pass":
            return "done"
        if state["round"] >= self.max_rounds:
            return "done"
        return "revise"

    # -- 组装 -----------------------------------------------------------

    def build(self):
        g = StateGraph(WriterState)
        g.add_node("researcher", self.researcher)
        g.add_node("reviewer", self.reviewer)
        g.add_edge(START, "researcher")
        g.add_edge("researcher", "reviewer")
        g.add_conditional_edges("reviewer", self.should_revise, {"revise": "researcher", "done": END})
        return g.compile()

    def run(self, topic: str) -> dict[str, Any]:
        app = self.build()
        result = app.invoke(
            {"topic": topic, "draft": None, "review": None, "round": 0, "history": []}
        )
        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="研究员 + 审稿员多智能体")
    parser.add_argument("topic", nargs="?", default="AI 在活动页生成中的应用")
    parser.add_argument("--rounds", type=int, default=MAX_ROUNDS, help="最大修订轮数")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON 结果")
    args = parser.parse_args()

    if not HAS_LANGGRAPH:
        print("缺少 langgraph，请执行: uv pip install langgraph")
        return 1

    llm = get_client()
    writer = MultiAgentWriter(llm, max_rounds=args.rounds)
    result = writer.run(args.topic)

    print(f"\n=== 主题: {result['topic']} ===")
    print(f"=== 修订轮数: {result['round']} ===\n")

    if result.get("draft"):
        print("【终稿标题】", result["draft"].get("title"))
        print(f"【章节数】 {len(result['draft'].get('sections', []))}")
        for sec in result["draft"].get("sections", []):
            print(f"  - {sec.get('heading')}")

    if result.get("review"):
        scores = result["review"].get("scores", {})
        print(f"\n【审稿评分】 clarity={scores.get('clarity')} accuracy={scores.get('accuracy')} completeness={scores.get('completeness')}")
        print(f"【审稿结论】 {result['review'].get('verdict')}")
        issues = result["review"].get("issues", [])
        if issues:
            print("【审稿意见】")
            for i in issues:
                print(f"  - {i}")

    if args.json:
        print("\n=== 完整 JSON ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
