# Day 37 · M3 开发（二）：接入 MCP，端到端打通

> W8 · 周二 ｜ 5h ｜ 产出 `code/week08/activity_assistant/demo.py` ｜ [Day 36](day-36.md) · [Day 38](day-38.md)

**今日目标**
- 把 M1（资讯）与 M2（知识库）的 MCP Server 接进 M3
- 完成"一句话需求 → 活动页代码骨架 + 自检报告"的端到端演示
- 补上质量检查角色，形成完整四角色流水线

**验收**：一条命令跑完全流程，输出 `runs/{run_id}/`（含 index.html、assets.md、review.md、timeline.json）。

---

## 上午 09:00–11:30 · 集成要点

### 1. 三个 MCP 连接的生命周期

```python
async with AsyncExitStack() as stack:
    sessions = {}
    for name, params in SERVERS.items():
        read, write = await stack.enter_async_context(stdio_client(params))
        s = await stack.enter_async_context(ClientSession(read, write))
        await s.initialize()
        sessions[name] = s
    yield sessions
```

**连接是有成本的**（启动子进程 + 握手）。不要每个请求都连一次——在应用启动时建立，全局复用。

### 2. 工具名冲突与前缀

```python
def namespaced(tools: list, prefix: str) -> list[dict]:
    out = []
    for t in tools:
        schema = {"type": "function", "function": {
            "name": f"{prefix}_{t.name}",
            "description": t.description or "",
            "parameters": t.inputSchema,
        }}
        out.append(schema)
    return out
```

调用时按前缀路由回对应 session：

```python
def split_name(name: str, sessions: dict) -> tuple[str, str]:
    prefix, _, rest = name.partition("_")
    if prefix not in sessions:
        raise ValueError(f"未知工具前缀: {name}")
    return prefix, rest
```

**下划线分隔有歧义**（`kb_search` 是 `kb` + `search` 还是 `kb_search` + 空？），更稳妥的是 `kb.search` 或在注册表里显式维护映射。

### 3. M3 里 MCP 用来干什么

| 角色 | 用的工具 | 用途 |
| --- | --- | --- |
| 分析师 | `kb_search` | 查历史活动规则，判断玩法是否冲突 |
| 素材 | `query_news` | 找近期热点，生成应景文案 |
| 检查员 | `kb_search` | 核对奖励名称、合规条款是否与知识库一致 |

**不是"为了用 MCP 而用"**：每个调用都要能说清"没有它，这一步会差在哪"。

### 4. 端到端的时间线

```json
{
  "run_id": "20261229-101533",
  "requirement": "...",
  "steps": [
    {"name": "analyst", "ms": 2100, "tokens": 900},
    {"name": "asset", "ms": 3400, "tokens": 1500, "mcp_calls": 2},
    {"name": "coder", "ms": 8200, "tokens": 3100},
    {"name": "reviewer", "ms": 1900, "tokens": 800},
    {"name": "revise", "ms": 6100, "tokens": 2400}
  ],
  "total_ms": 21700,
  "total_cost_cny": 0.21
}
```

**这份 timeline 就是"3 天 → 1 天"叙事的量化支撑**：21.7 秒生成初稿，人工修改 2 小时 vs 原来 3 天。

### 5. 演示脚本要"可重复"

```python
DEMOS = [
    "做一个情人节双人组队活动，奖励是限定皮肤",
    "做一个春节签到活动，7 天领奖励",
    "做一个周年庆抽奖活动（故意缺信息，触发澄清）",
]
```

每次跑用固定需求，输出可对比。**别每次换需求演示**，那样无法说明改进。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 接入 MCP（70 min）

```python
class ActivityAssistant:
    def __init__(self, llm, sessions: dict[str, ClientSession], config: AppConfig):
        self.llm, self.sessions, self.config = llm, sessions, config
        self.registry = ToolRegistry()

    async def load_tools(self) -> None:
        for prefix, session in self.sessions.items():
            tools = await session.list_tools()
            for t in tools.tools:
                self.registry.register(MCPTool(prefix, t, session))
```

### 任务 2 · 补上检查员（60 min）

```python
def reviewer(state: M3State) -> dict:
    issues = rule_checks(state["code"].files[0]["content"])
    llm_review = llm.chat(REVIEW_PROMPT.format(code=truncate(state["code"].files[0]["content"], 6000)),
                          json_mode=True, temperature=0)
    report = ReviewReport(**json.loads(extract_json(llm_review)),
                          issues=issues + json.loads(extract_json(llm_review))["issues"])
    return {"review": report}
```

规则问题（error）+ LLM 问题（warn/info）合并，`verdict` 由"是否有 error"决定——**硬错误一票否决**。

### 任务 3 · 端到端（60 min）

跑 3 个 DEMO，产出：

```
runs/20261229-101533/
├─ index.html
├─ assets.md
├─ review.md
├─ timeline.json
└─ requirement.json
```

检查：页面能打开、素材清单完整、review 有具体问题、timeline 有每步耗时。

### 任务 4 · 60 秒演示视频（30 min）

脚本：
1. `0-10s`：说清"输入一句需求，输出活动页骨架"
2. `10-30s`：跑一遍，展示中间步骤（分析师输出、代码生成）
3. `30-45s`：打开生成的页面，展示功能
4. `45-60s`：展示 timeline 与成本（"21 秒，0.2 元"）

---

## 代码思考（写进 `logs/day-37.md`）

1. MCP 连接为什么要在启动时建立？每个请求建一次会怎样（启动子进程的成本）？
2. 工具名前缀用下划线有歧义，你会怎么设计命名规则？
3. 规则检查与 LLM 检查结果冲突（规则说没问题，LLM 说有问题），采信谁？
4. timeline 数据怎么支撑"3 天 → 1 天"？需要补哪些人工环节的耗时？
5. 如果 MCP Server 挂了，M3 应该整体失败还是降级？降级后哪些角色受影响？

## 复盘清单

- [ ] MCP 工具接进 M3，调用链可见
- [ ] 四角色完整跑通
- [ ] 三个 DEMO 产出可对比
- [ ] 演示视频录好
- [ ] commit：`M3: 接入 MCP + 四角色端到端`
