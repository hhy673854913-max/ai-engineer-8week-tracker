"""M3 端到端演示。

用法（仓库根目录，离线可跑）：
    python -m code.week08.activity_assistant.demo --offline

接真实模型：
    python -m code.week08.activity_assistant.demo --requirement "做一个情人节双人组队活动，奖励是限定皮肤"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.week08.activity_assistant.graph import run_pipeline  # noqa: E402

DEFAULT_REQUIREMENT = "做一个情人节双人组队活动，奖励是限定皮肤"


def main() -> int:
    parser = argparse.ArgumentParser(description="M3 活动搭建助手")
    parser.add_argument("--requirement", default=DEFAULT_REQUIREMENT)
    parser.add_argument("--offline", action="store_true", help="不调用模型，用规则版跑通链路")
    parser.add_argument("--out", type=Path, default=ROOT / "runs")
    args = parser.parse_args()

    client = None
    if not args.offline:
        from code.shared.llm_client import get_client

        client = get_client()

    state = run_pipeline(args.requirement, offline=args.offline, client=client, out_root=args.out)

    print("=" * 60)
    print(f"需求：{args.requirement}")
    print(f"运行目录：{state['run_dir']}")
    print("-" * 60)
    print("需求解析：")
    print(json.dumps(state["requirement"].model_dump(), ensure_ascii=False, indent=2))
    if state["blocked_by"]:
        print(f"\n⚠ 待澄清信息：{state['blocked_by']}（真实系统会中断等待人工回答）")
    print("-" * 60)
    print(f"代码文件：{[f['path'] for f in state['code'].files]}")
    print(f"自检结论：{state['review'].verdict}，问题 {len(state['review'].issues)} 条")
    print(f"总耗时：{sum(s['ms'] for s in state['timeline'])} ms")
    print(f"\n用浏览器打开：{Path(state['run_dir']) / state['code'].entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
