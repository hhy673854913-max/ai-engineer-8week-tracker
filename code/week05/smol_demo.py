"""Day 23 · smolagents 对照实践：CodeAgent vs 手写 Agent。

需要先安装：
    uv pip install smolagents

用法：
    python -m code.week05.smol_demo "厦门和北京现在温差多少？给穿衣建议"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client, load_config


def get_weather(city: str) -> dict:
    """查询城市实时天气。

    Args:
        city: 城市中文名，如 厦门
    """
    db = {"厦门": {"temp": 24, "text": "多云"}, "北京": {"temp": 8, "text": "晴"}}
    return db.get(city, {"error": f"未收录城市: {city}"})


def run_smolagents(question: str) -> str | None:
    try:
        from smolagents import CodeAgent, OpenAIServerModel, tool
    except ImportError:
        print("未安装 smolagents，请执行: uv pip install smolagents")
        return None

    cfg = load_config()

    @tool
    def weather_tool(city: str) -> dict:
        """查询城市实时天气。

        Args:
            city: 城市中文名，如 厦门
        """
        return get_weather(city)

    model = OpenAIServerModel(
        model_id=cfg.model,
        api_base=cfg.base_url,
        api_key=cfg.api_key,
    )
    agent = CodeAgent(tools=[weather_tool], model=model, max_steps=6)

    t0 = time.perf_counter()
    result = agent.run(question)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    print(f"\n[smolagents] 耗时: {elapsed_ms} ms")
    print(f"[smolagents] 结果: {result}")
    return result


def run_handwritten(question: str) -> str:
    from code.week05.agent_loop import Agent
    from code.week05.tools import default_registry

    client = get_client()
    agent = Agent(client, default_registry(), max_steps=8)

    t0 = time.perf_counter()
    answer = agent.run(question)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    print(f"\n[手写 Agent] 耗时: {elapsed_ms} ms")
    print(f"[手写 Agent] 步数: {len(agent.trace)}")
    print(f"[手写 Agent] 结果: {answer}")
    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description="smolagents 对照实验")
    parser.add_argument("question", nargs="?", default="厦门和北京现在温差多少？给穿衣建议")
    parser.add_argument("--hand-only", action="store_true", help="只跑手写版")
    parser.add_argument("--smol-only", action="store_true", help="只跑 smolagents 版")
    args = parser.parse_args()

    question = args.question
    print(f"任务: {question}\n")

    if not args.smol_only:
        print("=== 手写 Agent ===")
        run_handwritten(question)
        print()

    if not args.hand_only:
        print("=== smolagents CodeAgent ===")
        result = run_smolagents(question)
        if result is None:
            print("（跳过 smolagents，未安装依赖）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
