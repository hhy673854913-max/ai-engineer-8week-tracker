"""Day 08 · 抽取提示词 v1 → v2 对照实验 + 自洽性实验。

对应 docs/week-02/day-08.md 四个任务：
- 任务 1/2：v1 vs v2 跑同一批样本，落 CSV 供人工评字段准确率
- 任务 3：对 credibility 做 N 次采样（温度 > 0），观察分数方差
- 任务 4：模板渲染器演示（prompts/render.py），踩 str.format 花括号的坑

用法（仓库根目录）：
    python code/week02/day08_extract_prompt.py                  # v1/v2 对照，落 CSV
    python code/week02/day08_extract_prompt.py --limit 5        # 调试：只跑前 5 条
    python code/week02/day08_extract_prompt.py --consistency 5  # 自洽性实验
    python code/week02/day08_extract_prompt.py --stats output/day08_xxx.csv  # 统计已评分 CSV

说明：字段准确率需要人工判断（title 是否忠实原文等），代码负责跑出原始数据、
自动统计"可自动判"的指标（解析成功率 / 各字段 null 率），score 列留空由人填。
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client  # noqa: E402
from code.shared.structured import model_from_text  # noqa: E402
from code.week02.prompts.extract import CHANGELOG, TEMPLATES, VERSION  # noqa: E402
from code.week02.prompts.render import render  # noqa: E402

OUTPUT_DIR = ROOT / "output"
MOCK_NEWS = ROOT / "data" / "mock_news.json"

FIELDS = ["title", "summary", "category", "entities", "credibility"]


# ---------------------------------------------------------------------------
# 输出契约：与 TEMPLATES["extract_v2"] 的 JSON 结构一一对应
# ---------------------------------------------------------------------------


class ExtractResult(BaseModel):
    analysis: str | None = None
    title: str | None = Field(default=None, description="不超过 30 字")
    summary: str | None = Field(default=None, description="不超过 80 字")
    entities: list[str] | None = None
    category: Literal["融资", "产品", "政策", "技术", "其他"] | None = None
    credibility: int | None = Field(default=None, ge=0, le=100)


# ---------------------------------------------------------------------------
# 实验核心
# ---------------------------------------------------------------------------


def extract_one(text: str, template_id: str, *, temperature: float = 0.0) -> ExtractResult:
    """渲染模板 → 调模型 → Pydantic 校验。失败抛异常由上层隔离。"""
    client = get_client()
    prompt = render(TEMPLATES[template_id], text=text[:2000])  # 成本规则：只发前 2000 字
    resp = client.chat(
        [{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=800,
    )
    return model_from_text(resp.content, ExtractResult)


def run_compare(samples: list[dict], template_ids: list[str], *, limit: int = 0) -> list[dict]:
    """同一批样本跑多个模板版本，返回带原始输出的结果行。"""
    rows: list[dict] = []
    for tid in template_ids:
        cases = samples[:limit] if limit > 0 else samples
        print(f"[{tid}] 开始：{len(cases)} 条样本 …", flush=True)
        for c in cases:
            row: dict = {
                "id": c["url"], "template": tid, "raw": "", "error": "",
                "title": "", "summary": "", "category": "",
                "entities": "", "credibility": "",
                "analysis": "",
            }
            # 每个字段一列 score（title_score / summary_score / ...），留空由人填
            for f in FIELDS:
                row[f + "_score"] = ""
            try:
                r = extract_one(c["content"], tid)
                row.update({
                    "raw": r.model_dump_json(),
                    "title": r.title or "",
                    "summary": r.summary or "",
                    "category": r.category or "",
                    "entities": json.dumps(r.entities or [], ensure_ascii=False),
                    "credibility": r.credibility if r.credibility is not None else "",
                    "analysis": r.analysis or "",
                })
            except Exception as exc:  # noqa: BLE001 - 单条失败不中断，记 error 继续
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
        ok = sum(1 for r in rows if r["template"] == tid and not r["error"])
        print(f"[{tid}] 完成：{ok} 成功 / {len(cases) - ok} 失败", flush=True)
    return rows


def run_consistency(samples: list[dict], n: int, *, limit: int = 0) -> None:
    """任务 3：对 credibility 做 n 次采样，观察方差。方差大 = 评分标准不可执行。"""
    cases = samples[:limit] if limit > 0 else samples
    print(f"自洽性实验：{len(cases)} 条样本 × {n} 次采样（temperature=0.7）")
    print(f"{'url':<44} {'min':>4} {'max':>4} {'mean':>7} {'stdev':>7}  判定")
    print("─" * 90)
    high_variance = 0
    for c in cases:
        scores: list[int] = []
        for _ in range(n):
            try:
                r = extract_one(c["content"], "extract_v2", temperature=0.7)
                if r.credibility is not None:
                    scores.append(r.credibility)
            except Exception as exc:  # noqa: BLE001
                print(f"  采样失败（{type(exc).__name__}），跳过")
        if len(scores) < 2:
            print(f"{c['url']:<44} 样本不足，跳过")
            continue
        stdev = statistics.stdev(scores)
        # 阈值 15 分来自 Day 08：超过说明评分标准要拆得更具体
        verdict = "方差过大，需细化标准" if stdev > 15 else "ok"
        if stdev > 15:
            high_variance += 1
        print(f"{c['url']:<44} {min(scores):>4} {max(scores):>4} "
              f"{statistics.mean(scores):>7.1f} {stdev:>7.1f}  {verdict}")
    print("─" * 90)
    print(f"方差 > 15 分的样本：{high_variance}/{len(cases)}")
    print("修正方向：把'信源权威性'拆成具体清单（官方公告 40 / 权威媒体 30 / 自媒体 10）")


# ---------------------------------------------------------------------------
# CSV 落盘与统计
# ---------------------------------------------------------------------------


def save_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "template", "raw", "error", "analysis",
              *FIELDS, *(f + "_score" for f in FIELDS)]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def print_auto_stats(rows: list[dict]) -> None:
    """可自动判的指标：解析成功率 + 各字段 null 率。

    null 率异常高 → 模型在逃避抽取；异常低 → 可能学会了"永远有话说"（幻觉）。
    """
    by_tpl: dict[str, list[dict]] = {}
    for r in rows:
        by_tpl.setdefault(r["template"], []).append(r)
    print(f"\n自动指标（无需人工评分）")
    print(f"{'template':<12} {'条数':>4} {'失败':>4} {'成功率':>7}  各字段 null 率")
    for tid, rs in by_tpl.items():
        n = len(rs)
        failed = sum(1 for r in rs if r["error"])
        null_rates = []
        for f in FIELDS:
            nulls = sum(1 for r in rs if not r["error"] and r[f] in ("", "[]"))
            null_rates.append(f"{f}={nulls / max(n - failed, 1):.0%}")
        print(f"{tid:<12} {n:>4} {failed:>4} {(n - failed) / n:>7.0%}  {' '.join(null_rates)}")


def stats_from_csv(path: Path) -> None:
    """人工评完分后调用：按模板统计各字段准确率（口径同 Day 08 表格）。"""
    by_tpl: dict[str, dict[str, int]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("error"):
                continue
            bucket = by_tpl.setdefault(row["template"], {f: [0, 0] for f in FIELDS})  # [对, 总]
            for f in FIELDS:
                s = (row.get(f + "_score") or "").strip()
                if s:
                    bucket[f][1] += 1
                    if s in ("1", "对", "准确"):
                        bucket[f][0] += 1
    print(f"\n字段准确率：{path.name}（score 列填 1/0）")
    for tid, bucket in by_tpl.items():
        cells = []
        for f in FIELDS:
            ok, total = bucket[f]
            cells.append(f"{f} {ok}/{total}={ok / total:.0%}" if total else f"{f} 未评")
        print(f"  {tid}: " + "  ".join(cells))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Day08 抽取模板 v1/v2 对照 + 自洽性实验")
    parser.add_argument("--templates", nargs="+", default=["extract_v1", "extract_v2"],
                        choices=sorted(TEMPLATES), help="要对照的模板版本")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条样本（调试用）")
    parser.add_argument("--consistency", type=int, default=0, metavar="N",
                        help="自洽性实验：credibility 采样 N 次")
    parser.add_argument("--out", type=str, default="", help="CSV 输出路径")
    parser.add_argument("--stats", type=str, default="", metavar="CSV", help="统计已评分 CSV")
    args = parser.parse_args(argv)

    if args.stats:
        stats_from_csv(Path(args.stats))
        return 0

    samples = json.loads(MOCK_NEWS.read_text(encoding="utf-8"))
    print(f"样本：{MOCK_NEWS}（{len(samples)} 条）｜模板版本 {VERSION}：{CHANGELOG}")

    if args.consistency > 0:
        run_consistency(samples, args.consistency, limit=args.limit)
        return 0

    rows = run_compare(samples, args.templates, limit=args.limit)
    out_path = Path(args.out) if args.out else OUTPUT_DIR / f"day08_{datetime.now():%Y%m%d}.csv"
    save_csv(rows, out_path)
    print_auto_stats(rows)
    print(f"\n结果已写入：{out_path}")
    print("下一步：打开 CSV，对各字段填 *_score 列（1=准确, 0=不准确），然后跑 --stats")
    print(f"累计用量：{json.dumps(get_client().report(), ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
