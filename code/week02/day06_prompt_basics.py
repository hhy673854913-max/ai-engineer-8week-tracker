"""Day 06 · 提示词两大原则：三版 prompt 对照实验台。

对应 docs/week-02/day-06.md 任务 1/2/3：
- 同一批 10 条玩家评论，分别用 v1_模糊 / v2_清晰 / v3_清晰+思考 三版 prompt 跑一遍
- 结果落 CSV 到 output/prompt_exp_YYYYMMDD.csv，人工按 准确/可用/不可用 三档打分
- run_experiment 设计为可复用：Day 08 迭代 M1 抽取模板时直接换 CASES 和 PROMPTS

用法：
    python code/week02/day06_prompt_basics.py                 # 三版 × 10 条全量
    python code/week02/day06_prompt_basics.py --prompt v2_清晰  # 只跑一版
    python code/week02/day06_prompt_basics.py --limit 3       # 只跑前 3 条样本调试
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import LLMError, get_client  # noqa: E402

# ---------------------------------------------------------------------------
# 固定样本：10 条真实风格的玩家评论（正面/中性/负面混合，含一条边界样本）
# 样本固定是评估的前提：改 prompt 不换样本，结果才可横向对比
# ---------------------------------------------------------------------------

CASES: list[dict] = [
    {
        "id": "c1",
        "text": "新版本卡池爆率明显调高了，三十抽出了两个 SSR，终于当了一次欧皇，好评！",
    },
    {
        "id": "c2",
        "text": "更新后登录界面一直转圈，重启五次才进去，官方能不能管管服务器？",
    },
    {
        "id": "c3",
        "text": "玩了三个月，日常就是清体力做委托，感觉内容有点重复，但也找不到替代的手游。",
    },
    {
        "id": "c4",
        "text": "剧情第五章的反转写得太好了，配音也到位，就是章节之间的衔接有点生硬。",
    },
    {
        "id": "c5",
        "text": "客服处理账号找回的速度很慢，提交工单三天才回复，不过最后问题解决了。",
    },
    {
        "id": "c6",
        "text": "萌新求问，体力每天几点刷新？商店里那个金色箱子值得买吗？",
    },
    {
        "id": "c7",
        "text": "PVP 匹配机制是不是有问题？我青铜段位天天排到钻石，体验极差，已卸载。",
    },
    {
        "id": "c8",
        "text": "周年庆福利还可以，登录就送十连，就是活动 UI 太花哨，找了半天入口。",
    },
    {
        "id": "c9",
        "text": "联动活动的关卡设计挺有创意，奖励也丰厚，希望下次联动能早点公布角色名单。",
    },
    {
        "id": "c10",
        "text": "这游戏画面还行，说不上惊艳但也过得去，先玩着看看吧。",
    },
]

# ---------------------------------------------------------------------------
# 三版 prompt：模糊 → 清晰 → 清晰+思考
# v3 与 v2 的唯一差异是增加了 analysis 字段，方便隔离"给思考时间"这一个变量的效果
# ---------------------------------------------------------------------------

PROMPTS: dict[str, str] = {
    "v1_模糊": "总结下面这段内容，提取主题和情感。\n{text}",
    "v2_清晰": (
        "你是游戏社区运营分析师。阅读下面的玩家评论，完成三件事：\n"
        "1. 用不超过 40 字概括这条评论的主要诉求；\n"
        "2. 判断情感倾向，只能选：正面 / 中性 / 负面；\n"
        "3. 列出 1-3 个关键词。\n"
        "只输出 JSON，不要 markdown 代码块，不要任何解释。\n"
        'JSON 结构：{{"summary": "", "sentiment": "", "keywords": []}}\n'
        "评论：\n<review>{text}</review>"
    ),
    "v3_清晰+思考": (
        "你是游戏社区运营分析师。阅读下面的玩家评论，完成三件事：\n"
        "1. 用不超过 40 字概括这条评论的主要诉求；\n"
        "2. 判断情感倾向，只能选：正面 / 中性 / 负面；\n"
        "3. 列出 1-3 个关键词。\n"
        "先在 analysis 字段写 2 句话分析依据（引用原文关键词），再填其余字段。\n"
        "只输出 JSON，不要 markdown 代码块，不要任何解释。\n"
        'JSON 结构：{{"analysis": "", "summary": "", "sentiment": "", "keywords": []}}\n'
        "评论：\n<review>{text}</review>"
    ),
}

# 人工评分档（任务 1 要求）：留空由人填，不参与自动统计
SCORE_CHOICES = ("准确", "可用", "不可用", "")

OUTPUT_DIR = ROOT / "output"


# ---------------------------------------------------------------------------
# 实验台核心：可复用的单 prompt 批量运行函数
# ---------------------------------------------------------------------------


def run_experiment(
    prompt_id: str,
    cases: list[dict],
    *,
    client=None,
    temperature: float = 0.0,
    max_tokens: int = 500,
) -> list[dict]:
    """对一批样本跑同一个 prompt，返回带用量信息的原始结果。

    Day 08 复用方式：把 cases 换成 20 条资讯正文、PROMPTS 换成 M1 抽取模板，
    函数本身不需要改。失败样本不中断实验，记录 error 字段后继续。
    """
    if client is None:
        client = get_client()
    if prompt_id not in PROMPTS:
        raise KeyError(f"未知 prompt_id: {prompt_id}，可选: {', '.join(PROMPTS)}")

    results = []
    for c in cases:
        prompt = PROMPTS[prompt_id].format(text=c["text"])
        t0 = time.perf_counter()
        try:
            resp = client.chat(
                [{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            results.append({
                "id": c["id"],
                "prompt": prompt_id,
                "raw": resp.content,
                "latency_ms": resp.latency_ms,
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "cost_cny": round(resp.cost_cny, 6),
                "error": "",
            })
        except LLMError as exc:
            # 单条失败不中断整批：实验数据的完整性比单条结果更重要
            results.append({
                "id": c["id"],
                "prompt": prompt_id,
                "raw": "",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cost_cny": 0.0,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return results


# ---------------------------------------------------------------------------
# CSV 落盘 + 汇总
# ---------------------------------------------------------------------------


def save_csv(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # score 列留空供人工填写，实现"代码跑数据、人来做裁判"的分工
    fields = [
        "id", "prompt", "raw", "score", "error",
        "latency_ms", "prompt_tokens", "completion_tokens", "cost_cny",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow({"score": "", **r})


def print_summary(results: list[dict]) -> None:
    """按 prompt 版本汇总：条数 / 失败数 / 平均耗时 / 平均成本。

    通过率需要人工评分后才能算，这里先给物理指标；
    评完分后可用 --stats 重新统计通过率。
    """
    by_prompt: dict[str, list[dict]] = {}
    for r in results:
        by_prompt.setdefault(r["prompt"], []).append(r)

    print(f"\n{'═' * 60}")
    print(f"{'prompt':<14} {'条数':>4} {'失败':>4} {'平均ms':>8} {'平均成本':>12}")
    print("─" * 60)
    for pid, rows in by_prompt.items():
        n = len(rows)
        failed = sum(1 for r in rows if r["error"])
        avg_ms = sum(r["latency_ms"] for r in rows) / n
        avg_cost = sum(r["cost_cny"] for r in rows) / n
        print(f"{pid:<14} {n:>4} {failed:>4} {avg_ms:>8.0f} ¥{avg_cost:>11.6f}")
    print("═" * 60)
    print("提示：打开 CSV 填好 score 列后，用 --stats <csv路径> 统计通过率")


def stats_from_csv(path: Path) -> None:
    """读取已人工评分的 CSV，按 prompt 版本统计三档分布与通过率。

    通过率口径：准确 + 可用 记为通过（与 Day 08 M1 的字段口径保持一致）。
    """
    by_prompt: dict[str, dict[str, int]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            s = (row.get("score") or "").strip()
            bucket = by_prompt.setdefault(row["prompt"], {"准确": 0, "可用": 0, "不可用": 0, "未评": 0, "总": 0})
            bucket["总"] += 1
            bucket[s if s in ("准确", "可用", "不可用") else "未评"] += 1

    print(f"\n评分统计：{path.name}")
    print(f"{'prompt':<14} {'准确':>4} {'可用':>4} {'不可用':>5} {'未评':>4} {'通过率':>8}")
    print("─" * 60)
    for pid, b in by_prompt.items():
        graded = b["准确"] + b["可用"] + b["不可用"]
        pass_rate = (b["准确"] + b["可用"]) / graded * 100 if graded else 0.0
        print(f"{pid:<14} {b['准确']:>4} {b['可用']:>4} {b['不可用']:>5} {b['未评']:>4} {pass_rate:>7.1f}%")
    print("通过率口径：（准确 + 可用）/ 已评条数")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Day06 提示词三版对照实验台")
    parser.add_argument(
        "--prompt", action="append", default=None,
        help=f"只跑指定版本（可多次传入），可选: {', '.join(PROMPTS)}；默认跑全部",
    )
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条样本（调试用）")
    parser.add_argument("--out", type=str, default="", help="CSV 输出路径（默认 output/prompt_exp_YYYYMMDD.csv）")
    parser.add_argument("--stats", type=str, default="", metavar="CSV", help="跳过实验，只统计已评分 CSV 的通过率")
    args = parser.parse_args(argv)

    if args.stats:
        stats_from_csv(Path(args.stats))
        return 0

    prompt_ids = args.prompt or list(PROMPTS)
    for pid in prompt_ids:
        if pid not in PROMPTS:
            print(f"错误：未知 prompt {pid!r}，可选: {', '.join(PROMPTS)}", file=sys.stderr)
            return 2

    cases = CASES[: args.limit] if args.limit > 0 else CASES
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"prompt_exp_{datetime.now():%Y%m%d}.csv"

    client = get_client()
    all_results: list[dict] = []
    for pid in prompt_ids:
        print(f"[{pid}] 开始实验：{len(cases)} 条样本 …", flush=True)
        results = run_experiment(pid, cases, client=client)
        errors = sum(1 for r in results if r["error"])
        print(f"[{pid}] 完成：{len(results) - errors} 成功 / {errors} 失败", flush=True)
        all_results.extend(results)

    save_csv(all_results, out_path)
    print_summary(all_results)
    print(f"\n结果已写入：{out_path}")
    print(f"累计用量：{json.dumps(client.report(), ensure_ascii=False)}")
    print("下一步：打开 CSV，对每条 raw 人工填 score 列（准确/可用/不可用），然后跑 --stats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
