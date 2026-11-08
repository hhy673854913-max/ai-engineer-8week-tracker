# 40 天日程表

> 建议起始日：**2026-11-09（周一）**，毕业日：**2027-01-01**。
> 每周 5 天学习、周末留白（补进度 / 整理笔记 / 休息）。在职转型可按「隔天推进」拉成 16 周。
> 需要改日期：`python scripts/gen_schedule.py --start 2027-03-01`，本文件会自动重写。

## 阶段总览

| 周次 | 日期 | 主题 | 里程碑 |
| --- | --- | --- | --- |
| W1 · 基础切换 | 11-09 ~ 11-13 | 环境与语法：从 JS 迁移到 Python | `llm_client.py` |
| W2 · 提示词与多模态 | 11-16 ~ 11-20 | 提示词工程系统化 + 多模态 + M1 | **M1 智能简报 v2** |
| W3 · RAG 原理 | 11-23 ~ 11-27 | RAG 基础链路（无框架手写） | mini-RAG 原型 |
| W4 · RAG 工程化 | 11-30 ~ 12-04 | RAG 工程化 + M2 知识库问答 | **M2 知识库问答** |
| W5 · Agent 基础 | 12-07 ~ 12-11 | Agent 基础与 LangGraph | 多工具 + 记忆 Agent |
| W6 · MCP 与多智能体 | 12-14 ~ 12-18 | MCP 协议 + 多智能体 + M3 设计 | **MCP Server** |
| W7 · 评估与上线 | 12-21 ~ 12-25 | 评估、可观测与服务化上线 | **M2 上线 + 评估报告** |
| W8 · 毕业与求职 | 12-28 ~ 01-01 | 毕业项目整合 + 求职冲刺 | **M3 + 作品集** |

## 逐日安排

| Day | 日期 | 星期 | 今日课题 | 今日产出 | 详情 |
| --- | --- | --- | --- | --- | --- |
| 01 | 11-09 | 周一 | 环境管理与 JS→Python 语法迁移 | `day01_md5.py` | [打开](week-01/day-01.md) |
| 02 | 11-10 | 周二 | 类型注解、Pydantic 与 CLI 工具 | `day02_cli.py` | [打开](week-01/day-02.md) |
| 03 | 11-11 | 周三 | 第一个大模型 API 调用 | `llm_client.py v0` | [打开](week-01/day-03.md) |
| 04 | 11-12 | 周四 | 流式输出与采样参数 | `day04_stream_chat.py` | [打开](week-01/day-04.md) |
| 05 | 11-13 | 周五 | 结构化输出与文案生成器 | `day05_event_copy.py` | [打开](week-01/day-05.md) |
| 06 | 11-16 | 周一 | 提示词两大原则 | `day06_prompt_basics.py` | [打开](week-02/day-06.md) |
| 07 | 11-17 | 周二 | 文本转换与提示词模式库 | `day07_prompt_patterns.py` | [打开](week-02/day-07.md) |
| 08 | 11-18 | 周三 | 思维链、少样本与结构化模板 | `day08_extract_prompt.py` | [打开](week-02/day-08.md) |
| 09 | 11-19 | 周四 | 多模态图像理解 | `day09_vision.py` | [打开](week-02/day-09.md) |
| 10 | 11-20 | 周五 | 里程碑 M1：智能简报 v2 | `m1_brief/` | [打开](week-02/day-10.md) |
| 11 | 11-23 | 周一 | 嵌入向量与语义相似度 | `week03/mini_rag/similarity.py` | [打开](week-03/day-11.md) |
| 12 | 11-24 | 周二 | 文档加载与分块策略 | `week03/mini_rag/chunking.py` | [打开](week-03/day-12.md) |
| 13 | 11-25 | 周三 | 向量库与语义检索 | `week03/mini_rag/store.py` | [打开](week-03/day-13.md) |
| 14 | 11-26 | 周四 | 完整 RAG 链路与引用溯源 | `week03/mini_rag/rag.py` | [打开](week-03/day-14.md) |
| 15 | 11-27 | 周五 | 混合检索与重排序 | `week03/mini_rag/hybrid.py` | [打开](week-03/day-15.md) |
| 16 | 11-30 | 周一 | LangChain 快速上手 | `week04/langchain_rag.py` | [打开](week-04/day-16.md) |
| 17 | 12-01 | 周二 | LCEL 与可配置检索链 | `week04/configurable_chain.py` | [打开](week-04/day-17.md) |
| 18 | 12-02 | 周三 | M2 设计：领域知识库 | `data/kb/ + 设计文档` | [打开](week-04/day-18.md) |
| 19 | 12-03 | 周四 | M2 开发一：问答链路与 Badcase | `m2_kb/qa_chain.py` | [打开](week-04/day-19.md) |
| 20 | 12-04 | 周五 | M2 开发二：引用溯源界面 | `m2_kb/web/` | [打开](week-04/day-20.md) |
| 21 | 12-07 | 周一 | ReAct 与手写 Agent 循环 | `week05/agent_loop.py` | [打开](week-05/day-21.md) |
| 22 | 12-08 | 周二 | Function Calling 与多工具编排 | `week05/tools.py` | [打开](week-05/day-22.md) |
| 23 | 12-09 | 周三 | smolagents 对照实践 | `week05/smol_demo.py` | [打开](week-05/day-23.md) |
| 24 | 12-10 | 周四 | LangGraph 状态图 | `week05/langgraph_agent.py` | [打开](week-05/day-24.md) |
| 25 | 12-11 | 周五 | 记忆系统 | `week05/memory.py` | [打开](week-05/day-25.md) |
| 26 | 12-14 | 周一 | MCP 协议与官方 SDK | `week06/mcp_hello.py` | [打开](week-06/day-26.md) |
| 27 | 12-15 | 周二 | 开发第一个 MCP Server | `week06/mcp_server_news.py` | [打开](week-06/day-27.md) |
| 28 | 12-16 | 周三 | MCP 进阶：资源、提示与调试 | `week06/mcp_server_kb.py` | [打开](week-06/day-28.md) |
| 29 | 12-17 | 周四 | 多智能体协作 | `week06/multi_agent.py` | [打开](week-06/day-29.md) |
| 30 | 12-18 | 周五 | M3 架构设计 | `docs/week-06/m3-design.md` | [打开](week-06/day-30.md) |
| 31 | 12-21 | 周一 | 评估方法论与评估集 | `week07/eval/eval_set.jsonl` | [打开](week-07/day-31.md) |
| 32 | 12-22 | 周二 | RAGAS 自动化评估 | `week07/eval/run_ragas.py` | [打开](week-07/day-32.md) |
| 33 | 12-23 | 周三 | 可观测性与链路追踪 | `week07/observability.py` | [打开](week-07/day-33.md) |
| 34 | 12-24 | 周四 | FastAPI 服务化 | `week07/api/main.py` | [打开](week-07/day-34.md) |
| 35 | 12-25 | 周五 | Docker 部署与降本实验 | `week07/api/Dockerfile` | [打开](week-07/day-35.md) |
| 36 | 12-28 | 周一 | M3 开发一：多智能体流水线 | `week08/activity_assistant/graph.py` | [打开](week-08/day-36.md) |
| 37 | 12-29 | 周二 | M3 开发二：接入 MCP 端到端 | `week08/activity_assistant/demo.py` | [打开](week-08/day-37.md) |
| 38 | 12-30 | 周三 | 作品集与 README 打磨 | `各项目 README` | [打开](week-08/day-38.md) |
| 39 | 12-31 | 周四 | 简历重写与模拟面试 | `resume/ 两版简历` | [打开](week-08/day-39.md) |
| 40 | 01-01 | 周五 | 投递、复盘与长期路线 | `投递记录表` | [打开](week-08/day-40.md) |

## 打卡方式

```powershell
python scripts/checkin.py 12     # 生成 logs/day-12.md 并标记进度
python scripts/checkin.py --status   # 看整体进度
```

打卡不是形式主义：`logs/day-XX.md` 里写清『今天学了什么 / 卡在哪 / 明天第一件事』，
八周之后这 40 篇就是你面试时讲 badcase 与取舍的原始素材。
