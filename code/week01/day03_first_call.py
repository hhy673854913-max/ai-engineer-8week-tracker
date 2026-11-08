"""Day 03 · 第一次调用：看清 Chat Completions 的返回结构。

用法：
    python code/week01/day03_first_call.py "用一句话解释 RAG"
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client  # noqa: E402


def main() -> int:
    question = " ".join(sys.argv[1:]) or "用一句话解释 RAG"
    client = get_client()
    result = client.chat(
        [
            {"role": "system", "content": "你是严谨的中文技术编辑，回答不超过 3 句。"},
            {"role": "user", "content": question},
        ],
        temperature=0.3,
        max_tokens=300,
    )

    print("=" * 60)
    print(result.content)
    print("=" * 60)
    print(f"model       : {result.model}")
    print(f"latency     : {result.latency_ms} ms")
    print(f"tokens      : in={result.usage.prompt_tokens} out={result.usage.completion_tokens}")
    print(f"cost (估算) : ¥{result.cost_cny:.6f}")
    print(f"finish      : {result.finish_reason}")
    print(f"累计用量    : {client.report()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
