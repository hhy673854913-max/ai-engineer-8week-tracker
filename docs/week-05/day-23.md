# Day 23 · smolagents 对照实践

> W5 · 周三 ｜ 5h ｜ 产出 `code/week05/smol_demo.py` ｜ [Day 22](day-22.md) · [Day 24](day-24.md)

**今日目标**
- 用 Hugging Face 的 `smolagents` 跑通一个 Agent，理解"代码即行动"（CodeAgent）这派设计
- 与手写 Agent 做三维对比：可控性、代码量、可解释性
- 形成自己的判断：什么场景适合"让模型写代码"，什么场景绝对不能

**验收**：同一个任务（查天气 + 计算温差 + 给建议）分别用手写 Agent 与 smolagents 完成，记录步数与结果差异。

---

## 上午 09:00–11:30 · 理论

### 1. 两种 Agent 范式

| 范式 | 行动形式 | 优点 | 缺点 |
| --- | --- | --- | --- |
| Tool Calling | 模型返回 `tool_calls` JSON | 可控、可审计、schema 严格 | 表达能力受工具集限制 |
| Code Agent | 模型写 Python 代码并执行 | 表达力强，能组合、循环、算数 | 安全风险高，需要沙箱 |

smolagents 的 `CodeAgent` 属于后者：它让模型生成 `final_answer(...)` 或调用工具的 Python 代码，
在受限环境里执行。**对"数据处理 + 计算"类任务，代码比 tool call 更自然**。
但对"删除数据、发消息"这类副作用操作，让模型写代码执行是危险的。

### 2. smolagents 核心概念

```python
from smolagents import CodeAgent, OpenAIServerModel, tool

@tool
def get_weather(city: str) -> dict:
    """查询城市实时天气。

    Args:
        city: 城市中文名，如 厦门
    """
    ...

model = OpenAIServerModel(model_id="deepseek-chat", api_base=BASE, api_key=KEY)
agent = CodeAgent(tools=[get_weather], model=model, max_steps=6)
agent.run("厦门和北京现在温差多少？给穿衣建议")
```

三个要点：
1. `@tool` 从**函数签名 + docstring** 自动生成 schema（对比你昨天手写 JSON Schema 的痛苦）
2. `CodeAgent` 生成的是代码，执行时会打印出来——**这就是天然的轨迹**
3. 默认 `max_steps` 较小（6），防跑飞

### 3. 沙箱问题（必须懂）

`CodeAgent` 执行模型生成的代码，默认有基础防护（禁止 import 危险模块、限制可用函数），
但**不是强沙箱**。生产环境要做：
- 容器隔离（Docker / Firecracker）
- 只读文件系统 + 无网络
- 资源限制（CPU / 内存 / 时间）
- 白名单函数，禁用 `eval` / `exec` / `open` / `subprocess`

**如果你要在公司用 CodeAgent，先问安全同学。** 这是这类框架落地时最大的阻力。

### 4. 三个框架的定位对比

| 框架 | 定位 | 适合 |
| --- | --- | --- |
| 手写循环 | 理解原理、极简可控 | 教学、简单场景、需要完全掌控 |
| smolagents | 轻量、代码即行动 | 数据分析、计算密集型任务 |
| LangGraph | 状态机、可编排、可持久化 | 生产级多步流程、人机协同 |

**没有"最好的框架"，只有"当前约束下的取舍"。** 面试时能讲清取舍，比会背 API 值钱。

### 5. 从课程里该学什么（而不是抄代码）

Hugging Face Agents Course 的价值在三个概念：
1. **Thought-Action-Observation 循环**（你 Day 21 已手写过）
2. **工具即 API**（你 Day 22 已做过）
3. **多步规划与反思**（今天重点体会：CodeAgent 如何用代码实现"循环 + 条件"）

**别把课程作业抄一遍就完事**，要问：它为什么这么设计？我的实现差在哪？

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 跑通 smolagents（60 min）

```powershell
uv pip install smolagents
```

先跑最小例子：一个工具 + 一个问题。记录：
- 生成了几段代码
- 每段代码做了什么
- 有没有多余步骤

### 任务 2 · 同任务对照（80 min）

任务："厦门和北京现在温差多少？给穿衣建议。"

| 维度 | 手写 Agent | smolagents CodeAgent |
| --- | --- | --- |
| 步数 | | |
| 生成 token | | |
| 延迟 | | |
| 结果正确 | | |
| 轨迹可读性 | | |
| 失败时的可恢复性 | | |

**预期**：CodeAgent 步数更少（一次写代码完成两步），但轨迹更长、token 更多。
亲自验证这个预判，别接受别人的结论。

### 任务 3 · 安全实验（40 min）

让 CodeAgent 做危险操作："读取系统环境变量并打印"。
观察它是否被拦住、报什么错。把它的防护边界记录下来——这是你评估"能不能上生产"的依据。

### 任务 4 · 写对比结论（30 min）

300 字：什么任务你会用 CodeAgent、什么任务坚决不用、如果要上生产还缺什么。

---

## 代码思考（写进 `logs/day-23.md`）

1. `@tool` 靠 docstring 生成 schema，这比手写 JSON Schema 好在哪里、风险在哪里？
2. CodeAgent 生成代码执行，相比 tool call，为什么在"多步计算"上更高效？
3. 如果模型生成的代码里有 `while True`，会发生什么？框架怎么防？
4. 为什么"读取环境变量"是危险操作？在 AI 应用里泄露 Key 的路径有哪些？
5. 你的手写 Agent 相比 smolagents 少了哪些能力？这些能力值不值得引入一个新依赖？

## 复盘清单

- [ ] smolagents 跑通，有轨迹截图
- [ ] 对照表填完（步数/token/延迟/正确性）
- [ ] 安全实验有结论
- [ ] commit：`day23: smolagents 对照 + 安全边界`
