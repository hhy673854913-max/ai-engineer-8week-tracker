"""模板渲染器：把 prompt 当代码管理。

为什么不用 str.format 裸调：
1. 模板里带 JSON 示例（花括号）会炸——本模块的 render 已处理转义；
2. 缺变量时 KeyError 信息不友好——这里一次性列出所有缺失变量；
3. 模板误写了未声明的变量能立刻发现，而不是上线后才发现输出少了一块。

用法：
    from code.week02.prompts.render import render
    prompt = render(TEMPLATES["extract_v2"], text="……")
"""

from __future__ import annotations

import re
from string import Template

_VAR = re.compile(r"\$([A-Za-z_]\w*)")


def render(template: str, **kwargs: str) -> str:
    """$var 风格渲染：缺变量报错，多余变量容忍（方便模板裁剪）。"""
    missing = sorted(set(_VAR.findall(template)) - set(kwargs))
    if missing:
        raise ValueError(f"缺少模板变量: {missing}")
    return Template(template).substitute(**kwargs)


def check(template: str, **kwargs: str) -> list[str]:
    """只做变量白名单校验，返回缺失变量列表（不抛错），供测试用。"""
    return sorted(set(_VAR.findall(template)) - set(kwargs))
