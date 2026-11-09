# week-08 审校结果

## 周总评

本周后三天（day-38/39/40）是把前七周成果变现的部分，动机和落点都扎实——README 按面试官前 30 秒的阅读顺序写、STAR-M 给到"4399 活动交付 3 天 → 1 天"这种可直接背的例子、投递表带转化率状态机，读者不会问"这跟我的岗位有什么关系"。问题全部压在 day-36：这是本周唯一能把"Agent 工程师的工程能力"变成证据的一天，但讲义几乎全是代码片段，缺的恰恰是"缝合"——目录到能跑、契约到入口、校验到失败、澄清到恢复，这四条缝都没补，而读者画像里"只写过脚本级 Python"的人正好会断在缝上。后果不是跑不出 Demo，而是 M3 只剩一个能跑的 Demo：面试官追问"状态怎么设计的""模型输出不稳定怎么办""HITL 挂起后怎么恢复"时，你手里没有可讲的东西。day-37 明显写得好（每个 MCP 调用都交代"没有它这一步会差在哪"、timeline 直接服务 3 天 → 1 天的叙事），说明这种密度作者是会的，建议按 day-37 的标准回补 day-36。

## day-36 · M3 开发（一）：多智能体流水线骨架

- **P1 · 1. 目录结构** ｜ 问题：目录树之后直接跳到代码，对"只写过脚本级 Python"的读者这里就是第一道坎：`├─ __init__.py` 没有一句说明它是干什么的，而任务 3 的运行命令是 `python -m week08.activity_assistant.demo`、文件却落在 `code/week08/activity_assistant/`，模块名与物理目录怎么对上（从哪个目录执行、要不要设 `PYTHONPATH`）全文没交代，照敲大概率是 `No module named week08`。｜ 建议补写：`code/week08/` 是仓库里的物理目录，`week08` 才是包名，所以 `python -m` 必须在 `code/` 目录下执行（或把 `code/` 加进 `PYTHONPATH`）；每个子目录里的 `__init__.py` 不是摆设，它让 Python 把文件夹当包处理，缺了它 `from .models import Requirement` 会直接报错。面试官 clone 你的仓库时第一件事就是跑这条命令，跑不起来，后面三个项目都不用看了。

- **P1 · 2. 从"能跑"到"可验收"** ｜ 问题：本节只有 6 行代码，而且只给了"校验通过"的那一条路径。入口没交代：代码读的 `state["raw_requirement"]` 这个 key 在 Day 30 定义的 `M3State`（`requirement` / `assets` / `code` / `review` / `round` / `clarifications` / `timeline`）里根本不存在，初始 state 由谁写、CLI 参数怎么变成 state，一句都没有。失败也没交代：`Requirement.model_validate_json(extract_json(raw))` 径直抛 `ValidationError`，等于把 Day 05 教的"回传字段错误重试、两次后降级"整段丢了——而本节的标题恰恰叫"可验收"。｜ 建议补写：初始 state 由一个入口节点写死，`graph.invoke({"raw_requirement": req, "timeline": [], "round": 0})`，所以要先在 `M3State` 里补上 `raw_requirement: str`，并把 `requirement` 放宽成 `Requirement | None`。校验别让它直接抛：复用 Day 05 的 `generate_with_retry`（`shared/structured.py`），把字段错误当成澄清线索回传，两次修不好就写进 `missing` 走 clarify 分支，而不是让整条流水线崩掉——M3 的"一次通过率 65%"这个面试数字，就是从这条链路里量出来的。

- **P1 · 3. 澄清分支：不要假装什么都能做** ｜ 问题：这段只写了"怎么问"，没写"答案怎么用"。`clarify` 把人工回答存进 `clarifications`，但第 2 节里 `analyst` 的 prompt 只读 `state["raw_requirement"]`，两次解析之间没有任何接线——照抄跑起来就是"澄清 → 再解析 → 还是缺同样字段 → 再澄清"的死循环，直到 `recursion_limit` 报错。另外 `interrupt` 要真正挂起并恢复，必须在 `compile(checkpointer=...)` 下用同一个 `thread_id` 重新 invoke（Day 24 讲过），本节一句没提，读者写到这一步会卡在"图跑一半就停了，怎么继续"。｜ 建议补写：把 `clarifications` 拼进 analyst 的 prompt（"以下信息已由运营确认：{clarifications}，不要重复问"），并在 `interrupt` 旁边写全三件事：编译时 `checkpointer=MemorySaver()`、调用时带固定 `thread_id`、恢复时 `Command(resume={"answers": [...]})`。演示视频里把这条"机器停住等人回答"的路径录进去——HITL 是面试官判断你懂不懂企业落地的分水岭，而它恰好最容易被讲成"我加了个 input()"。

- **P1 · 5. 质量检查要"规则优先"** ｜ 问题：`lxml` 在全文第一次出现就直接进代码（`etree.fromstring(html, etree.HTMLParser())`），既没说它是什么，也没说为什么校验 HTML 用它而不是正则或字符串匹配。更关键的是上一节的表格承诺"检查是否有未闭合标签"，但 `HTMLParser` 是浏览器式的容错解析器——`<div>` 没闭合它会自动补全，根本不会抛异常，这段 `try/except` 的 `error` 分支实际上永远不触发，读者会以为自己装了一道语法门禁。｜ 建议补写：`lxml` 是 Python 的 HTML/XML 解析库，作用和浏览器里的 `DOMParser` 一样：把字符串变成一棵可查询的 DOM 树，好处是能用 XPath 选节点做规则检查，不用拿正则去啃标签。但它的 `HTMLParser` 走的是容错路线，想真抓"未闭合标签"，得自己比对标签栈或用 `lxml.html` 解析后检查异常节点，否则你那条"硬错误一票否决"永远哑火——面试问"你怎么保证生成代码可运行"，答"我用解析器校验过"和答"我以为解析器会校验"，中间差的就是这一句。

## day-37 · 接入 MCP，端到端打通

无

## day-38 · 作品集与 README 打磨

无

## day-39 · 简历重写与模拟面试

无

## day-40 · 投递、复盘与长期路线

无
