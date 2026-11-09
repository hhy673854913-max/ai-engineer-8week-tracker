# Day 26 · MCP 协议精读与官方 SDK 跑通

> W6 · 周一 ｜ 5h ｜ 产出 `code/week06/mcp_hello.py` ｜ [Day 25](../week-05/day-25.md)

**今日目标**
- 讲清 MCP 解决什么问题、Host/Client/Server 三方各是什么
- 记住三个原语：**Tools / Resources / Prompts**，以及它们与 Function Calling 的关系
- 用官方 Python SDK 跑通一个最小 Server，并被客户端调用成功

**验收**：`mcp dev code/week06/mcp_hello.py` 或用 Inspector 连上，能看到并调用 `add` 工具。

---

## 上午 09:00–11:30 · 理论

### 1. MCP 解决什么问题

没有 MCP 时，每个 AI 应用要自己接一遍：文件系统、数据库、GitHub、日历……每个客户端 × 每个工具 = N×M 份适配。

MCP 把它变成：**工具方实现一次 Server，任何支持 MCP 的客户端都能用**。

```text
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Host (IDE)  │──►   │  MCP Client  │──►   │  MCP Server  │
│  用户界面     │      │  协议实现     │      │  你的工具     │
└──────────────┘      └──────────────┘      └──────────────┘
        │                     │                     │
        │  1:1 连接           │  JSON-RPC 2.0       │  访问文件/API/DB
```

- **Host**：面向用户的应用（Claude Desktop、Cursor、你自己的 Agent）
- **Client**：Host 内部为每个 Server 建立的连接，负责协议握手与消息路由
- **Server**：暴露能力的进程（可以本地 stdio，也可以远程 HTTP）

一句话：**MCP 是"AI 应用的工具插座标准"**，类比 USB-C。

### 2. 三个原语

| 原语 | 谁控制 | 用途 | 例子 |
| --- | --- | --- | --- |
| **Tools** | 模型决定调用 | 有副作用的动作 | `query_news`、`create_issue` |
| **Resources** | 应用决定加载 | 只读数据 | `file:///docs/a.md`、`db://orders/123` |
| **Prompts** | 用户主动选择 | 预置提示模板 | `/summarize`、`/review` |

区别很关键：
- Tool 是"模型想做什么"
- Resource 是"应用想给模型看什么"
- Prompt 是"用户想怎么问"

### 3. 传输方式

| 传输 | 场景 | 说明 |
| --- | --- | --- |
| `stdio` | 本地进程 | Host 启动子进程，走标准输入输出。最简单 |
| Streamable HTTP | 远程服务 | 正式规范里的远程方式（SSE 已逐步被取代） |
| SSE（旧） | 远程 | 兼容老客户端时还会遇到 |

本地开发 99% 用 stdio。

在 M3 里你会用 stdio 同时拉起 M1、M2 两个 Server——它们就是 Agent 的子进程，跟着 Agent 一起启停，这也是为什么 Day 27 的日志不能写 stdout。等这套东西要给别的团队远程调用，才换成 Streamable HTTP，而此时"谁能调、能调哪几个工具"必须你自己在 Server 里判，协议层不会替你挡。

### 4. MCP 与 Function Calling 的关系

| | Function Calling | MCP |
| --- | --- | --- |
| 层级 | 模型 API 的能力 | 应用之间的协议 |
| 工具从哪来 | 你在请求里传 schema | 从 Server 动态发现（`tools/list`） |
| 跨应用复用 | 不能 | 能 |
| 谁执行 | 你的代码 | Server |

**MCP 不替代 Function Calling**：Host 拿到 Server 的工具列表后，通常还是把它们转成 Function Calling 的 schema 交给模型。

### 5. 协议消息长什么样（JSON-RPC）

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"1.0"}}}
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":{"name":"hello","version":"0.1.0"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"add","arguments":{"a":1,"b":2}}}
```

生命周期：`initialize` → `initialized` 通知 → 正常请求 → `shutdown`。
**握手失败是最常见的连接问题**，先看协议版本是否兼容。

JSON-RPC 2.0 就是"用 JSON 传远程调用"的约定：请求带 `jsonrpc` / `id` / `method` / `params`，服务端用同一个 `id` 回 `result` 或 `error`，MCP 的每一条消息都是这个壳。平时用 SDK 你看不到它，但握手失败、工具名对不上、客户端收不到响应时，抓的就是这几行——面试问"MCP 底层怎么通信"答的就是这个。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 安装与最小 Server（60 min）

```powershell
uv pip install "mcp[cli]"
```

```python
# code/week06/mcp_hello.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hello")

@mcp.tool()
def add(a: int, b: int) -> int:
    """两数相加。"""
    return a + b

@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """返回一句问候。"""
    return f"你好，{name}！"

@mcp.prompt()
def summarize(text: str) -> str:
    """摘要提示模板。"""
    return f"请用 3 句话总结：\n{text}"

if __name__ == "__main__":
    mcp.run()   # 默认 stdio
```

FastMCP 是官方 SDK 上的一层封装，定位类似 FastAPI：你写普通函数挂 `@mcp.tool()`，它负责生成 `tools/list` 要的 schema、接住 `tools/call`、把返回值包成 JSON-RPC 响应——上午那些报文它替你发了。真实项目里绝大多数 Server 都这么写，只有调不通时才回头抓报文。

### 任务 2 · 用 Inspector 调试（40 min）

```powershell
uv run mcp dev code/week06/mcp_hello.py
```

Inspector 是官方调试工具，能列出 tools/resources/prompts，直接调用并看返回。
**每一步都截图**——这是你 README 里最有说服力的证据。

### 任务 3 · 手写客户端调用（60 min）

不依赖 Inspector，用 SDK 的客户端 API 走一遍 stdio 连接：

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command="python", args=["code/week06/mcp_hello.py"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print([t.name for t in tools.tools])
            result = await session.call_tool("add", {"a": 1, "b": 2})
            print(result.content[0].text)

asyncio.run(main())
```

**这一步必须自己写**：面试问"MCP 客户端怎么连 Server"，答得出代码细节的人不多。

### 任务 4 · 接进 Claude Desktop / Cursor（30 min）

配置示例（Claude Desktop 的 `claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "hello": {
      "command": "uv",
      "args": ["run", "--directory", "C:/space/AI学习/ai-engineer-8week-tracker", "python", "code/week06/mcp_hello.py"]
    }
  }
}
```

启动后问"用 add 工具算 1+2"，看它是否调用。**Windows 路径要用正斜杠或双反斜杠**，这是最常见的配置错误。

---

## 代码思考（写进 `logs/day-26.md`）

1. MCP 的 Tools / Resources / Prompts 三原语，为什么"谁控制"是区分它们的关键？
2. 为什么 stdio 是最常用的本地传输？它有什么天然限制（并发、日志污染）？
3. MCP 工具列表是动态发现的，这对"模型上下文"有什么影响？工具太多会怎样？
4. `initialize` 握手失败，你会按什么顺序排查？
5. 如果公司要接内部系统（订单库），你会做成 MCP Server 还是普通 API？判断依据是什么？

## 复盘清单

- [ ] 最小 Server 跑通，Inspector 能调用
- [ ] 手写客户端能连上并 call_tool
- [ ] 接进至少一个 Host（Desktop/Cursor/自己写的 Agent）
- [ ] commit：`day26: MCP 最小 Server + 手写客户端`
