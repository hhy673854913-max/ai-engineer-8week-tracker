"""Day 31 · 评估集：20 条样本（含 4 条应拒答的负样本）。

字段说明见 docs/week-07/day-31.md。
"""

from __future__ import annotations

import json
from pathlib import Path

CASES = [
    {"id": "q01", "question": "春节活动奖励什么时候发放", "type": "direct", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["7 个工作日"], "reference_answer": "活动结束后 7 个工作日内通过邮件发放。", "should_refuse": False},
    {"id": "q02", "question": "奖励咋还没到", "type": "colloquial", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["活动结束后", "7 个工作日"], "reference_answer": "奖励在活动结束后 7 个工作日内发放，30 天内领取。", "should_refuse": False},
    {"id": "q03", "question": "参加春节活动需要什么条件", "type": "direct", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["20 级", "实名认证"], "reference_answer": "账号等级 20 级且完成实名认证。", "should_refuse": False},
    {"id": "q04", "question": "积分多少能换皮肤", "type": "direct", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["100 分"], "reference_answer": "积分累计达到 100 分可兑换限定皮肤。", "should_refuse": False},
    {"id": "q05", "question": "钱什么时候能退回来", "type": "direct", "gold_doc_ids": ["refund-faq"], "gold_keywords": ["1-3 个工作日"], "reference_answer": "审核通过后 1-3 个工作日到账，银行卡可能 5 个工作日。", "should_refuse": False},
    {"id": "q06", "question": "充值了能退吗", "type": "colloquial", "gold_doc_ids": ["refund-faq"], "gold_keywords": ["7 天内", "未消费"], "reference_answer": "未消费订单可在支付后 7 天内申请退款。", "should_refuse": False},
    {"id": "q07", "question": "退款走什么流程", "type": "direct", "gold_doc_ids": ["refund-faq"], "gold_keywords": ["工单", "原路返回"], "reference_answer": "提交工单、提供订单号，审核后原路返回。", "should_refuse": False},
    {"id": "q08", "question": "发票怎么开", "type": "direct", "gold_doc_ids": ["refund-faq"], "gold_keywords": ["100 元", "3 个工作日"], "reference_answer": "充值满 100 元可申请电子发票，3 个工作日开具。", "should_refuse": False},
    {"id": "q09", "question": "开服崩了有啥说法", "type": "colloquial", "gold_doc_ids": ["compensation"], "gold_keywords": ["影响时长"], "reference_answer": "按影响时长补偿，1 小时内 50 钻石。", "should_refuse": False},
    {"id": "q10", "question": "补偿标准是什么", "type": "direct", "gold_doc_ids": ["compensation"], "gold_keywords": ["500 钻石", "头像框"], "reference_answer": "超过 4 小时补偿 500 钻石与限定头像框。", "should_refuse": False},
    {"id": "q11", "question": "奖励发放异常怎么办", "type": "multi_hop", "gold_doc_ids": ["compensation", "spring-activity"], "gold_keywords": ["15 天", "3 个工作日"], "reference_answer": "活动结束后 15 天内提交工单，核实后 3 个工作日内补发。", "should_refuse": False},
    {"id": "q12", "question": "手滑把道具用了还能找回不", "type": "direct", "gold_doc_ids": ["compensation"], "gold_keywords": ["每月上限 1 次"], "reference_answer": "原则上不补，系统提示不清晰可酌情补偿，每月 1 次。", "should_refuse": False},
    {"id": "q13", "question": "双十一活动有什么奖励", "type": "negative", "gold_doc_ids": [], "gold_keywords": [], "reference_answer": "知识库没有该活动。", "should_refuse": True},
    {"id": "q14", "question": "周年庆抽奖概率是多少", "type": "negative", "gold_doc_ids": [], "gold_keywords": [], "reference_answer": "知识库没有相关信息。", "should_refuse": True},
    {"id": "q15", "question": "海外服怎么充值", "type": "negative", "gold_doc_ids": [], "gold_keywords": [], "reference_answer": "知识库未覆盖海外服。", "should_refuse": True},
    {"id": "q16", "question": "能不能把我的账号数据导出", "type": "negative", "gold_doc_ids": [], "gold_keywords": [], "reference_answer": "知识库没有相关说明。", "should_refuse": True},
    {"id": "q17", "question": "活动期间用外挂会怎样", "type": "direct", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["取消获奖资格", "冻结"], "reference_answer": "取消获奖资格并冻结账号 7 天。", "should_refuse": False},
    {"id": "q18", "question": "队伍可以换人吗", "type": "entity", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["仅可绑定一次"], "reference_answer": "每个账号仅可绑定一次队伍。", "should_refuse": False},
    {"id": "q19", "question": "奖励一直没领会不会没了", "type": "multi_hop", "gold_doc_ids": ["spring-activity"], "gold_keywords": ["30 天内", "逾期作废"], "reference_answer": "需在 30 天内领取，逾期作废。", "should_refuse": False},
    {"id": "q20", "question": "客服电话是多少", "type": "negative", "gold_doc_ids": [], "gold_keywords": [], "reference_answer": "知识库未提供电话。", "should_refuse": True},
]


def main() -> int:
    out = Path(__file__).resolve().parent / "eval_set.jsonl"
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CASES), encoding="utf-8")
    print(f"wrote {out} ({len(CASES)} cases, {sum(c['should_refuse'] for c in CASES)} negative)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
