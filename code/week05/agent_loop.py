"""Day 21 · 手写 ReAct Agent 循环（约 100 行）。

核心不是"调模型"，而是三件事：工具回传、错误隔离、终止条件。

用法：
    python -m code.week05.agent_loop "厦门和北京温差多少？给穿衣建议"
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client  # noqa: E402
from code.week05.tools import ToolRegistry, default_registry  # noqa: E402

SYSTEM = """你是一个严谨的助手。你可以调用工具来获取信息或计算。

规则：
1. 需要事实（天气、计算、笔记）时必须调用工具，不要凭记忆回答；
2. 工具返回错误时，根据错误信息调整参数或换工具，最多尝试 2 次；
3. 信息足够后直接给出最终答案，不要多余解释。"""


@dataclass
class Step:
    n: int
    tools: list[str] = field(default_factory=list)
    args: list[dict] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    elapsed_ms: int = 0


class Agent:
    def __init__(self, client: Any, registry: ToolRegistry, max_steps: int = 8):
        self.client = client
        self.registry = registry
        self.max_steps = max_steps
        self.trace: list[Step] = []

    def run(self, question: str) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ]
        for step_no in range(1, self.max_steps + 1):
            t0 = time.perf_counter()
            result = self.client.chat(messages, tools=self.registry.schemas(), temperature=0)
            tool_calls = result.tool_calls
            if not tool_calls:
                self.trace.append(Step(step_no, elapsed_ms=int((time.perf_counter() - t0) * 1000)))
                return result.content

            step = Step(step_no)
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments},
                        }
                        for c in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                observation = self.registry.call(name, args)
                step.tools.append(name)
                step.args.append(args)
                step.observations.append(json.dumps(observation, ensure_ascii=False)[:500])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(observation, ensure_ascii=False),
                    }
                )
            step.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            self.trace.append(step)

        return "已达到最大步数，未能完成任务。请缩小问题范围后重试。"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", default="厦门现在多少度？换算成华氏度给我")
    parser.add_argument("--trace", type=Path, default=ROOT / "output" / "agent_trace.jsonl")
    args = parser.parse_args()

    client = get_client()
    agent = Agent(client, default_registry())
    answer = agent.run(args.question)
    print("\n=== 最终答案 ===")
    print(answer)

    args.trace.parent.mkdir(parents=True, exist_ok=True)
    with args.trace.open("w", encoding="utf-8") as f:
        for step in agent.trace:
            f.write(json.dumps(asdict(step), ensure_ascii=False) + "\n")
    print(f"\n轨迹已写入 {args.trace}（{len(agent.trace)} 步）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
