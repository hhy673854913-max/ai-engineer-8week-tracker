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

ALGOS = ("md5", "sha1", "sha256")


def file_digest(path: Path, algo: str = "md5", chunk_size: int = 1 << 20) -> str:
    """分块读取并计算哈希，避免大文件一次性读入内存。"""
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(root: Path, algo: str = "md5") -> dict:
    """遍历目录，返回文件清单与重复组。"""
    files: list[dict] = []
    by_size: dict[int, list[Path]] = defaultdict(list)
    skipped: list[dict] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError as exc:
            skipped.append({"path": str(p), "reason": str(exc)})
            continue
        files.append({"path": str(p), "size": st.st_size, "mtime": st.st_mtime})
        by_size[st.st_size].append(p)

    # 第一层去重：大小相同才可能重复，避免对大文件全量算哈希
    digests: dict[tuple[int, str], list[str]] = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2 or size == 0:
            continue
        for p in paths:
            try:
                digests[(size, file_digest(p, algo))].append(str(p))
            except OSError as exc:
                skipped.append({"path": str(p), "reason": str(exc)})

    duplicates = [
        {"algo": algo, "size": size, "digest": digest, "paths": paths}
        for (size, digest), paths in digests.items()
        if len(paths) > 1
    ]
    duplicates.sort(key=lambda d: d["size"] * (len(d["paths"]) - 1), reverse=True)

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
    args = parser.parse_args(argv)

    if not args.dir.exists():
        print(f"目录不存在: {args.dir}", file=sys.stderr)
        return 2

    t0 = time.perf_counter()
    report = scan(args.dir, args.algo)
    report["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
        print(f"\n耗时 {report['elapsed_ms']} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
