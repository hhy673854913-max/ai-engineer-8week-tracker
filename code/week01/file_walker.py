"""Day 01 · 公共文件遍历工具：剪枝 + 可选跳过隐藏目录。

被 day01_md5.py 和 day01_bonus.py 复用。
"""

from __future__ import annotations

import os
from pathlib import Path

# 默认跳过的目录：版本控制、虚拟环境、缓存、输出目录等
SKIP_DIRS = {
    ".git", ".venv", "__pycache__", ".pytest_cache",
    ".ruff_cache", "output", "runs", ".mini_rag_index",
}


def walk_files(
    root: Path,
    skip: set[str] | None = SKIP_DIRS,
    include_hidden: bool = False,
) -> "os.PathLike[str]":
    """遍历目录，惰性产出文件路径（生成器）。

    - skip: 要剪枝的目录名集合；None 表示不剪枝
    - include_hidden: 是否进入以 . 开头的隐藏目录（默认跳过）
    """
    # os.walk 自顶向下遍历，修改 dirnames 可阻止进入某些子目录（剪枝）
    for dirpath, dirnames, filenames in os.walk(root):
        # 剪枝：过滤掉要跳过的目录
        if skip is not None:
            dirnames[:] = [d for d in dirnames if d not in skip]
        # 可选：跳过隐藏目录（以 . 开头）
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            yield Path(dirpath) / name
