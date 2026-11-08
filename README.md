# AI 应用工程师 · 8 周实战计划（40 天学习留痕）

> 11 年前端 → AI 应用工程师的转型记录：**每天 5 小时，40 天，3 个可演示项目**。
> 每个「天」都是一份可执行的课程：上午理论 + 下午代码 + 代码思考题 + 打卡模板。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Days](https://img.shields.io/badge/days-40-blue)

---

## 这是什么

不是课程笔记的堆砌，而是一套**按天排好、可执行、可验证**的转型计划：

| 项目 | 说明 |
| --- | --- |
| 周期 | 8 周 × 每周 5 天 = **40 天**，每天约 5 小时 |
| 结构 | 上午理论输入（2.5h）+ 下午动手实战（2.5h）+ 晚间复盘（1h） |
| 主线 | Python 工程 → LLM API → 提示词 → RAG → Agent / MCP → 评估 → 部署 |
| 产出 | **M1 智能资讯简报**、**M2 领域知识库问答**、**M3 Agentic 活动搭建助手** |
| 代码 | 核心链路都有可运行实现（`code/`），纯函数部分**不需要 API Key 就能跑测试** |
| 留痕 | `logs/` 每天一份复盘，`scripts/checkin.py` 一键生成 |

设计原则只有一条：**先手写原理，再用框架**。
第 3 周不用任何框架手写 RAG，第 5 周手写 Agent 循环——之后再看 LangChain / LangGraph，你才知道它们替你做了什么。

---

## 目录结构

```
.
├─ docs/                 每日课程
│  ├─ roadmap.md         八周路线与验收标准
│  ├─ schedule.md        40 天日程表（日期可重排）
│  ├─ setup.md           环境准备
│  ├─ resources.md       学习资源清单
│  ├─ patterns.md        提示词模式库
│  └─ week-01 … week-08/ 每天一份 day-XX.md
├─ code/                 每日实战代码
│  ├─ shared/            llm_client.py（生产级封装）、structured.py
│  ├─ week01 … week08/   按周实现
│  └─ week03/mini_rag/   手写 RAG（分块/向量库/BM25/RRF/评测）
├─ data/                 示例知识库与 mock 数据
├─ logs/                 每日学习留痕（打卡）
├─ scripts/              gen_schedule.py / checkin.py
├─ tests/                纯函数单测（CI 无 Key 可跑）
└─ requirements/         按周拆分的依赖
```

---

## 快速开始

```powershell
git clone https://github.com/hhy673854913-max/ai-engineer-8week-tracker.git
cd ai-engineer-8week-tracker

# 1) 纯函数自测：不需要任何 API Key
pip install -r requirements/ci.txt
pytest tests -q

# 2) 离线跑通 M1 简报（mock 数据，不调用模型）
python code/week02/m1_brief/pipeline.py --mock

# 3) 离线跑通手写 RAG 检索
python -m code.week03.mini_rag.cli index --docs data/kb_sample
python -m code.week03.mini_rag.cli query "退款多久到账" --offline

# 4) 离线跑通 M3 活动助手
python -m code.week08.activity_assistant.demo --offline

# 5) 接真实模型
copy .env.example .env   # 填入 DeepSeek / 百炼 / 智谱 任一 Key
python code/week01/day03_first_call.py "用一句话解释 RAG"
```

---

## 40 天索引

| 周 | 主题 | 里程碑 |
| --- | --- | --- |
| [W1](docs/week-01/day-01.md) | 基础切换：Python 工程化 + LLM API | `shared/llm_client.py` |
| [W2](docs/week-02/day-06.md) | 提示词工程 + 多模态 | **M1 智能简报 v2** |
| [W3](docs/week-03/day-11.md) | RAG 原理（无框架手写） | mini-RAG 原型 |
| [W4](docs/week-04/day-16.md) | RAG 工程化 + 知识库 | **M2 领域知识库问答** |
| [W5](docs/week-05/day-21.md) | Agent 与 LangGraph | 多工具 + 记忆 Agent |
| [W6](docs/week-06/day-26.md) | MCP 协议 + 多智能体 | **MCP Server** |
| [W7](docs/week-07/day-31.md) | 评估、可观测、上线 | **M2 公网 demo + 评估报告** |
| [W8](docs/week-08/day-36.md) | 毕业项目 + 求职 | **M3 + 作品集** |

<details>
<summary><b>展开 40 天完整清单</b></summary>

| Day | 课题 | Day | 课题 |
| --- | --- | --- | --- |
| [01](docs/week-01/day-01.md) | 环境与 JS→Python 语法 | [21](docs/week-05/day-21.md) | ReAct 与手写 Agent |
| [02](docs/week-01/day-02.md) | 类型注解 / Pydantic / CLI | [22](docs/week-05/day-22.md) | Function Calling 与多工具 |
| [03](docs/week-01/day-03.md) | 第一个 LLM API | [23](docs/week-05/day-23.md) | smolagents 对照 |
| [04](docs/week-01/day-04.md) | 流式输出与采样参数 | [24](docs/week-05/day-24.md) | LangGraph 状态图 |
| [05](docs/week-01/day-05.md) | 结构化输出 | [25](docs/week-05/day-25.md) | 记忆系统 |
| [06](docs/week-02/day-06.md) | 提示词两大原则 | [26](docs/week-06/day-26.md) | MCP 协议与 SDK |
| [07](docs/week-02/day-07.md) | 文本转换与模式库 | [27](docs/week-06/day-27.md) | 第一个 MCP Server |
| [08](docs/week-02/day-08.md) | CoT / Few-shot / 模板 | [28](docs/week-06/day-28.md) | MCP 资源与调试 |
| [09](docs/week-02/day-09.md) | 多模态图像理解 | [29](docs/week-06/day-29.md) | 多智能体协作 |
| [10](docs/week-02/day-10.md) | **里程碑 M1** | [30](docs/week-06/day-30.md) | M3 架构设计 |
| [11](docs/week-03/day-11.md) | 嵌入与相似度 | [31](docs/week-07/day-31.md) | 评估集构建 |
| [12](docs/week-03/day-12.md) | 文档分块 | [32](docs/week-07/day-32.md) | RAGAS 自动化评估 |
| [13](docs/week-03/day-13.md) | 向量库 | [33](docs/week-07/day-33.md) | 可观测与追踪 |
| [14](docs/week-03/day-14.md) | 完整 RAG 与引用 | [34](docs/week-07/day-34.md) | FastAPI 服务化 |
| [15](docs/week-03/day-15.md) | 混合检索与重排 | [35](docs/week-07/day-35.md) | Docker 与降本 |
| [16](docs/week-04/day-16.md) | LangChain 上手 | [36](docs/week-08/day-36.md) | M3 流水线骨架 |
| [17](docs/week-04/day-17.md) | 可配置检索链 | [37](docs/week-08/day-37.md) | M3 接入 MCP |
| [18](docs/week-04/day-18.md) | M2 设计 | [38](docs/week-08/day-38.md) | 作品集包装 |
| [19](docs/week-04/day-19.md) | M2 问答链路 | [39](docs/week-08/day-39.md) | 简历与模拟面试 |
| [20](docs/week-04/day-20.md) | **里程碑 M2** | [40](docs/week-08/day-40.md) | 投递与复盘 |

</details>

---

## 三个里程碑

| 项目 | 一句话定位 | 关键指标（示例，填你自己的） |
| --- | --- | --- |
| **M1** 智能资讯简报 | 多信源 → 结构化抽取 → 可信度排序 → 简报 | 抽取成功率、单日成本、平均可信度 |
| **M2** 领域知识库问答 | 混合检索 + 重排 + 引用溯源 + 公网 demo | hit-rate@5、Faithfulness、P95 延迟、单次成本 |
| **M3** Agentic 活动助手 | 四角色流水线 + MCP 工具复用 | 端到端耗时、一次通过率、人工修改量 |

三个项目都脱胎于真实业务经验——**面试时你能讲清每个 badcase 的业务背景**，这比"照教程做的聊天机器人"有说服力得多。

---

## 每日留痕

```powershell
python scripts/checkin.py 12        # 生成 logs/day-12.md
python scripts/checkin.py --status  # 查看 40 天进度
```

每天只写三件事：**今天产出了什么 / 卡在哪 / 明天第一件事**。
40 天之后，这 40 份日志就是你的面试素材库。

---

## 技术栈

`Python 3.11+` · `uv` · `openai SDK`（兼容 DeepSeek / 通义千问 / 智谱）· `Pydantic` · `FastAPI`
· `Chroma` · `BM25 + RRF` · `LangChain` · `LangGraph` · `MCP` · `RAGAS` · `Docker`

---

## 说明

- 本项目为个人学习路线与实现记录，代码以教学可读性优先，生产使用请补充鉴权、限流、审计与监控。
- 模型、价格、API 细节以各厂商官方文档为准；代码中的默认值仅作示例。
- 欢迎提 Issue 交流，或 Fork 后改成你自己的 40 天。

## License

[MIT](LICENSE) © 2026 洪恒洋
