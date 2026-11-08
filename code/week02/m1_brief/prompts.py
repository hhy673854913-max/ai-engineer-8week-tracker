"""M1 的提示词模板（版本化）。

模板改动必须同时更新 VERSION 与 CHANGELOG——否则一周后你无法复现"那次 0.82"。
"""

from __future__ import annotations

VERSION = "v2.1"
CHANGELOG = "v2.1 增加 analysis 字段与 credibility 三维评分；v2.0 增加 category/entities"

EXTRACT_PROMPT = """你是资深财经编辑。从下面的资讯原文中抽取结构化信息。

规则：
1. 只依据原文，原文没有的信息填 null，不要推测；
2. credibility 从 0-100 打分：
   - 信源权威性（40）：官方公告 40 / 权威媒体 30 / 垂直媒体 20 / 自媒体 10
   - 信息可验证性（30）：有具体数字、时间、可查证主体各 10
   - 内容具体性（30）：笼统表述 10 / 有细节 20 / 有数据与引述 30
3. analysis 用两句话说明打分依据，必须引用原文片段。

输出 JSON：
{{
  "analysis": "string",
  "title": "string，不超过 30 字",
  "summary": "string，不超过 80 字",
  "entities": ["string，公司/产品/人物"],
  "category": "融资 | 产品 | 政策 | 技术 | 其他",
  "credibility": 0
}}

原文：
<article>{text}</article>
"""
