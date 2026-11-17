"""Day 19 · 20 组人工测试：逐条记录 hit / answer_ok / citation_ok。

产出 CSV：output/m2_eval.csv
用法：
    python -m code.week04.m2_kb.eval_manual
    python -m code.week04.m2_kb.eval_manual --out output/m2_eval.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.week04.m2_kb.qa_chain import QAService, Answer

# 20 组测试问题（Day 18 规格：直接事实 / 口语化 / 跨段 / 专名 / 库里没有）
# 标注 gold_ids 与 gold_answer 关键词
TEST_CASES: list[dict] = [
    # 直接事实（10）
    {"q": "春节活动奖励什么时候发", "gold_ids": [], "gold_answer": "活动结束后7个工作日内"},
    {"q": "退款多久到账", "gold_ids": [], "gold_answer": "3-5个工作日"},
    {"q": "补偿标准是什么", "gold_ids": [], "gold_answer": "补偿"},
    {"q": "活动参与条件有哪些", "gold_ids": [], "gold_answer": "等级/时间"},
    {"q": "如何申请退款", "gold_ids": [], "gold_answer": "申请"},
    {"q": "SPRING2026 兑换码在哪用", "gold_ids": [], "gold_answer": "兑换"},
    {"q": "春节活动持续几天", "gold_ids": [], "gold_answer": "7天"},
    {"q": "奖励发到哪里", "gold_ids": [], "gold_answer": "邮箱/背包"},
    {"q": "活动几点开始", "gold_ids": [], "gold_answer": "20:00"},
    {"q": "退款需要什么条件", "gold_ids": [], "gold_answer": "条件"},
    # 口语化（8）
    {"q": "奖励咋还没到", "gold_ids": [], "gold_answer": "7个工作日"},
    {"q": "钱退哪去了", "gold_ids": [], "gold_answer": "原支付渠道"},
    {"q": "这活动啥时候结束", "gold_ids": [], "gold_answer": "日期"},
    {"q": "补偿咋领", "gold_ids": [], "gold_answer": "领取"},
    {"q": "码在哪输", "gold_ids": [], "gold_answer": "兑换"},
    {"q": "退不了咋办", "gold_ids": [], "gold_answer": "客服"},
    {"q": "奖励能叠加吗", "gold_ids": [], "gold_answer": "叠加"},
    {"q": "活动 bug 了有补偿吗", "gold_ids": [], "gold_answer": "补偿"},
    # 跨段（5）
    {"q": "参与条件是什么，奖励有哪些", "gold_ids": [], "gold_answer": "条件+奖励"},
    {"q": "退款条件和到账时间分别是什么", "gold_ids": [], "gold_answer": "条件+3-5个工作日"},
    {"q": "春节活动怎么参加，奖励怎么领", "gold_ids": [], "gold_answer": "参加+领取"},
    {"q": "补偿标准和申请流程是什么", "gold_ids": [], "gold_answer": "标准+流程"},
    {"q": "兑换码有效期和使用限制", "gold_ids": [], "gold_answer": "有效期+限制"},
    # 专名（4）
    {"q": "SPRING2026 兑换码使用方法", "gold_ids": [], "gold_answer": "SPRING2026"},
    {"q": "2026 春节活动规则", "gold_ids": [], "gold_answer": "2026春节"},
    {"q": "周年庆活动奖励", "gold_ids": [], "gold_answer": "周年庆"},
    {"q": "新年限定皮肤怎么得", "gold_ids": [], "gold_answer": "皮肤"},
    # 库里没有（3）
    {"q": "双十一活动规则", "gold_ids": [], "gold_answer": "资料未提及"},
    {"q": "暑假活动什么时候开", "gold_ids": [], "gold_answer": "资料未提及"},
    {"q": "万圣节皮肤返场吗", "gold_ids": [], "gold_answer": "资料未提及"},
]


def run_eval(service: QAService, out_path: Path) -> list[dict]:
    """跑 20 组测试，逐条记录到 CSV。"""
    rows = []
    for i, case in enumerate(TEST_CASES, 1):
        ans: Answer = service.ask(case["q"])
        hit = 1 if ans.hits else 0
        # 自动判：gold_answer 关键词是否出现在回答中
        answer_ok = 1 if case["gold_answer"] in ans.answer else 0
        # 引用有效率：引用编号是否指向真实命中
        citation_ok = 1 if ans.citations and all(1 <= c.n <= len(ans.hits) for c in ans.citations) else 0
        rows.append({
            "id": i,
            "question": case["q"],
            "hit": hit,
            "answer_ok": answer_ok,
            "citation_ok": citation_ok,
            "latency_ms": ans.latency_ms,
            "tokens": ans.tokens,
            "cost_cny": round(ans.cost_cny, 6),
            "trace_id": ans.trace_id,
            "note": "" if hit else "未命中",
        })
        print(f"[{i:2d}/20] {case['q']:<30} hit={hit} answer_ok={answer_ok} cite_ok={citation_ok} {ans.latency_ms}ms")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n评估结果已写入: {out_path}")

    # 汇总
    n = len(rows)
    print(f"\n汇总: hit_rate={sum(r['hit'] for r in rows)/n:.2f}  answer_ok={sum(r['answer_ok'] for r in rows)/n:.2f}  citation_ok={sum(r['citation_ok'] for r in rows)/n:.2f}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="M2 20 组人工测试")
    parser.add_argument("--out", default=str(ROOT / "output" / "m2_eval.csv"))
    parser.add_argument("--index-dir", default=str(ROOT / "output" / "m2_kb_index"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    service = QAService(index_dir=Path(args.index_dir), top_k=args.top_k)
    run_eval(service, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
