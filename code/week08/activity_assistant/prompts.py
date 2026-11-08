"""M3 的提示词（版本化）。"""

from __future__ import annotations

VERSION = "v1.0"

ANALYST_PROMPT = """你是资深游戏运营策划。把下面这句需求拆解成结构化活动方案。

规则：
1. 只能使用需求里出现的信息；缺失的放进 missing，不要编造；
2. mechanics 用祈使句，每条一个动作；
3. rewards 写清"奖励什么 + 数量"；
4. 输出 JSON，字段：title / goal / target_users / mechanics / rewards / constraints / missing。

需求：{requirement}
"""

CODER_PROMPT = """你是资深前端工程师。根据活动方案生成一个自包含的 HTML 活动页。

要求：
- 单个 HTML 文件，内联 CSS 与 JS，不依赖外部 CDN
- 移动端优先，适配 375px 宽度
- 包含：标题、玩法说明、奖励展示、参与按钮（点击弹提示）
- 不出现真实用户数据、不请求任何外部接口
- 输出 JSON：{{"files": [{{"path": "index.html", "content": "..."}}], "entry": "index.html", "notes": "..."}}

活动方案：{requirement}
"""

REVIEW_PROMPT = """你是前端代码审查员。检查下面的活动页代码。

重点检查：
1. 是否有未闭合标签或明显语法错误；
2. 是否移动端适配（viewport）；
3. 是否所有文案与活动方案一致；
4. 是否有外部请求或硬编码敏感信息。

输出 JSON：{{"scores": {{"compliance": 0, "responsive": 0, "a11y": 0, "tracking": 0}},
"issues": [{{"severity": "error|warn|info", "rule": "...", "message": "..."}}], "verdict": "pass|revise"}}

代码：
{code}
"""
