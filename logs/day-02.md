# Day 02 · 类型注解、Pydantic 与 CLI 工具

> 2026-11-09（排期 11-10，提前一天）｜ 对应课程：[../../docs/week-01/day-02.md](../../docs/week-01/day-02.md) ｜ 用时：约 2.5 h

## 今日产出

- 代码：`code/week01/day02_cli.py`（逐段走查 + 跑通全部验收）、`code/week01/day02_mypy_demo.py`（新增：故意写错，给 mypy 抓）

## 学到什么（费曼式，3 条以内）

1. py的类型注释，`dataclass` vs `Pydantic`，数据在自己进程内部流转用 dataclass，跨过信任边界（模型、用户、网络）就用 Pydantic。

2. 异常处理分层 AppError（业务错误基类）、ConfigError（配置错误基类）。以及对应代码实践

3. `print` 用于"给人看的输出"，`logging` 用于"给机器和排障看的记录"，logging用法学习





## 卡点与解决

| 卡住的地方 | 尝试了多久 | 怎么解决的 |
| --- | --- | --- |
| uv pip install mypy 报错 | 1分钟 | 询问AI，使用pip安装以及直接用powershell装uv |

## 代码思考题回答

> 题目见课程文档的「代码思考」小节，答 2–3 题即可，写出你的判断和依据。
1. BaseModel可以自动校验类型/约束

## 明天第一件事



## 一句话复盘

