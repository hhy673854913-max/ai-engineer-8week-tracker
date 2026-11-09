# Day 36 · M3 开发（一）：多智能体流水线骨架

> W8 · 周一 ｜ 5h ｜ 产出 `code/week08/activity_assistant/graph.py` ｜ [Day 35](../week-07/day-35.md)

**今日目标**
- 把 Day 30 的设计变成代码：四个角色、状态机、澄清中断
- 先跑通"需求解析 → 代码生成"两个最小角色，不追求完整
- 每个角色都有 Pydantic 契约与单测

**验收**：输入一句活动需求，输出可运行的 HTML 活动页骨架 + 素材清单 + 自检报告。

---

## 上午 09:00–11:30 · 实现要点

### 1. 目录结构

```
code/week08/activity_assistant/
├─ __init__.py
├─ models.py        # 四个角色的 Pydantic 契约
├─ prompts.py       # 各角色提示词（版本化）
├─ roles.py         # analyst / asset / coder / reviewer
├─ graph.py         # LangGraph 状态机
├─ render.py        # 生成物落盘 + 预览
└─ demo.py          # 端到端演示
```

落到路径上：`code/week08/` 是仓库里的物理目录，`week08` 才是包名，所以 `python -m` 必须在 `code/` 目录下执行（或把 `code/` 加进 `PYTHONPATH`）；每个子目录里的 `__init__.py` 不是摆设，它让 Python 把文件夹当包处理，缺了它 `from .models import Requirement` 会直接报错。面试官 clone 你的仓库时第一件事就是跑这条命令，跑不起来，后面三个项目都不用看了。

### 2. 从"能跑"到"可验收"

每个角色的输出都必须通过 Pydantic 校验：

```python
def analyst(state: M3State) -> dict:
    raw = llm.chat(PROMPTS["analyst"].format(requirement=state["raw_requirement"]), json_mode=True)
    req = Requirement.model_validate_json(extract_json(raw))
    return {"requirement": req, "timeline": state["timeline"] + [{"step": "analyst", "ts": now()}]}
```

落到入口上：初始 state 由一个入口节点写死，`graph.invoke({"raw_requirement": req, "timeline": [], "round": 0})`，所以要先在 `M3State` 里补上 `raw_requirement: str`，并把 `requirement` 放宽成 `Requirement | None`。校验别让它直接抛：复用 Day 05 的 `generate_with_retry`（`shared/structured.py`），把字段错误当成澄清线索回传，两次修不好就写进 `missing` 走 clarify 分支，而不是让整条流水线崩掉——M3 的"一次通过率 65%"这个面试数字，就是从这条链路里量出来的。

### 3. 澄清分支：不要假装什么都能做

```python
def route_after_analyst(state: M3State) -> str:
    if state["requirement"].missing:
        return "clarify"
    return "asset"

def clarify(state: M3State) -> dict:
    questions = state["requirement"].missing
    decision = interrupt({"questions": questions})
    # 人工回答后回到 analyst 重新解析
    return {"clarifications": decision.get("answers", [])}
```

**`interrupt` 是 M3 的关键**：它证明你懂"AI 做初稿、人做决策"，而不是盲目自动化。

把线接全：`clarifications` 要拼进 analyst 的 prompt（"以下信息已由运营确认：{clarifications}，不要重复问"），并在 `interrupt` 旁边写全三件事：编译时 `checkpointer=MemorySaver()`、调用时带固定 `thread_id`、恢复时 `Command(resume={"answers": [...]})`。演示视频里把这条"机器停住等人回答"的路径录进去——HITL 是面试官判断你懂不懂企业落地的分水岭，而它恰好最容易被讲成"我加了个 input()"。

### 4. 代码生成的工程约束

| 约束 | 做法 |
| --- | --- |
| 单文件可预览 | 生成 `index.html` 自包含（内联 CSS/JS） |
| 尺寸可控 | 限制每文件 ≤ 8KB，超了拆分 |
| 可校验 | HTML 用 `lxml` 解析，检查是否有未闭合标签 |
| 可回滚 | 每次生成存 `runs/{run_id}/`，保留历史 |

### 5. 质量检查要"规则优先"

```python
def rule_checks(html: str) -> list[dict]:
    issues = []
    if "<meta name=\"viewport\"" not in html:
        issues.append({"severity": "warn", "rule": "responsive", "message": "缺少 viewport meta"})
    if "onclick=" in html:
        issues.append({"severity": "info", "rule": "a11y", "message": "建议用 addEventListener"})
    try:
        etree.fromstring(html, etree.HTMLParser())
    except Exception as e:
        issues.append({"severity": "error", "rule": "syntax", "message": str(e)})
    return issues
```

**规则能查的，不要花 LLM 的钱**。LLM 只负责"业务合理性"这类规则查不了的部分。

落到解析器上：`lxml` 是 Python 的 HTML/XML 解析库，作用和浏览器里的 `DOMParser` 一样：把字符串变成一棵可查询的 DOM 树，好处是能用 XPath 选节点做规则检查，不用拿正则去啃标签。但它的 `HTMLParser` 走的是容错路线，想真抓"未闭合标签"，得自己比对标签栈或用 `lxml.html` 解析后检查异常节点，否则你那条"硬错误一票否决"永远哑火——面试问"你怎么保证生成代码可运行"，答"我用解析器校验过"和答"我以为解析器会校验"，中间差的就是这一句。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 契约与提示词（60 min）

```python
# models.py
class Requirement(BaseModel):
    title: str = Field(min_length=2, max_length=20)
    goal: str
    target_users: str
    mechanics: list[str] = Field(min_length=1)
    rewards: list[str] = Field(min_length=1)
    constraints: list[str] = []
    missing: list[str] = []
```

```text
# prompts.py · analyst v1
你是资深游戏运营策划。把下面这句需求拆解成结构化活动方案。

规则：
1. 只能使用需求里出现的信息；缺失的放进 missing，不要编造；
2. mechanics 用祈使句，每条一个动作；
3. rewards 写清"奖励什么 + 数量"；
4. 输出 JSON，字段与 schema 一致。

需求：{requirement}
```

### 任务 2 · 两个角色（90 min）

分析师 + 代码生成器。代码生成器要求：

```text
你是资深前端工程师。根据活动方案生成一个**自包含的 HTML 活动页**。

要求：
- 单个 HTML 文件，内联 CSS 与 JS，不依赖外部 CDN
- 移动端优先，适配 375px 宽度
- 包含：标题、玩法说明、奖励展示、参与按钮（点击弹 toast）
- 不出现真实用户数据、不请求任何外部接口
- 输出 JSON：{"files": [{"path": "index.html", "content": "..."}], "entry": "index.html", "notes": "..."}
```

### 任务 3 · 跑通端到端（60 min）

```powershell
python -m week08.activity_assistant.demo --requirement "做一个情人节双人组队活动，奖励是限定皮肤"
```

检查三件事：
1. `runs/{run_id}/index.html` 能在浏览器打开
2. 素材清单齐全（图片尺寸、文案、配置项）
3. 缺失信息被识别（这个需求确实缺"活动时间"，应该进 missing）

### 任务 4 · 加单测（30 min）

对 `rule_checks` 与 `Requirement` 校验写测试（不需要 API Key），保证 CI 能跑。

---

## 代码思考（写进 `logs/day-36.md`）

1. 为什么分析师要输出 `missing` 而不是"自己补全"？补全会导致什么后果？
2. 代码生成为什么要求"自包含单文件"？多文件有什么好处与代价？
3. 规则检查能覆盖哪些问题？哪些必须 LLM 判断？各举两例。
4. `interrupt` 之后如果人一直不回答，状态怎么处理？
5. 生成物保留历史 `runs/{run_id}/` 会占空间，什么时候清理？

## 复盘清单

- [ ] 两个角色跑通，输出符合契约
- [ ] 生成物可在浏览器打开
- [ ] 缺失信息能被识别
- [ ] 单测通过
- [ ] commit：`M3: 分析师 + 代码生成器 + 端到端`
