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
1. BaseModel可以自动校验类型/约束 而且静态 + 运行时都能校验到类型。
2. 我觉得是有点，确保数据在流转过程中是正确的，避免运行时出错。
3. 因为`type=bool` 存在 严重的语义陷阱 ：`--json False` 会返回`True` ，且默认行为完全错误。！！！Python 的非空字符串都为 True
4. 破坏性操作最好要二次确认，避免误操作。
5. 不能，真实场景：夜间备份流水线误判
场景 ：定时任务运行`day02_cli.py scan --dir /backup/today` 检查备份完整性，随后触发下游处理。
正常情况（退出码正确区分）
`# CI 脚本
python day02_cli.py scan --dir /backup/today
case $? in
    0  process_backup ;;      # 成功，继续处理
    1  notify_ops "备份目录异常" ;;  # 业务问题，通知运维
    2  alert_critical "脚本调用错误" ;; # 配置错误，立即修复
esac`
混用之后就无法判断

## 明天第一件事



## 一句话复盘

