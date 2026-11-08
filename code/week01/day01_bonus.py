"""Day 01 · 用 Python 重写 MD5 工具：文件哈希 + 重复文件检测。

对应文档：docs/week-01/day-01.md

用法：
    python code/week01/day01_md5.py --dir . --algo md5
    python code/week01/day01_md5.py --dir . --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from file_walker import SKIP_DIRS, walk_files  # 复用公共遍历函数

def scan(root: Path, sort: str = "desc", include_hidden: bool = False, min_size: int = 0) -> dict:
    """统计当前目录下每个扩展名的总大小

    返回的 report["extensions"] 是按总大小排序后的列表，每项：
        {"ext": ".py", "files": 文件数, "bytes": 总字节数}

    - include_hidden: 是否进入隐藏目录（以 . 开头）
    - min_size: 只统计大于等于该字节数的文件
    """
    # 键为扩展名（小写，无扩展名归为 ""），值累积该扩展名的文件数与总字节
    stats: dict[str, dict] = defaultdict(lambda: {"files": 0, "bytes": 0})
    total_files = 0
    total_bytes = 0
    skipped: list[dict] = []

    # 复用公共遍历函数（自动剪枝 SKIP_DIRS，可选包含隐藏目录）
    for p in walk_files(root, include_hidden=include_hidden):
        try:
            size = p.stat().st_size
        except OSError as exc:  # 无权限/被占用等，记录后跳过
            skipped.append({"path": str(p), "reason": str(exc)})
            continue
        if size < min_size:  # --min-size 过滤
            continue
        ext = p.suffix.lower()  # 取扩展名，如 ".PY" → ".py"；无扩展名则为 ""
        stats[ext]["files"] += 1
        stats[ext]["bytes"] += size
        total_files += 1
        total_bytes += size

    # 按总大小排序，sort="desc" 降序（默认），"asc" 升序
    extensions = [
        {"ext": ext, **info} for ext, info in stats.items()
    ]
    extensions.sort(key=lambda e: e["bytes"], reverse=(sort == "desc"))

    return {
        "root": str(root),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "extensions": extensions,
        "skipped": skipped,
    }

    
def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n} B"


def render(report: dict) -> str:
    """渲染统计结果，格式：.md   124.3 KB   (12 files)"""
    lines = [
        f"根目录: {report['root']}",
        f"文件数: {report['total_files']}    总大小: {human(report['total_bytes'])}",
        "",
    ]
    for e in report["extensions"]:
        ext = e["ext"] or "(无扩展名)"
        lines.append(f"{ext:<12} {human(e['bytes']):>10}   ({e['files']} files)")
    if report["skipped"]:
        lines.append(f"\n跳过 {len(report['skipped'])} 个文件（无权限/读取失败）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统计当前目录下每个扩展名的总大小")
    parser.add_argument("--dir", type=Path, default=Path("."), help="要扫描的目录")
    # 升序还是降序
    parser.add_argument("--sort", choices=["asc", "desc"], default="desc", help="排序方式")
    parser.add_argument("--num", type=int, default=5, help="按总大小输出前 N 名扩展名")
    parser.add_argument("--min-size", type=int, default=0, help="只统计大于等于该字节数的文件")
    parser.add_argument("--include-hidden", action="store_true", help="包含隐藏目录（以 . 开头）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    if not args.dir.exists():
        print(f"目录不存在: {args.dir}", file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    report = scan(args.dir, args.sort, include_hidden=args.include_hidden, min_size=args.min_size)
    report["extensions"] = report["extensions"][: args.num]  # 只保留前 N 名
    report["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
        print(f"\n耗时 {report['elapsed_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
