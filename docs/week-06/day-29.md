# Day 29 · 多智能体协作：Supervisor 与流水线

> W6 · 周四 ｜ 5h ｜ 产出 `code/week06/multi_agent.py` ｜ [Day 28](day-28.md) · [Day 30](day-30.md)

**今日目标**
- 分清三种多智能体编排：流水线、Supervisor、辩论/评审
- 用 LangGraph 实现"研究员 + 审稿员"两角色协作
- 想清楚一个关键问题：**什么时候多智能体反而不如单 Agent**

**验收**：给定主题 → 研究员产出初稿 → 审稿员提意见 → 研究员修订 → 输出终稿，全程可追踪。

---

## 上午 09:00–11:30 · 理论

### 1. 三种编排

| 模式 | 结构 | 适合 | 风险 |
| --- | --- | --- | --- |
| 流水线（Pipeline） | A → B → C | 步骤固定（解析→生成→检查） | 中间失败要能重试 |
| Supervisor | 一个调度者分派给多个专家 | 任务类型多样 | 调度者成为瓶颈 |
| 辩论 / 评审 | 多角色互相批评 | 质量要求高（文案、方案） | token 成本翻倍，可能"互相吹捧" |

```text
流水线：      [解析] → [生成] → [检查] → 输出
Supervisor：  [调度] ⇄ [研究员] / [程序员] / [审核]
辩论：        [正方] ⇄ [反方] → [裁判]
```

先划一条线：同一个 Agent 里加节点、共用一份上下文和一份 system prompt，那还是单 Agent；只有当每个角色有独立的 system prompt、独立的输入输出契约、能被单独跑和单独验收时，才算多智能体。面试问"你们到底是几个 agent"时，答的就是这条线，而不是数节点个数。

### 2. 多智能体的真实成本

| 成本项 | 影响 |
| --- | --- |
| token | 每个角色都要完整上下文，成本 ≈ 角色数 × 单 Agent |
| 延迟 | 串行角色叠加，可能 3–5 倍 |
| 调试 | 出错时不知道是哪个角色的问题 |
| 一致性 | 角色间对目标理解不一致，产出割裂 |

**所以**：能用单 Agent + 好工具解决的，不要上多智能体。
多智能体的价值在"角色隔离带来的专业性与可检查性"，不是"更聪明"。

### 3. 角色设计：每个角色必须有"可验收的输出"

```python
class Role(BaseModel):
    name: str
    system_prompt: str
    input_schema: type[BaseModel]      # 它需要什么
    output_schema: type[BaseModel]     # 它必须产出什么
    max_retries: int = 1
```

**坏设计**："研究员随便写点东西，审稿员随便看看。"
**好设计**：研究员输出 `Draft{title, sections[], citations[]}`，审稿员输出 `Review{scores{clarity, accuracy, completeness}, issues[], verdict: pass|revise}`。
这样每一步都能被程序校验，也能被评估。

### 4. 终止与迭代上限

评审循环最容易失控：

```python
MAX_ROUNDS = 2
if review.verdict == "pass" or round >= MAX_ROUNDS:
    return finalize(draft)
```

**必须有硬上限**。真实系统里还要加"改进幅度检测"：如果两轮分数没提升，直接接受现状。

### 5. 共享状态 vs 消息传递

LangGraph 里两种风格：

- **共享 State**：所有角色读写同一个 `TypedDict`（简单，但容易互相覆盖）
- **消息传递**：角色间通过 messages 交流（清晰，但 token 多）

建议：**结构化的中间产物放 State，对话式的讨论放 messages**。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 两个角色（80 min）

```python
class WriterState(TypedDict):
    topic: str
    draft: dict | None
    review: dict | None
    round: int
    history: Annotated[list[str], operator.add]

def researcher(state: WriterState) -> dict:
    prompt = RESEARCH_PROMPT.format(topic=state["topic"], feedback=state.get("review", {}).get("issues", []))
    raw = llm.chat(prompt, json_mode=True, temperature=0.4)
    return {"draft": json.loads(raw), "round": state["round"] + 1}

def reviewer(state: WriterState) -> dict:
    raw = llm.chat(REVIEW_PROMPT.format(draft=json.dumps(state["draft"], ensure_ascii=False)), json_mode=True, temperature=0)
    return {"review": json.loads(raw)}
```

### 任务 2 · 图与路由（60 min）

```python
g = StateGraph(WriterState)
g.add_node("researcher", researcher)
g.add_node("reviewer", reviewer)
g.add_edge(START, "researcher")
g.add_edge("researcher", "reviewer")
g.add_conditional_edges("reviewer", should_revise, {"revise": "researcher", "done": END})

def should_revise(state: WriterState) -> str:
    if state["review"]["verdict"] == "pass":
        return "done"
    if state["round"] >= 2:
        return "done"
    return "revise"
```

跑起来，观察：审稿意见是否具体？修订是否真的改进了？把每轮分数记下来。

### 任务 3 · 对照实验（40 min）

同一个主题，跑三种配置：

| 配置 | 质量（1-5 人工） | token | 延迟 |
| --- | --- | --- | --- |
| 单 Agent 一次生成 | | | |
| 单 Agent + 自我检查 | | | |
| 研究员 + 审稿员（2 轮） | | | |

**如果多智能体没有显著提升，就在 README 里写"实测不建议"** —— 这种诚实的结论比吹嘘有价值。

### 任务 4 · 扩展到三角色（30 min）

加一个"事实核查员"：只负责检查草稿里的数字、时间、专名是否有据可查（可以用 MCP 的知识库工具）。
体会"角色越细，编排与成本越复杂"。

---

## 代码思考（写进 `logs/day-29.md`）

1. 多智能体在什么情况下反而不如单 Agent？举一个你实测的例子。
2. 审稿员的评分如果每轮都是 4/5（不给具体意见），系统会怎样？怎么防"形式化评审"？
3. 共享 State 的写法下，两个角色同时写 `draft` 会怎样？LangGraph 的 reducer 怎么解决？
4. 为什么"改进幅度检测"比"最大轮数"更有效？具体怎么实现？
5. 如果要把这套用于生产（比如活动页生成），你会保留几个角色？哪些环节必须人工审？

## 复盘清单

- [ ] 两角色流水线跑通，可追踪
- [ ] 有硬上限与终止条件
- [ ] 三种配置的对照数据
- [ ] commit：`day29: 研究员/审稿员多智能体 + 对照实验`
