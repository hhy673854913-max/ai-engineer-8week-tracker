# 学习资源清单

> 使用纪律：**主线课程按周推进，官方文档当字典查，资讯限时看。**
> 最常见的失败模式是把 80% 时间花在"收藏和对比资料"上——清单已经筛完了，直接开干。

## 1. 中文系统课程（免费）

| 资源 | 地址 | 用途 |
| --- | --- | --- |
| llm-universe | github.com/datawhalechina/llm-universe | 大模型应用开发全流程，W1–W4 主线 |
| llm-cookbook | github.com/datawhalechina/llm-cookbook | 吴恩达系列中文实践版，W2 主线 |
| prompt-engineering-for-developers | github.com/datawhalechina/prompt-engineering-for-developers | 提示词工程中文教程，W2 配套 |
| hugging-multi-agent | github.com/datawhalechina/hugging-multi-agent | 多智能体开发，W6 配套 |
| learn-python-the-smart-way-v2 | github.com/datawhalechina/learn-python-the-smart-way-v2 | Python 语法速成，W1 对照 |
| self-llm | github.com/datawhalechina/self-llm | 开源模型部署与微调（八周后进阶） |
| happy-llm | github.com/datawhalechina/happy-llm | 大模型原理科普，通勤阅读 |

## 2. 国际课程（免费）

| 资源 | 地址 | 用途 |
| --- | --- | --- |
| ChatGPT Prompt Engineering for Developers | deeplearning.ai/short-courses | 提示词经典课（1.5h），W2 必学 |
| Building and Evaluating Advanced RAG | deeplearning.ai/short-courses | RAG 进阶与评估，W3–W4 / W7 |
| AI Agents in LangGraph | deeplearning.ai/short-courses | LangGraph，W5 |
| Hugging Face Agents Course | huggingface.co/learn/agents-course | Agent 系统课（有中文版），W5–W6 |
| Functions, Tools and Agents with LangChain | deeplearning.ai/short-courses | 工具调用基础，W5 |

## 3. 官方文档（边做边查，不要求通读）

| 文档 | 地址 | 对应天 |
| --- | --- | --- |
| OpenAI 兼容 API 参考 | platform.openai.com/docs/api-reference | Day 03–05 |
| DeepSeek API | api-docs.deepseek.com | Day 03 |
| 通义千问（百炼） | help.aliyun.com/zh/model-studio | Day 03 / 09 / 11 |
| Chroma | docs.trychroma.com | Day 13 |
| LangChain（Python） | python.langchain.com | Day 16–17 |
| LangGraph | langchain-ai.github.io/langgraph | Day 24–25 |
| MCP 官方文档 | modelcontextprotocol.io | Day 26–28 |
| FastAPI（中文） | fastapi.tiangolo.com/zh | Day 34 |
| RAGAS | docs.ragas.io | Day 32 |
| Langfuse | langfuse.com/docs | Day 33 |
| Prompt Engineering Guide（中文） | promptingguide.ai/zh | Day 06–08 |
| Docker | docs.docker.com/get-started | Day 35 |

## 4. 视频与社区

- **B 站 · 同济子豪兄**：吴恩达课程中文精讲、RAG / Agent 实战。
- **B 站 · Datawhale**：开源课程配套视频。
- **Datawhale 社区**：组队学习 + 打卡群，自学期的自律神器。
- **Hugging Face 中文社区**：模型与数据集实践讨论。
- **信息源**：机器之心 / 量子位（行业）+ 模型官方公众号（API 变更），每周固定 30 分钟。

## 5. 面试自测清单

| 主题 | 高频问题 |
| --- | --- |
| RAG | 完整链路；分块怎么选；检索不准怎么排查；幻觉怎么缓解；引用溯源怎么实现 |
| Agent | ReAct 原理；工具调用失败怎么处理；多智能体何时优于单 Agent；LangGraph 状态设计 |
| MCP | 解决什么问题；Host/Client/Server 架构；与直接 Function Calling 的区别 |
| 评估 | 怎么建评估集；LLM-as-judge 的坑；上线后怎么持续监控 |
| 工程化 | 流式实现；成本控制；缓存策略；错误重试设计 |
| 项目深挖 | 架构取舍、badcase 复盘、"如果重来会怎么改" |
