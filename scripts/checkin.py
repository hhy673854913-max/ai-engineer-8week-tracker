"""每日打卡：生成 logs/day-XX.md，并查看整体进度。

用法：
    python scripts/checkin.py 12          # 生成第 12 天的日志
    python scripts/checkin.py 12 --force  # 覆盖已存在的日志
    python scripts/checkin.py --status    # 查看进度
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DOCS = ROOT / "docs"
START = date(2026, 11, 9)  # 与 scripts/gen_schedule.py 保持一致

# 从 docs/schedule.md 解析 40 天的标题与文档路径
ROW = re.compile(r"^\|\s*(\d{2})\s*\|\s*[\d-]+\s*\|\s*[^|]+\|\s*([^|]+?)\s*\|[^|]*\|\s*\[打开\]\(([^)]+)\)\s*\|$", re.M)


def load_schedule() -> dict[int, tuple[str, str]]:
    path = DOCS / "schedule.md"
    if not path.exists():
        print("找不到 docs/schedule.md，请先运行 scripts/gen_schedule.py", file=sys.stderr)
        raise SystemExit(1)
    text = path.read_text(encoding="utf-8")
    rows: dict[int, tuple[str, str]] = {}
    for day, title, doc in ROW.findall(text):
        rows[int(day)] = (title.strip(), doc.strip())
    if not rows:
        print("schedule.md 解析失败，请检查表格格式", file=sys.stderr)
        raise SystemExit(1)
    return rows


def day_date(n: int) -> date:
    week, weekday = divmod(n - 1, 5)
    return START + timedelta(weeks=week, days=weekday)


def create(n: int, force: bool) -> int:
    schedule = load_schedule()
    if n not in schedule:
        print(f"Day 必须在 1-40 之间，收到 {n}", file=sys.stderr)
        return 2
    title, doc = schedule[n]
    target = LOGS / f"day-{n:02d}.md"
    if target.exists() and not force:
        print(f"{target.relative_to(ROOT)} 已存在（加 --force 覆盖）")
        return 0

    template = (LOGS / "TEMPLATE.md").read_text(encoding="utf-8")
    content = template.format(
        day=f"{n:02d}",
        title=title,
        date=f"{day_date(n):%Y-%m-%d}",
        doc=f"../../docs/{doc}",
    )
    target.write_text(content, encoding="utf-8")
    print(f"已生成 {target.relative_to(ROOT)}（{day_date(n):%Y-%m-%d} · {title}）")
    return 0


def status() -> int:
    schedule = load_schedule()
    done = [n for n in schedule if (LOGS / f"day-{n:02d}.md").exists()]
    print(f"进度：{len(done)}/40（{len(done) / 40:.0%}）\n")
    for n in range(1, 41):
        mark = "✅" if n in done else "⬜"
        title, _ = schedule[n]
        print(f"{mark} Day {n:02d}  {day_date(n):%m-%d}  {title}")
    print()
    if done:
        print(f"已完成 {len(done)} 天，继续保持。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="学习打卡")
    parser.add_argument("day", nargs="?", type=int, help="第几天（1-40）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的日志")
    parser.add_argument("--status", action="store_true", help="查看进度")
    args = parser.parse_args()

    if args.status or args.day is None:
        return status()
    return create(args.day, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
