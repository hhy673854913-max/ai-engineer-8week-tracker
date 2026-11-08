"""生成 40 天日程表（docs/schedule.md）。

用途：把"第几天 → 哪天 → 学什么"固定下来，避免每天早上的选择成本。
改日期只需改 START_DATE 或传 --start，然后重新运行：

    python scripts/gen_schedule.py --start 2026-11-09
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "schedule.md"
START_DATE = date(2026, 11, 9)  # 周一

# (周主题, [(今日课题, 今日产出, 文档路径)])
WEEKS: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "环境与语法：从 JS 迁移到 Python",
        [
            ("环境管理与 JS→Python 语法迁移", "day01_md5.py", "week-01/day-01.md"),
            ("类型注解、Pydantic 与 CLI 工具", "day02_cli.py", "week-01/day-02.md"),
            ("第一个大模型 API 调用", "llm_client.py v0", "week-01/day-03.md"),
            ("流式输出与采样参数", "day04_stream_chat.py", "week-01/day-04.md"),
            ("结构化输出与文案生成器", "day05_event_copy.py", "week-01/day-05.md"),
        ],
    ),
    (
        "提示词工程系统化 + 多模态 + M1",
        [
            ("提示词两大原则", "day06_prompt_basics.py", "week-02/day-06.md"),
            ("文本转换与提示词模式库", "day07_prompt_patterns.py", "week-02/day-07.md"),
            ("思维链、少样本与结构化模板", "day08_extract_prompt.py", "week-02/day-08.md"),
            ("多模态图像理解", "day09_vision.py", "week-02/day-09.md"),
            ("里程碑 M1：智能简报 v2", "m1_brief/", "week-02/day-10.md"),
        ],
    ),
    (
        "RAG 基础链路（无框架手写）",
        [
            ("嵌入向量与语义相似度", "week03/mini_rag/similarity.py", "week-03/day-11.md"),
            ("文档加载与分块策略", "week03/mini_rag/chunking.py", "week-03/day-12.md"),
            ("向量库与语义检索", "week03/mini_rag/store.py", "week-03/day-13.md"),
            ("完整 RAG 链路与引用溯源", "week03/mini_rag/rag.py", "week-03/day-14.md"),
            ("混合检索与重排序", "week03/mini_rag/hybrid.py", "week-03/day-15.md"),
        ],
    ),
    (
        "RAG 工程化 + M2 知识库问答",
        [
            ("LangChain 快速上手", "week04/langchain_rag.py", "week-04/day-16.md"),
            ("LCEL 与可配置检索链", "week04/configurable_chain.py", "week-04/day-17.md"),
            ("M2 设计：领域知识库", "data/kb/ + 设计文档", "week-04/day-18.md"),
            ("M2 开发一：问答链路与 Badcase", "m2_kb/qa_chain.py", "week-04/day-19.md"),
            ("M2 开发二：引用溯源界面", "m2_kb/web/", "week-04/day-20.md"),
        ],
    ),
    (
        "Agent 基础与 LangGraph",
        [
            ("ReAct 与手写 Agent 循环", "week05/agent_loop.py", "week-05/day-21.md"),
            ("Function Calling 与多工具编排", "week05/tools.py", "week-05/day-22.md"),
            ("smolagents 对照实践", "week05/smol_demo.py", "week-05/day-23.md"),
            ("LangGraph 状态图", "week05/langgraph_agent.py", "week-05/day-24.md"),
            ("记忆系统", "week05/memory.py", "week-05/day-25.md"),
        ],
    ),
    (
        "MCP 协议 + 多智能体 + M3 设计",
        [
            ("MCP 协议与官方 SDK", "week06/mcp_hello.py", "week-06/day-26.md"),
            ("开发第一个 MCP Server", "week06/mcp_server_news.py", "week-06/day-27.md"),
            ("MCP 进阶：资源、提示与调试", "week06/mcp_server_kb.py", "week-06/day-28.md"),
            ("多智能体协作", "week06/multi_agent.py", "week-06/day-29.md"),
            ("M3 架构设计", "docs/week-06/m3-design.md", "week-06/day-30.md"),
        ],
    ),
    (
        "评估、可观测与服务化上线",
        [
            ("评估方法论与评估集", "week07/eval/eval_set.jsonl", "week-07/day-31.md"),
            ("RAGAS 自动化评估", "week07/eval/run_ragas.py", "week-07/day-32.md"),
            ("可观测性与链路追踪", "week07/observability.py", "week-07/day-33.md"),
            ("FastAPI 服务化", "week07/api/main.py", "week-07/day-34.md"),
            ("Docker 部署与降本实验", "week07/api/Dockerfile", "week-07/day-35.md"),
        ],
    ),
    (
        "毕业项目整合 + 求职冲刺",
        [
            ("M3 开发一：多智能体流水线", "week08/activity_assistant/graph.py", "week-08/day-36.md"),
            ("M3 开发二：接入 MCP 端到端", "week08/activity_assistant/demo.py", "week-08/day-37.md"),
            ("作品集与 README 打磨", "各项目 README", "week-08/day-38.md"),
            ("简历重写与模拟面试", "resume/ 两版简历", "week-08/day-39.md"),
            ("投递、复盘与长期路线", "投递记录表", "week-08/day-40.md"),
        ],
    ),
]

WEEK_NAMES = [
    "W1 · 基础切换",
    "W2 · 提示词与多模态",
    "W3 · RAG 原理",
    "W4 · RAG 工程化",
    "W5 · Agent 基础",
    "W6 · MCP 与多智能体",
    "W7 · 评估与上线",
    "W8 · 毕业与求职",
]

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五"]


def build(start: date) -> str:
    lines: list[str] = []
    lines += [
        "# 40 天日程表",
        "",
        f"> 建议起始日：**{start:%Y-%m-%d}（周一）**，毕业日：**{start + timedelta(weeks=7, days=4):%Y-%m-%d}**。",
        "> 每周 5 天学习、周末留白（补进度 / 整理笔记 / 休息）。在职转型可按「隔天推进」拉成 16 周。",
        "> 需要改日期：`python scripts/gen_schedule.py --start 2027-03-01`，本文件会自动重写。",
        "",
        "## 阶段总览",
        "",
        "| 周次 | 日期 | 主题 | 里程碑 |",
        "| --- | --- | --- | --- |",
    ]
    milestones = [
        "`llm_client.py`",
        "**M1 智能简报 v2**",
        "mini-RAG 原型",
        "**M2 知识库问答**",
        "多工具 + 记忆 Agent",
        "**MCP Server**",
        "**M2 上线 + 评估报告**",
        "**M3 + 作品集**",
    ]
    for w in range(8):
        monday = start + timedelta(weeks=w)
        friday = monday + timedelta(days=4)
        lines.append(
            f"| {WEEK_NAMES[w]} | {monday:%m-%d} ~ {friday:%m-%d} | {WEEKS[w][0]} | {milestones[w]} |"
        )

    lines += ["", "## 逐日安排", "", "| Day | 日期 | 星期 | 今日课题 | 今日产出 | 详情 |", "| --- | --- | --- | --- | --- | --- |"]
    d = 0
    for w, (_, days) in enumerate(WEEKS):
        for i, (title, output, path) in enumerate(days):
            d += 1
            day = start + timedelta(weeks=w, days=i)
            lines.append(
                f"| {d:02d} | {day:%m-%d} | {WEEKDAYS[i]} | {title} | `{output}` | [打开]({path}) |"
            )

    lines += [
        "",
        "## 打卡方式",
        "",
        "```powershell",
        "python scripts/checkin.py 12     # 生成 logs/day-12.md 并标记进度",
        "python scripts/checkin.py --status   # 看整体进度",
        "```",
        "",
        "打卡不是形式主义：`logs/day-XX.md` 里写清『今天学了什么 / 卡在哪 / 明天第一件事』，",
        "八周之后这 40 篇就是你面试时讲 badcase 与取舍的原始素材。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=START_DATE, help="起始日期，如 2026-11-09")
    args = parser.parse_args()
    content = build(args.start)
    OUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(content.splitlines())} lines)")


if __name__ == "__main__":
    main()
