"""资讯抽取模板 v1 → v2（Day 08 迭代，M1 生产使用）。

迭代记录：
- v1 朴素版：无 analysis、无 few-shot、credibility 只有一句"打分"
- v2.0 加 analysis 字段（先思考后输出）
- v2.1 加 2 个 few-shot（含"信息不足 → null"）+ credibility 三维评分

所有模板使用 $var 占位（与 render.py 配套），JSON 示例里的花括号无需转义。
"""

from __future__ import annotations

VERSION = "v2.1"
CHANGELOG = "v2.1 增加 few-shot 与 credibility 三维评分；v2.0 增加 analysis 字段"

TEMPLATES: dict[str, str] = {}

# ---------------------------------------------------------------------------
# v1：最朴素版（对照组）
# ---------------------------------------------------------------------------
TEMPLATES["extract_v1"] = """从下面的资讯原文中抽取信息，输出 JSON：
{"title": "标题", "summary": "摘要", "category": "分类", "entities": ["实体"], "credibility": 0}

原文：
<article>$text</article>
"""

# ---------------------------------------------------------------------------
# v2.1：analysis + few-shot + 三维评分
# few-shot 原则：同构 / 覆盖边界（第二条是"信息不足 → null"）/ 最重要的放最后
# ---------------------------------------------------------------------------
TEMPLATES["extract_v2"] = """你是资深财经编辑。从下面的资讯原文中抽取结构化信息。

规则：
1. 只依据原文，原文没有的信息填 null，不要推测；
2. credibility 从 0-100 打分：
   - 信源权威性（40）：官方公告 40 / 权威媒体 30 / 垂直媒体 20 / 自媒体 10
   - 信息可验证性（30）：有具体数字、时间、可查证主体各 10
   - 内容具体性（30）：笼统表述 10 / 有细节 20 / 有数据与引述 30
3. analysis 用两句话说明打分依据，必须引用原文片段。

输出 JSON：
{
  "analysis": "string",
  "title": "string，不超过 30 字",
  "summary": "string，不超过 80 字",
  "entities": ["string，公司/产品/人物"],
  "category": "融资 | 产品 | 政策 | 技术 | 其他",
  "credibility": 0
}

示例 1（正常抽取）：
原文：<article>某权威媒体报道，A 公司今日宣布完成 5 亿元 B 轮融资，由知名基金领投，资金将用于扩充研发团队。</article>
输出：
{
  "analysis": "来源为权威媒体得 30 分；'5 亿元''今日'为可验证数字与时间再得 20 分；有领投方与用途等细节得 30 分。",
  "title": "A 公司完成 5 亿元 B 轮融资",
  "summary": "A 公司宣布完成 5 亿元 B 轮融资，由知名基金领投，资金用于扩充研发团队。",
  "entities": ["A 公司"],
  "category": "融资",
  "credibility": 80
}

示例 2（信息不足 → null，这是必须有的边界示例）：
原文：<article>听说隔壁公司最近拿到了一大笔钱，具体多少不清楚，好像是做 AI 的。</article>
输出：
{
  "analysis": "'听说''不清楚'表明来源不可验证，权威性 10 分；无具体数字与时间得 0 分；表述笼统得 10 分。",
  "title": "传闻某 AI 公司获投",
  "summary": "网传某 AI 公司获得大额投资，金额与投资方均不明确，尚无法验证。",
  "entities": [],
  "category": "融资",
  "credibility": 20
}

现在处理下面的原文：
<article>$text</article>
"""

# 按版本取模板的便捷入口
LATEST = "extract_v2"
