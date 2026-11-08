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

ALGOS = ("md5", "sha1", "sha256")


def file_digest(path: Path, algo: str = "md5", chunk_size: int = 1 << 20) -> str:
    """分块读取并计算哈希，避免大文件一次性读入内存。

    chunk_size 默认 1MB（1 << 20），任何时候内存中只有一块数据，
    因此 GB 级文件也能安全处理。
    """
    h = hashlib.new(algo)
    with path.open("rb") as f:  # 以二进制只读模式打开；with 保证文件最终关闭
        # iter(调用函数, 哨兵值)：反复调用 lambda，直到返回值等于 b""（文件读完）才停止。
        # 必须用 lambda 包一层，让 f.read 在“每次迭代时”执行；
        # 若直接写 f.read(chunk_size)，会在传参那一刻立刻执行，只读一次。
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)  # 增量更新哈希，逐块累积
    return h.hexdigest()


def scan(root: Path, algo: str = "md5", include_hidden: bool = False) -> dict:
    """遍历目录，返回文件清单与重复组。"""
    # 初始化三个容器：分别存放所有文件清单、按大小分组的索引、读取失败的记录
    files: list[dict] = []                          # 所有文件的元信息列表
    by_size: dict[int, list[Path]] = defaultdict(list)  # 大小 → 该大小的文件路径列表
    skipped: list[dict] = []                        # 无法访问的文件及原因

    # 第一阶段：递归遍历目录（公共函数，自动剪枝），收集文件元数据
    for p in walk_files(root, include_hidden=include_hidden):
        try:
            st = p.stat()                           # 获取文件状态（大小、修改时间等）
        except OSError as exc:                      # 权限不足/文件被占用等系统错误
            skipped.append({"path": str(p), "reason": str(exc)})
            continue
        files.append({"path": str(p), "size": st.st_size, "mtime": st.st_mtime})
        by_size[st.st_size].append(p)               # 按大小分组，为后续快速筛选做准备

    # 第二层去重：仅对大小相同（≥2个）的文件计算哈希，避免全量哈希计算
    digests: dict[tuple[int, str], list[str]] = defaultdict(list)  # (大小, 哈希) → 路径列表
    for size, paths in by_size.items():             # 遍历每个大小分组
        if len(paths) < 2 or size == 0:             # 单文件组不可能重复；空文件内容相同无意义
            continue
        for p in paths:
            try:
                digest = file_digest(p, algo)       # 分块计算文件哈希
                digests[(size, digest)].append(str(p))  # 相同(大小,哈希) → 确认为重复
            except OSError as exc:                  # 读取失败（权限/占用等）
                skipped.append({"path": str(p), "reason": str(exc)})

    # 筛选出真正的重复组（同大小同哈希且路径数≥2），按可节省空间降序排列
    duplicates = [
        {"algo": algo, "size": size, "digest": digest, "paths": paths}
        for (size, digest), paths in digests.items()
        if len(paths) > 1
    ]
    # 排序键：文件大小 × (份数-1) = 删除冗余后可回收的空间，从大到小展示
    duplicates.sort(key=lambda d: d["size"] * (len(d["paths"]) - 1), reverse=True)

    # 统计总浪费空间（每组只保留一份，其余视为浪费）
    wasted = sum(d["size"] * (len(d["paths"]) - 1) for d in duplicates)
    return {
        "root": str(root),
        "algo": algo,
        "total_files": len(files),
        "total_bytes": sum(f["size"] for f in files),
        "duplicate_groups": len(duplicates),
        "wasted_bytes": wasted,
        "duplicates": duplicates,
        "skipped": skipped,
    }

def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n} B"


def render(report: dict) -> str:
    lines = [
        f"根目录: {report['root']}",
        f"算法:   {report['algo']}",
        f"文件数: {report['total_files']}    总大小: {human(report['total_bytes'])}",
        f"重复组: {report['duplicate_groups']}    可回收: {human(report['wasted_bytes'])}",
    ]
    for i, d in enumerate(report["duplicates"], 1):
        lines.append(f"\n[{i}] {human(d['size'])} × {len(d['paths'])}  {d['digest'][:12]}…")
        lines.extend(f"    {p}" for p in d["paths"])
    if report["skipped"]:
        lines.append(f"\n跳过 {len(report['skipped'])} 个文件（无权限/读取失败）")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="计算文件哈希并找出重复文件")
    parser.add_argument("--dir", type=Path, default=Path("."), help="要扫描的目录")
    parser.add_argument("--algo", choices=ALGOS, default="md5")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--min-size", type=int, default=0, help="只报告大于等于该字节数的重复组")
    parser.add_argument("--include-hidden", action="store_true", help="包含隐藏目录（以 . 开头）")
    args = parser.parse_args(argv)

    if not args.dir.exists():
        print(f"目录不存在: {args.dir}", file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    report = scan(args.dir, args.algo, include_hidden=args.include_hidden)
    report["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)

    # 过滤重复组，只保留大于等于 min_size 的
    report["duplicates"] = [d for d in report["duplicates"] if d["size"] >= args.min_size]
    report["wasted_bytes"] = sum(d["size"] * (len(d["paths"]) - 1) for d in report["duplicates"])


    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
        print(f"\n耗时 {report['elapsed_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
