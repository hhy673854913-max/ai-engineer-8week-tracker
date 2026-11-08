# Day 24 · LangGraph 状态图建模

> W5 · 周四 ｜ 5h ｜ 产出 `code/week05/langgraph_agent.py` + 状态流转图 ｜ [Day 23](day-23.md) · [Day 25](day-25.md)

**今日目标**
- 用"状态机"重新理解 Agent：节点是函数，边是控制流，状态是唯一的真相源
- 用 LangGraph 重写 Day 22 的多工具 Agent，画出状态流转图
- 掌握条件路由、循环、检查点（checkpoint）三个生产必备能力

**验收**：`python -m week05.langgraph_agent "厦门天气如何"` 跑通；`state.png`（或 mermaid）能讲清每一步。

---

## 上午 09:00–11:30 · 理论

### 1. 为什么用状态机而不是 while 循环

手写 Agent 的循环里，"当前进展"散落在 `messages` 列表里；状态机把它显式化成 `State`：

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    question: str
    tool_calls_count: int
    final_answer: str | None
```

好处：
- **可持久化**：状态可以存库，进程挂了能恢复（checkpoint）
- **可路由**：按状态决定下一步，而不是靠模型自由发挥
- **可测试**：每个节点是纯函数，能单独测
- **可视化**：图能画出来，给人看

代价：多一层抽象，简单任务反而更啰嗦。**3 步以内的任务，手写循环更划算。**

### 2. 三个核心概念

| 概念 | 作用 | API |
| --- | --- | --- |
| Node | 一个处理函数 `state -> partial_state` | `add_node("name", fn)` |
| Edge | 固定流转 | `add_edge("a", "b")` |
| Conditional Edge | 按状态路由 | `add_conditional_edges("a", router, {"x": "b", "y": "c"})` |

```python
graph = StateGraph(AgentState)
graph.add_node("agent", call_model)
graph.add_node("tools", run_tools)
graph.add_node("finalize", finalize)

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "finalize"})
graph.add_edge("tools", "agent")
graph.add_edge("finalize", END)

app = graph.compile(checkpointer=MemorySaver())
```

### 3. 循环与终止

```python
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    if state.get("final_answer"):
        return "end"
    return "end"
```

**`recursion_limit`** 是 LangGraph 的安全阀（默认 25）。超了会抛 `GraphRecursionError`。
生产里要设置合理值并把错误翻译成用户能懂的话。

### 4. 检查点（Checkpoint）：这才是 LangGraph 的真正价值

```python
from langgraph.checkpoint.memory import MemorySaver
app = graph.compile(checkpointer=MemorySaver())

config = {"configurable": {"thread_id": "user-123"}}
app.invoke({"messages": [("user", "查厦门天气")]}, config)
# 下一次用同一个 thread_id，能接着上次的状态继续
```

三个应用：
1. **多轮对话**：`thread_id` 隔离会话
2. **人机协同（HITL）**：在危险操作前 `interrupt()`，等人审批后继续
3. **故障恢复**：进程挂了，从最后一个 checkpoint 重放

生产里把 `MemorySaver` 换成 `SqliteSaver` / `PostgresSaver`。

### 5. 状态设计的三条纪律

1. **状态尽量小**：只放"下一步需要的"，不要把整个文档塞进 state
2. **用 reducer 合并**：`add_messages` 是官方 reducer，自己写列表时注意覆盖 vs 追加
3. **节点幂等**：同一个 state 跑两次结果应一致（工具调用除外，要防重复执行）

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 最小图（40 min）

先画一个"问候 → 判断语气 → 正式/随意回复"的两分支图，跑通。
确认 `add_conditional_edges` 的路由 map 与返回值一致（拼错 key 会静默走错分支）。

### 任务 2 · 重写多工具 Agent（80 min）

```python
def call_model(state: AgentState) -> dict:
    resp = llm.chat(state["messages"], tools=TOOLS, temperature=0)
    return {"messages": [resp.choices[0].message]}

def run_tools(state: AgentState) -> dict:
    last = state["messages"][-1]
    results = []
    for call in last.tool_calls:
        res = registry.call(call.function.name, json.loads(call.function.arguments or "{}"))
        results.append(ToolMessage(content=json.dumps(res, ensure_ascii=False), tool_call_id=call.id))
    return {"messages": results, "tool_calls_count": state["tool_calls_count"] + len(results)}
```

对照 Day 21 的手写版：代码量增加了多少？可读性提升了多少？

### 任务 3 · 画状态图（30 min）

```python
print(app.get_graph().draw_mermaid())
```

把输出贴进 README。**这张图是你面试讲 Agent 时的白板武器。**

### 任务 4 · 加 checkpointer 与人机协同（50 min）

```python
from langgraph.types import interrupt, Command

def dangerous_node(state: AgentState) -> dict:
    decision = interrupt({"question": "即将发送通知，确认吗？", "payload": state["draft"]})
    if decision != "yes":
        return {"final_answer": "已取消"}
    return {"final_answer": "已发送"}
```

跑一次：先 `invoke` 触发中断，再 `Command(resume="yes")` 继续。
**这是"AI 做建议、人做决策"的标准模式**，也是企业落地最容易被接受的方式。

---

## 代码思考（写进 `logs/day-24.md`）

1. 状态机相比 while 循环，多出来的抽象在什么规模下才开始划算？
2. `thread_id` 设计成"用户 id"和"会话 id"有什么区别？多设备登录会怎样？
3. `interrupt` 之后进程重启，审批状态还在吗？`MemorySaver` 与 `SqliteSaver` 的差别体现在哪？
4. `recursion_limit=25` 对 3 个工具的 Agent 够吗？怎么估算合理值？
5. 如果某个节点抛异常，LangGraph 默认会怎样？你要不要加 `retry_policy`？

## 复盘清单

- [ ] 状态图能画出来（mermaid）
- [ ] 多工具 Agent 在 LangGraph 上跑通
- [ ] HITL 中断/恢复体验过一次
- [ ] 对比了手写版与 LangGraph 版的代码量与可读性
- [ ] commit：`day24: LangGraph 状态机 Agent + HITL`
