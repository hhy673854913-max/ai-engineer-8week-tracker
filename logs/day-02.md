# Day 02 · 类型注解、Pydantic 与 CLI 工具

> 2026-11-09（排期 11-10，提前一天）｜ 对应课程：[../../docs/week-01/day-02.md](../../docs/week-01/day-02.md) ｜ 用时：约 2.5 h

## 今日产出

- 代码：`code/week01/day02_cli.py`（逐段走查 + 跑通全部验收）、`code/week01/day02_mypy_demo.py`（新增：故意写错，给 mypy 抓）
- 提交：`day02: 类型注解 + Pydantic 报告 + CLI 子命令`

## 学到什么（费曼式，3 条以内）

1. **注解是数据契约，不是运行时检查。**`def f(x: int) -> int: return x` 传 `"hello"` 照样跑通，返回 `"hello"`；价值全在工具链——编辑器补全、mypy 静态检查、Pydantic 运行时校验、FastAPI 自动生成文档。
2. **边界用 Pydantic，进程内部用 dataclass。**数据从外面进来（LLM 输出、HTTP 请求体）就用 `BaseModel`：它会转换类型（`"3"` → `3`）、给出带 `loc` 的报错、还能反射出 JSON Schema。内部传参用 dataclass：零校验、零依赖、快。
3. **异常要分层，退出码要守约定。**`AppError` → 具体子类，CLI 层统一翻译成 `0` 成功 / `1` 业务错误 / `2` 用法错误；`raise ... from e` 保住原始堆栈；日志走 `logging`（延迟格式化），`print` 只给人看。

## 卡点与解决

| 卡住的地方 | 尝试了多久 | 怎么解决的 |
| --- | --- | --- |
| `pip install mypy` 一直 `PermissionError: [Errno 13]`，卡在 `pip-unpack-*/mypy-*.whl.metadata` | 约 25 min | 先把 TMP 指到项目内 → 还是失败；写探针脚本对比，发现普通 `os.mkdir` 建的目录能写、`tempfile.mkdtemp()` 建的目录不能写，逐个查 ACL 才看到进程跑在**低完整性令牌**下（沙箱），mkdtemp 自带的目录安全描述符挡住了写入。最后一次性放宽沙箱权限装进 `.venv`，并把 `mypy>=1.11` 写进 `requirements/dev.txt` |
| CLI 的中文输出在 PowerShell 里全是 `��Ŀ¼` | 5 min | 控制台代码页是 936、Python 的 stdout 编码是 gbk，两边对不上；`$env:PYTHONIOENCODING='utf-8'` 后正常。顺带发现 `python -c "中文…"` 也会因为命令行参数编码直接崩 |
| `rename --prefix demo` 第二次跑没报冲突 | 2 min | 因为文件已经叫 `demo_001.txt`，新旧路径相同，`new_path != p` 判断把它放过了；换成 `a.txt` + 已存在的 `demo_001.txt` 才复现出 exit 1 |

## 代码思考题回答

> 题目见课程文档的「代码思考」小节，答 2–3 题即可，写出你的判断和依据。

1. **`TypedDict` / `dataclass` 都有结构，为什么 FastAPI、Pydantic 选 `BaseModel`？**
   前两者只描述"形状"，运行时什么都不做：`TypedDict` 就是给 mypy 看的 dict 别名，多一个键少一个键构造时没人拦；`dataclass` 只有 `__init__`，不校验、不转换、不会生成 JSON Schema。`BaseModel` 一次给三样：运行时校验 + 类型转换、能直接回给调用方的结构化错误（`loc`/`msg`）、可反射的 JSON Schema（FastAPI 的 `/docs` 就是它生成的）。LLM 输出这种"形状大体对、细节常错"的数据，只有第三样能兜住。

2. **Pydantic 默认做类型转换，在 LLM 输出场景是优点还是风险？**
   优点和风险是同一件事的两面。LLM 常把 `3` 写成 `"3"`、把数组写成 JSON 字符串，宽松模式能救回来、少一次重试，这是优点。风险是**静默地猜**：改错比报错更难查——比如 `"0"` 会被转成 `False`，看起来没毛病，实际是模型表达错了；金额、ID、枚举这类字段一旦被"顺手转换"，错误就流到下游了。所以做法是：默认宽松，**关键字段加 `Field(strict=True)`**，或者整个模型 `model_config = ConfigDict(strict=True)`，让不该转的地方直接报错、走重试。

3. **`argparse` 的 `--json` 为什么用 `action="store_true"` 而不是 `type=bool`？**
   `type=bool` 拿到的是命令行字符串，`bool("False")` 是 `True`（非空字符串恒真），于是 `--json False` 反而打开了开关，还要求用户写成 `--json=true` 这种别扭形式。`store_true` 表达的是"出现即真、不出现即假"的开关语义，干净且不吞后面的位置参数。真需要三态就用 `argparse.BooleanOptionalAction`（3.9+），自动生成 `--json/--no-json`。

4. **（加分）批量重命名撞名怎么办？**今天现场撞到了：`plan_rename` 遇到目标已存在就 `raise`，整个计划直接失败。安全，但脆——999 个文件会因为有 1 个冲突而全部不动。更好的做法是两阶段：先算出完整的 `旧名 → 新名` 计划表，再和"已存在的路径集合"求差集；冲突时按策略处理（跳过并记录 / 追加 `_1`、`_2` 到空闲 / 内容哈希后缀）。**不能简单覆盖**：`rename` 不幂等，覆盖之后没有撤销路径，同名不同内容的文件就真没了；业界的做法是先落一份 manifest，失败可逆。

## 明天第一件事

- Day 03 · 第一个大模型 API 调用：读 `docs/week-01/day-03.md`，产出 `code/shared/llm_client.py`，验收命令 `python -m shared.llm_client "用一句话解释 RAG"` 能返回答案并打印 token 与预估成本。
- 开工前先确认 `.env` 里有可用的 API Key（没有就先按 `docs/setup.md` 配好，别把 key 提交进去）。

## 一句话复盘

> 今天真正落地的一句话是"注解不执行，但检查器执行"——同一份 `day02_mypy_demo.py`，mypy 一行行报出 6 个错，`python` 跑起来却一个都不拦；所以类型的价值不在"防止运行时出错"，而在"把错误提前到提交之前"。
