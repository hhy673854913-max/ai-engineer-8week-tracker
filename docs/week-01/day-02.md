# Day 02 · 类型注解、Pydantic 与 CLI 工具

> W1 · 周二 ｜ 5h ｜ 产出 `code/week01/day02_cli.py` ｜ [Day 01](day-01.md) · [Day 03](day-03.md)

**今日目标**
- 用 `typing` 给函数、容器、可选值加注解，理解"注解不执行、但工具链依赖它"
- 分清 `dataclass` 与 `Pydantic BaseModel` 的适用边界
- 写出一个**有类型、有日志、有退出码、有异常分层**的 CLI 工具

**验收**：`python code/week01/day02_cli.py scan --dir . --json` 输出结构化报告，非法参数返回退出码 2。

---

## 上午 09:00–11:30 · 理论输入

### 1. 类型注解：写给工具，也写给人

```python
from typing import Literal, Protocol, TypedDict

def load(path: str, encoding: str = "utf-8") -> str: ...
def top_k(scores: list[float], k: int = 5) -> list[tuple[int, float]]: ...

class Doc(TypedDict):
    id: str
    text: str
    score: float
```

对照 TS：

| TS | Python |
| --- | --- |
| `string \| undefined` | `str \| None`（3.10+ 可直接用 `\|`） |
| `Array<T>` / `T[]` | `list[T]` |
| `Record<string, number>` | `dict[str, number]` / `dict[str, float]` |
| `interface` | `TypedDict` / `Protocol` / `BaseModel` |
| 泛型 `<T>` | `TypeVar("T")` |
| 联合类型 | `Union[A, B]` 或 `A \| B` |

**关键认知**：Python 运行时**不检查注解**。`def f(x: int)` 传字符串照样跑。
注解的价值在于：编辑器补全、mypy/pyright 静态检查、Pydantic 运行时校验、FastAPI 自动生成文档。
所以做 AI 应用时，**注解 = 数据契约**，不是装饰。

### 2. `dataclass` vs `Pydantic`：一条判断线

```python
from dataclasses import dataclass
from pydantic import BaseModel, Field

@dataclass
class Point:
    x: float
    y: float

class EventCopy(BaseModel):
    title: str = Field(min_length=4, max_length=30)
    bullets: list[str] = Field(min_length=2, max_length=5)
    risk: Literal["low", "mid", "high"] = "low"
```

- `dataclass`：进程内部的数据容器，零校验、零依赖、快。适合领域模型、内部传参。
- `Pydantic`：**边界**上的数据——外部输入、LLM 输出、HTTP 请求体。会做类型转换 + 校验 + 报错信息。

一句话记忆：**"数据从外面进来，就用 Pydantic。"** 这是第 1 周最重要的工程习惯，Day 05 的结构化输出全靠它。

### 3. 异常处理：别写 `except Exception: pass`

```python
class AppError(Exception):
    """业务错误基类。"""

class ConfigError(AppError):
    """配置缺失/非法。"""

def read_config(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"配置文件不存在: {path}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置不是合法 JSON: {e.msg} (line {e.lineno})") from e
```

三条纪律：
1. **只捕获你知道怎么处理的异常**，其余让它冒泡
2. 用 `raise ... from e` 保留原始堆栈（面试常问）
3. 自定义异常分层：`AppError` → 具体子类，CLI 层统一翻译成退出码

### 4. `logging` 而不是 `print`

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tool")
log.info("scan done: %d files", n)   # 延迟格式化，别用 f-string 拼
```

`print` 用于"给人看的输出"，`logging` 用于"给机器和排障看的记录"。AI 应用里日志就是你的可观测性雏形（Day 33 展开）。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 用 Pydantic 定义报告模型（40 min）

```python
from pydantic import BaseModel, Field

class FileInfo(BaseModel):
    path: str
    ext: str
    size: int = Field(ge=0)
    mtime: float

class ScanReport(BaseModel):
    root: str
    total_files: int
    total_bytes: int
    by_ext: dict[str, int]
    largest: list[FileInfo]
    generated_at: str
```

### 任务 2 · argparse 子命令（40 min）

```python
sub = p.add_subparsers(dest="cmd", required=True)

scan = sub.add_parser("scan", help="扫描目录并输出统计")
scan.add_argument("--dir", type=Path, default=Path("."))
scan.add_argument("--json", action="store_true")
scan.add_argument("--top", type=int, default=10)

rename = sub.add_parser("rename", help="批量重命名（默认 dry-run）")
rename.add_argument("--dir", type=Path, required=True)
rename.add_argument("--prefix", required=True)
rename.add_argument("--apply", action="store_true", help="真正执行，不加只预览")
```

**dry-run 默认开启**是运维级习惯：破坏性操作先预览，`--apply` 才动手。

### 任务 3 · 拼装与退出码（40 min）

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "scan":
            report = scan_dir(args.dir, args.top)
            print(report.model_dump_json(indent=2) if args.json else render(report))
            return 0
        if args.cmd == "rename":
            plan = plan_rename(args.dir, args.prefix)
            apply_plan(plan) if args.apply else print_plan(plan)
            return 0
    except AppError as e:
        log.error("%s", e)
        return 1
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
```

退出码约定：`0` 成功、`1` 业务错误、`2` 用法错误。这让脚本能被 CI / 定时任务正确判断成败。

### 任务 4 · 用 mypy 找出第一处类型错误（20 min）

```powershell
uv pip install mypy
mypy code/week01/day02_cli.py --ignore-missing-imports
```

故意写一个 `report.total_files = "abc"`，看它怎么报。体会"注解不执行，但检查器会执行"。

---

## 代码思考（写进 `logs/day-02.md`）

1. `TypedDict` 和 `dataclass` 都能描述结构，为什么 FastAPI / Pydantic 选的是 `BaseModel`？
2. Pydantic 默认会做类型**转换**（`"3"` → `3`），这在 LLM 输出场景是优点还是风险？怎么关掉（`strict=True`）？
3. `argparse` 的 `--json` 为什么用 `action="store_true"` 而不是 `type=bool`？（提示：`--json False` 的坑）
4. 批量重命名时两个文件重名怎么办？设计一个"冲突解决策略"，并说明为什么不能简单覆盖。
5. 如果把退出码 1 和 2 混用，CI 会怎样误判？举一个真实场景。

## 复盘清单

- [ ] 能说清"注解不执行"这句话的两层含义
- [ ] `dataclass` / Pydantic 的边界能一句话说清
- [ ] 代码 commit：`day02: 类型注解 + Pydantic 报告 + CLI 子命令`
- [ ] `logs/day-02.md` 记录 mypy 报的第一条错
