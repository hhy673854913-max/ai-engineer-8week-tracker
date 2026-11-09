"""Day 02 · 故意写错的类型样例：给 mypy 抓虫用。

mypy **不会执行**这个文件，它只读注解和赋值关系；
而 `python day02_mypy_demo.py` 能跑通——这就是"注解不执行，但检查器会执行"。

运行：
    python -m mypy code/week01/day02_mypy_demo.py --ignore-missing-imports
"""

from __future__ import annotations

from typing import reveal_type

from pydantic import BaseModel


class ScanReport(BaseModel):
    root: str
    total_files: int
    total_bytes: int
    by_ext: dict[str, int]


def make_report(root: str) -> ScanReport:
    return ScanReport(root=root, total_files=0, total_bytes=0, by_ext={})


def bump(report: ScanReport, n: int) -> ScanReport:
    report.total_files = "abc"  # E1: str 赋给 int 字段（Pydantic 不校验赋值，mypy 会）
    report.by_ext[1] = "x"  # E2: key 该是 str、value 该是 int，一行错两处
    return report


def top_k(scores: list[float], k: int = 5) -> list[tuple[int, float]]:
    pairs = sorted(enumerate(scores), key=lambda kv: -kv[1])
    return pairs[:k]


def main() -> int:
    report = make_report(".")
    bump(report, 3)

    bad: int = "3"  # E3: 字符串赋给 int 变量
    top_k("not a list")  # E4: 参数类型不匹配
    top_k([0.9, 0.2], k="3")  # E5: k 要 int，给了 str

    reveal_type(top_k([0.9, 0.2]))  # 让 mypy 把推断出的类型打印出来
    print(bad, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
