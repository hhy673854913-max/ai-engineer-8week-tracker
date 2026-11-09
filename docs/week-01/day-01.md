# Day 01 · 环境管理与 JS→Python 语法迁移

> W1 · 周一 ｜ 5h ｜ 产出 `code/week01/day01_md5.py` ｜ [日程表](../schedule.md)

**今日目标**
- 用 `uv` 建立可复现的 Python 环境，说清「解释器 / 虚拟环境 / 依赖锁定」三者的关系
- 用 JS 心智模型快速映射 Python 语法，识别 **5 个会咬人的差异**
- 用 Python 重写一个你熟悉的 JS 小工具，体会"同样的需求，不同的工程习惯"

**验收**：`python code/week01/day01_md5.py --dir . --json` 能输出文件哈希与重复文件报告。

---

## 上午 09:00–11:30 · 理论输入

### 1. 为什么 Python 是 AI 生态的第一公民

不是因为它更好，而是因为**生态惯性**：官方 SDK、论文复现代码、开源框架、教程示例几乎全部以 Python 为第一语言。
你要做的是"读得懂、改得动、封得住"，而不是"用 Python 重写一切"。

一个可直接迁移的认知：**Python 的包管理 ≈ npm，但更分散**。npm 只有一套（package.json + node_modules），
Python 有 pip / venv / conda / poetry / uv 多套并存——这就是为什么第一课先讲环境。

具体到岗位：RAG 的向量库与 embedding 客户端、Agent 编排（LangGraph）、评估（RAGAS）、服务化（FastAPI）在 Python 侧都是一等公民，M1/M2/M3 的交付物也全是 Python 服务。你不是要从头学一门语言，而是要把 AI 能力包成 Python 服务、再接回你最强的 React 界面。

### 2. 环境三件套

| 概念 | 作用 | 类比前端 |
| --- | --- | --- |
| 解释器版本 | 3.10 / 3.11 / 3.12 语法与性能不同 | Node 大版本 |
| 虚拟环境 | 每个项目独立的 site-packages | `node_modules` |
| 依赖锁定 | 记录精确版本，保证别人装出一样的环境 | `package-lock.json` |

`uv` 是目前最快的选择（Rust 实现），一条命令替代 venv + pip + pip-tools：

```powershell
uv venv --python 3.12          # 建 .venv
.\.venv\Scripts\Activate.ps1   # 激活
uv pip install -r requirements/base.txt
uv pip list                    # 看装了什么
```

三种"安装"要分清，面试也会问：

- `uv pip install`：装进当前虚拟环境（等价 pip install）
- `uv add`：项目模式，写入 `pyproject.toml` 并锁定
- `uv run xxx.py`：临时用项目环境执行，不污染全局

### 3. 语法对照表（照着敲一遍）

| JS / TS | Python | 备注 |
| --- | --- | --- |
| `const x = 1` | `x = 1` | 无声明关键字，变量即绑定 |
| `===` | `==` | Python 的 `==` 是值比较，`is` 是身份比较 |
| `{}` / `[]` | 缩进 / `[]` | 缩进是语法，不是风格 |
| `arr.map(f)` | `[f(x) for x in arr]` | 列表推导式更快更地道 |
| `obj.key` | `d["key"]` | dict 用下标；`obj.key` 用于对象/数据类 |
| `a ?? b` | `a if a is not None else b` | `or` 会把 `0`/`""` 也当成假 |
| `a?.b` | `a.get("b")` / `getattr(a, "b", None)` | 没有可选链 |
| `arr.slice(1,3)` | `arr[1:3]` | 切片会产生新列表 |
| `[...a, ...b]` | `[*a, *b]` | 解包运算符 |
| `{...a, k: v}` | `{**a, "k": v}` | 字典解包 |
| `Object.entries(o)` | `o.items()` | 遍历键值对 |
| `for (const [k,v] of ...)` | `for k, v in d.items():` | 元组解包 |
| `` `${a}` `` | `f"{a}"` | f-string |
| `try/catch` | `try/except` | 可多个 except |
| `throw new Error()` | `raise ValueError()` | 用内置异常类型 |
| `console.log` | `print` / `logging` | 生产代码用 logging |

这张表至少三行在 Agent 代码里天天出现：模型返回的 `tool_calls[0].function.arguments` 是 JSON 字符串，`json.loads` 之后就是 `d["name"]` / `d.get("arguments", "{}")`；`messages` 是 `list[dict]`，追加一轮对话就是 `messages.append({"role": "user", ...})`。敲完表顺手写个 `parse_tool_args(raw: str) -> dict`，这是第 5 周工具调用的第一块砖。

### 4. 五个会咬人的差异（今天就记住）

1. **可变默认参数**：`def f(items=[])` 的 `[]` 只创建一次，所有调用共享。
   ```python
   def f(items=None):
       items = items or []
   ```
2. **空容器的真假**：`[]`、`{}`、`""`、`0` 都是 `False`。写 `if data:` 前想清楚"空"和"没有"是不是一回事。
3. **`is` 不是 `===`**：`is` 比较内存地址。`a is None` 是惯用法，`a is 1` 是 bug（小整数缓存会让你偶尔"碰巧对"）。
4. **整数除法**：`/` 永远返回 float，整除用 `//`；`7 / 2 == 3.5`。
5. **模块名撞车**：本地文件 `random.py`、`json.py` 会遮蔽标准库，报一个莫名其妙的错。命名避开标准库。

这两个坑在 Agent 里是事故级的：工具函数写 `def search(q, filters={})`，同一进程里所有请求共享那个 dict，A 用户的过滤条件会漏进 B 用户的检索；检索后写 `if not docs:`，会把"确实没命中"和"检索抛错被吞"压成同一条降级路径，线上只能靠日志猜。

### 5. 心智差异：Python 更相信"约定"

JS 靠编译器与类型系统兜底，Python 靠**约定 + 鸭子类型**。所以工程纪律要自己补：
类型注解、小函数、显式异常、`__all__`、测试。这些在第 2 天会展开。

---

## 下午 14:00–16:30 · 实战

### 任务 1 · 建环境并跑通（20 min）

```powershell
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements/base.txt
python -c "import sys, pydantic; print(sys.version, pydantic.VERSION)"
```

### 任务 2 · 重写 MD5 工具（60 min）

JS 版本你大概写过：

```js
const hash = crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex')
```

Python 版本（完整实现见 [`code/week01/day01_md5.py`](../../code/week01/day01_md5.py)）：

```python
import hashlib
from pathlib import Path

def file_digest(path: Path, algo: str = "md5", chunk_size: int = 1 << 20) -> str:
    """分块读取，避免大文件爆内存——这是与前端 Buffer 全量读最大的习惯差异。"""
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
```

要点：
- `iter(callable, sentinel)` 是 Python 版的"读到 EOF 为止"，比 `while True` 干净
- 大文件必须分块，1MB 一块是经验值
- 用 `hashlib.new(algo)` 而不是写死 md5，顺手支持 sha256

### 任务 3 · 图片批处理（50 min）

用 Pillow 把目录里的图片批量生成缩略图，输出到 `output/thumbs/`：

```python
from PIL import Image

def make_thumb(src: Path, dst: Path, size=(320, 320)) -> tuple[int, int]:
    with Image.open(src) as im:
        im.thumbnail(size)          # 等比缩放，原地修改
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, quality=85)
        return im.size
```

注意 `im.thumbnail` 会**原地修改**（和 JS 里到处 immutable 的习惯相反），所以要 `with` 管理生命周期。

### 任务 4 · 给工具加 CLI（20 min）

```python
import argparse

p = argparse.ArgumentParser(description="计算文件哈希并找出重复文件")
p.add_argument("--dir", type=Path, default=Path("."))
p.add_argument("--algo", choices=["md5", "sha1", "sha256"], default="md5")
p.add_argument("--json", action="store_true", help="输出 JSON")
```

跑通验收：

```powershell
python code/week01/day01_md5.py --dir . --json
```

---

## 代码思考（写进 `logs/day-01.md`）

1. 为什么 `def f(items=[])` 是 bug，而 `def f(path=Path("."))` 相对安全？（提示：可变 vs 不可变）
2. 分块哈希时 `chunk_size` 取 1MB，如果取 1KB 或 1GB 分别会发生什么？用 `time` 实测三个值。
3. JS 的 `Object.keys(o)` 有稳定顺序，Python 3.7+ 的 dict 也有插入序——那 `set` 呢？为什么不能依赖 set 的顺序？
4. 你的 `file_digest` 如果遇到无权限文件会怎样？应该让异常冒泡还是捕获后跳过？两种选择各适合什么场景？
5. 把 `hashlib.new("md5")` 换成 `hashlib.md5()` 有什么差别？为什么后者在 FIPS 环境会失败？

## 复盘清单

- [ ] 能不看笔记说清 venv / pip / uv 的关系
- [ ] 五个"咬人差异"能各举一个例子
- [ ] 代码提交：`git commit -m "day01: 环境搭建 + 文件哈希工具"`
- [ ] `logs/day-01.md` 写了"今天最反直觉的一点"
