"""Day 02 · 类型注解 + Pydantic + CLI 子命令。

对应文档：docs/week-01/day-02.md

用法：
    python code/week01/day02_cli.py scan --dir . --top 5
    python code/week01/day02_cli.py rename --dir ./tmp --prefix demo --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tool")


class AppError(Exception):
    """业务错误基类：CLI 层统一翻译成退出码 1。"""


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
    generated_at: datetime


class RenamePlan(BaseModel):
    pairs: list[tuple[str, str]]
    applied: bool = False


def scan_dir(root: Path, top: int = 10) -> ScanReport:
    if not root.exists():
        raise AppError(f"目录不存在: {root}")

    files: list[FileInfo] = []
    by_ext: dict[str, int] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError as exc:
            log.warning("跳过 %s: %s", p, exc)
            continue
        ext = p.suffix.lower() or "<none>"
        by_ext[ext] = by_ext.get(ext, 0) + 1
        files.append(FileInfo(path=str(p), ext=ext, size=st.st_size, mtime=st.st_mtime))

    files.sort(key=lambda f: f.size, reverse=True)
    return ScanReport(
        root=str(root.resolve()),
        total_files=len(files),
        total_bytes=sum(f.size for f in files),
        by_ext=dict(sorted(by_ext.items(), key=lambda kv: kv[1], reverse=True)),
        largest=files[:top],
        generated_at=datetime.now(),
    )


def plan_rename(root: Path, prefix: str) -> RenamePlan:
    """生成重命名计划；重名时加序号，绝不覆盖已有文件。"""
    if not root.is_dir():
        raise AppError(f"不是目录: {root}")
    targets = sorted(p for p in root.iterdir() if p.is_file())
    pairs: list[tuple[str, str]] = []
    for i, p in enumerate(targets, 1):
        new_name = f"{prefix}_{i:03d}{p.suffix}"
        new_path = p.with_name(new_name)
        if new_path.exists() and new_path != p:
            raise AppError(f"目标已存在，拒绝覆盖: {new_path}")
        pairs.append((str(p), str(new_path)))
    return RenamePlan(pairs=pairs)


def render(report: ScanReport) -> str:
    lines = [
        f"根目录: {report.root}",
        f"文件数: {report.total_files}  总大小: {report.total_bytes / 1024:.1f} KB",
        "扩展名分布: " + ", ".join(f"{k}={v}" for k, v in list(report.by_ext.items())[:8]),
        "最大的文件:",
    ]
    lines += [f"  {f.size:>10} B  {f.path}" for f in report.largest]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="目录扫描与批量重命名示例")
    sub = p.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="扫描目录并输出统计")
    scan.add_argument("--dir", type=Path, default=Path("."))
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--top", type=int, default=10)

    rename = sub.add_parser("rename", help="批量重命名（默认 dry-run）")
    rename.add_argument("--dir", type=Path, required=True)
    rename.add_argument("--prefix", required=True)
    rename.add_argument("--apply", action="store_true", help="真正执行；不加只预览")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "scan":
            report = scan_dir(args.dir, args.top)
            print(report.model_dump_json(indent=2) if args.json else render(report))
            return 0

        if args.cmd == "rename":
            plan = plan_rename(args.dir, args.prefix)
            if not args.apply:
                for old, new in plan.pairs:
                    print(f"{old}  ->  {new}")
                log.info("dry-run 结束，共 %d 个文件；加 --apply 才会执行", len(plan.pairs))
                return 0
            for old, new in plan.pairs:
                Path(old).rename(new)
            log.info("已重命名 %d 个文件", len(plan.pairs))
            return 0
    except AppError as exc:
        log.error("%s", exc)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
