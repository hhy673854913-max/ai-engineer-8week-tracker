# Day 21 · ReAct 与手写 Agent 循环

> W5 · 周一 ｜ 5h ｜ 产出 `code/week05/agent_loop.py` ｜ [Day 20](../week-04/day-20.md)

**今日目标**
- 说清 Agent 与"链式调用"的本质区别：**模型决定下一步，而不是你写死顺序**
- 用原生 Function Calling 手写一个 ≈100 行的 ReAct 循环
- 理解"循环终止条件"为什么比"循环本身"更难写

**验收**：Agent 能自主完成"查天气 → 换算温度 → 给建议"三步任务，并打印每一步的思考与工具调用。

---

## 上午 09:00–11:30 · 理论输入

### 1. 链 vs Agent

| | 链（Chain） | Agent |
| --- | --- | --- |
| 控制流 | 你写死：A→B→C | 模型决定：下一步调哪个工具 |
| 步数 | 固定 | 动态 |
| 失败处理 | 每步 try/catch | 模型看到错误后自己调整 |
| 可预测性 | 高 | 低 |
| 调试难度 | 低 | 高（必须记录轨迹） |

**一句话**：链是"编排"，Agent 是"把编排权交给模型"。代价是可控性下降，所以生产系统常用"受限 Agent"——
给模型有限的工具 + 最大步数 + 明确的终止条件。

### 2. ReAct 循环

```text
while 未完成 and 步数 < max_steps:
    thought, action = LLM(历史 + 工具列表)
    if action == "final_answer": break
    observation = 执行工具(action)
    历史 += (action, observation)
```

真实实现里"thought"往往不是显式文本，而是模型直接返回 `tool_calls`。但**结构上仍是这三段**：
推理 → 行动 → 观察。

### 3. Function Calling 的消息结构（必须背下来）

```python
# 1) 模型要求调用工具
assistant_msg = {
    "role": "assistant",
    "content": None,
    "tool_calls": [{
        "id": "call_abc",
        "type": "function",
        "function": {"name": "get_weather", "arguments": "{\"city\":\"厦门\"}"},
    }],
}

# 2) 你把结果回传
tool_msg = {
    "role": "tool",
    "tool_call_id": "call_abc",     # 必须与上面 id 对应
    "content": "{\"temp\": 24, \"text\": \"多云\"}",
}
```

三个致命细节：
1. `tool_call_id` 对不上 → 400
2. `arguments` 是 **JSON 字符串**，不是对象
3. 多个工具调用时，**每个 `tool_call_id` 都要有一条 tool 消息**，少一条就报错

### 4. 工具 schema 怎么写

```python
TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "查询指定城市的实时天气。当用户问天气、温度、是否下雨时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市中文名，如 厦门"},
            },
            "required": ["city"],
        },
    },
}]
```

`description` 是给模型看的"使用说明"，写得好坏直接决定它会不会用错工具。
**给反例**：在 description 里写"不要用于查询历史天气"，比事后调参有效。

### 5. 终止条件（最容易写错的地方）

| 场景 | 处理 |
| --- | --- |
| 模型返回 `finish_reason="stop"` 且无 tool_calls | 正常结束 |
| 达到 `max_steps` | 强制结束，返回"未能完成，已尝试 N 步" |
| 工具连续失败 3 次 | 终止，把错误暴露给用户 |
| 模型重复调用同一工具同一参数 | 检测循环，注入提示"你已调用过，请换思路" |
| 单步超时 | 终止或重试（工具级超时） |

**没有终止条件的 Agent 会烧钱**：一个死循环能在几分钟内烧掉几十块。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 三个本地工具（40 min）

为了不依赖外部 API，先用本地函数造工具：

```python
def get_weather(city: str) -> dict:
    """假数据，但结构真实。"""
    db = {"厦门": {"temp": 24, "text": "多云"}, "北京": {"temp": 8, "text": "晴"}}
    return db.get(city, {"error": f"未收录城市: {city}"})

def calculator(expression: str) -> dict:
    allowed = set("0123456789+-*/(). ")
    if not set(expression) <= allowed:
        return {"error": "只支持四则运算"}
    return {"result": eval(expression)}   # 演示用；生产必须用 AST 白名单

def search_notes(keyword: str) -> list[str]:
    ...
```

**注意 `eval`**：演示可以，生产环境必须用 `ast.literal_eval` 或表达式解析器。这个坑在 Day 22 会再讲。

### 任务 2 · Agent 循环（80 min）

```python
class Agent:
    def __init__(self, llm, tools: dict[str, Callable], max_steps: int = 8):
        self.llm, self.tools, self.max_steps = llm, tools, max_steps

    def run(self, question: str) -> str:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
        for step in range(1, self.max_steps + 1):
            resp = self.llm.chat(messages, tools=TOOLS, temperature=0)
            msg = resp.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return msg.content or ""
            for call in msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                try:
                    result = self.tools[name](**args)
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
        return "已达到最大步数，未能完成任务。"
```

### 任务 3 · 加轨迹日志（30 min）

```python
@dataclass
class Step:
    n: int
    thought: str | None
    tool: str | None
    args: dict | None
    observation: str | None
    elapsed_ms: int
```

把每一步存成 JSONL。**Agent 的可调试性完全依赖轨迹**，没有轨迹你无法回答"它为什么选了这个工具"。

### 任务 4 · 压力测试（30 min）

故意制造问题，看 Agent 是否优雅失败：
- 问一个需要不存在工具的问题（"帮我订机票"）
- 让计算器除零
- 让城市查不到

记录它的行为，写进 `logs/day-21.md`。

---

## 代码思考（写进 `logs/day-21.md`）

1. 为什么 `arguments` 是字符串而不是对象？这个设计给解析带来什么风险？
2. 多个 `tool_calls` 时，如果只回传一个 `tool` 消息会怎样？错误信息能提示你原因吗？
3. 模型重复调用同一工具同一参数，你会在代码里怎么检测？检测到后注入什么提示？
4. `max_steps=8` 这个数字怎么定？太大太小分别有什么问题？
5. 为什么 Agent 的工具最好"幂等"？举一个不幂等导致重复扣款的场景。

## 复盘清单

- [ ] Agent 能跑通"天气 → 换算 → 建议"三步
- [ ] 有轨迹日志（JSONL）
- [ ] 三个异常场景都试过
- [ ] commit：`day21: 手写 ReAct Agent 循环`
