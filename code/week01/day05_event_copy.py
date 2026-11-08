"""Day 05 · 结构化输出：运营活动文案生成器。

演示"生成 → 解析 → 校验 → 带错误重试"的完整闭环。

用法：
    python code/week01/day05_event_copy.py --theme "春节签到" --audience "回流玩家"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field, ValidationError, field_validator  # noqa: E402

from code.shared.llm_client import get_client  # noqa: E402
from code.shared.structured import generate_with_repair  # noqa: E402

PROMPT = """你是资深游戏运营文案。为下面的活动生成 3 套文案方案。

只输出 JSON，不要 markdown 代码块，不要任何解释。
JSON 结构：
{{
  "variants": [
    {{
      "theme": "活动主题，2-12 字",
      "slogan": "一句话主标语，4-20 字",
      "bullets": ["3-4 条卖点，每条不超过 15 字"],
      "channels": ["从 站内Banner/推送/社群/短视频 中选"],
      "risk": "low | mid | high"
    }}
  ]
}}

活动信息：
- 主题：{theme}
- 目标人群：{audience}
- 玩法：{mechanic}
- 合规限制：{constraints}
"""


class CopyVariant(BaseModel):
    theme: str = Field(min_length=2, max_length=12)
    slogan: str = Field(min_length=4, max_length=20)
    bullets: list[str] = Field(min_length=3, max_length=4)
    channels: list[Literal["站内Banner", "推送", "社群", "短视频"]]
    risk: Literal["low", "mid", "high"] = "low"

    @field_validator("slogan")
    @classmethod
    def no_double_exclamation(cls, v: str) -> str:
        if "!!" in v:
            raise ValueError("标语不允许连续感叹号")
        return v


class CopySet(BaseModel):
    variants: list[CopyVariant] = Field(min_length=1, max_length=5)


def build_prompt(theme: str, audience: str, mechanic: str, constraints: str) -> str:
    return PROMPT.format(theme=theme, audience=audience, mechanic=mechanic, constraints=constraints)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运营活动文案生成器（结构化输出）")
    parser.add_argument("--theme", default="春节签到")
    parser.add_argument("--audience", default="回流玩家")
    parser.add_argument("--mechanic", default="连续签到 7 天领限定皮肤")
    parser.add_argument("--constraints", default="不得出现「最强」「第一」等绝对化用语")
    args = parser.parse_args(argv)

    client = get_client()
    prompt = build_prompt(args.theme, args.audience, args.mechanic, args.constraints)

    try:
        result = generate_with_repair(
            client.chat,
            prompt,
            CopySet,
            max_repair=2,
            temperature=0.8,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
    except (ValidationError, Exception) as exc:  # noqa: BLE001
        print(f"生成失败，已降级：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print(f"\n累计用量：{client.report()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
