"""Day 05 · 结构化输出：运营活动文案生成器。

演示"生成 → 解析 → 校验 → 带错误重试"的完整闭环。

用法：
    python code/week01/day05_event_copy.py --theme "春节签到" --audience "回流玩家"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field, ValidationError, field_validator  # noqa: E402

from code.shared.llm_client import get_client  # noqa: E402
from code.shared.structured import StructuredOutputError, generate_with_repair  # noqa: E402

# 批量模式默认使用的 10 个主题
DEFAULT_THEMES = [
    "春节签到", "周年庆典", "暑期冲榜", "新手礼包",
    "七夕限定", "中秋赏月", "国庆狂欢", "双11大促",
    "圣诞雪花", "元旦迎新",
]

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
            # raise ValueError("标语不允许连续感叹号")
            # 静默修复，不抛错
            return v.replace("!!", "!")
        return v


# 需要的格式：JSON 对象
class CopySet(BaseModel):
    variants: list[CopyVariant] = Field(min_length=1, max_length=5)


# ── 降级策略配置（三个问题的代码回答） ──

# 问题 1：重试 2 次仍失败，返回什么？
#   当前选择：返回 None（由调用方决定后续动作：跳过 / 人工 / 终止）
#   理由：空 CopySet(variants=[]) 会被 Pydantic 拒收（min_length=1），
#         硬塞默认值又可能脱离业务上下文造成误导，None 是最诚实的表达
FALLBACK_NONE = None

# 问题 2：部分字段合法、部分不合法，是整条丢弃还是保留可用字段？
#   当前选择：整条丢弃（Pydantic 校验是全有或全无，任一字段失败则整个对象拒收）
#   替代方案：partial_validate 逐字段校验，合法字段保留
#             → 需要额外实现，适用场景：字段间无强耦合，调用方可处理不完整数据
PARTIAL_KEEP = False  # True = 保留合法字段；False = 整条丢弃

# 问题 3：线上要不要把失败样本落盘？落盘要不要脱敏？
#   当前选择：本地批量模式，成功样本写 --out 指定的 JSONL
#             失败样本写 stderr + 可选落盘到 logs/day05_failures/（仅错误元数据）
#   生产建议：失败样本落盘到日志系统 + 告警，但必须脱敏：
#             - 移除 API key、用户隐私字段
#             - 保留 error 类型、prompt 前 200 字、模型输出前 500 字（足够调试）
#             - 设置保留期，定期清理，避免 PII 泄露
LOG_FAILURES = True
LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "day05_failures"


def build_prompt(theme: str, audience: str, mechanic: str, constraints: str) -> str:
    return PROMPT.format(theme=theme, audience=audience, mechanic=mechanic, constraints=constraints)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运营活动文案生成器（结构化输出）")
    parser.add_argument("--theme", default="春节签到")
    parser.add_argument("--audience", default="回流玩家")
    parser.add_argument("--mechanic", default="连续签到 7 天领限定皮肤")
    parser.add_argument("--constraints", default="不得出现「最强」「第一」等绝对化用语")
    parser.add_argument("--batch", action="store_true", help="批量模式：跑 N 个主题并输出统计")
    parser.add_argument("--n", type=int, default=10, help="批量模式的主题数量（默认 10）")
    parser.add_argument("--out", type=str, default="", help="批量结果 JSONL 输出路径（可选）")
    parser.add_argument("--verbose", "-v", action="store_true", help="打印每次 LLM 返回的原始内容")
    args = parser.parse_args(argv)

    client = get_client()

    if args.batch:
        return run_batch(args, client)

    prompt = build_prompt(args.theme, args.audience, args.mechanic, args.constraints)

    try:
        result, _ = generate_with_repair(
            client.chat,
            prompt,
            CopySet,
            max_repair=2,
            temperature=0.8,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
    except (ValidationError, Exception) as exc:  # noqa: BLE001
        # 问题 1 的落地：单次模式失败时打印错误 + 返回 None（调用方自行处理）
        print(f"生成失败，已降级：{type(exc).__name__}: {exc}", file=sys.stderr)
        print("null")   # JSON 中的 None
        return 1

    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    print(f"\n累计用量：{client.report()}")
    return 0


def run_batch(args: argparse.Namespace, client) -> int:
    """批量跑 N 个主题，记录四项指标。"""
    themes = DEFAULT_THEMES[: args.n]

    stats = {
        "total": 0,
        "first_try_ok": 0,   # 一次通过（0 次修复）
        "repaired_ok": 0,    # 修复后通过（≥1 次修复）
        "failed": 0,         # 修复上限后仍失败
        "total_calls": 0,    # 累计 LLM 调用次数（含修复重试）
        "total_ms": 0,       # 累计耗时
        "total_cost": 0.0,   # 累计成本
    }

    # 记录每个主题的初始 token 基数，用于计算单主题消耗
    out_path = Path(args.out) if args.out else None
    out_fh = open(out_path, "w", encoding="utf-8") if out_path else None

    # 用 ANSI 转义实现进度行原地刷新，不在终端留下滚动痕迹
    # \r 回到行首，\033[K 清除到行尾
    # 完成后 \n 换行，让汇总从新一行开始
    print(f"批量模式：{len(themes)} 个主题", flush=True)

    for i, theme in enumerate(themes, 1):
        prompt = build_prompt(theme, args.audience, args.mechanic, args.constraints)

        # 记录该主题开始前的累计 token 基数，用于计算单主题消耗
        usage_before = client.total.prompt_tokens + client.total.completion_tokens

        # 进度行（会被后续状态覆盖）
        sys.stdout.write(f"\r  [{i:2d}/{len(themes)}] {theme}  生成中…\033[K")
        sys.stdout.flush()

        t0 = time.perf_counter()
        try:
            result, calls_used = generate_with_repair(
                client.chat,
                prompt,
                CopySet,
                max_repair=2,
                temperature=0.8,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            repaired = calls_used > 1

            stats["total"] += 1
            if repaired:
                stats["repaired_ok"] += 1
            else:
                stats["first_try_ok"] += 1
            stats["total_calls"] += calls_used
            stats["total_ms"] += elapsed_ms

            # 单主题 token 消耗
            usage_now = client.total.prompt_tokens + client.total.completion_tokens
            stats["total_cost"] += _estimate_cost(usage_before, usage_now, client)

            status = "修复" if repaired else "一次通过"
            sys.stdout.write(f"\r  [{i:2d}/{len(themes)}] {theme}  ✓ {status}  {elapsed_ms}ms\033[K\n")

            # verbose 模式：打印 LLM 原始返回内容
            if args.verbose:
                for v in result.variants:
                    print(f"    {v.theme}: {v.slogan}")

            if out_fh:
                for v in result.variants:
                    out_fh.write(json.dumps(
                        {"theme": theme, **v.model_dump()}, ensure_ascii=False
                    ) + "\n")

        except (StructuredOutputError, ValidationError, Exception) as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            stats["total"] += 1
            stats["failed"] += 1
            stats["total_ms"] += elapsed_ms
            sys.stdout.write(f"\r  [{i:2d}/{len(themes)}] {theme}  ✗ 失败: {type(exc).__name__}\033[K\n")
            sys.stdout.flush()

            # 问题 1 的落地：失败时返回 None，由调用方（上层服务）决定后续动作
            # 当前批量模式选择：记录失败、继续下一个主题，不中断流程

            # 问题 3 的落地：失败样本落盘（仅元数据，不含敏感内容）
            if LOG_FAILURES:
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                fail_log = {
                    "theme": theme,
                    "error_type": type(exc).__name__,
                    "error_msg": str(exc)[:200],      # 截断，避免过长
                    "elapsed_ms": elapsed_ms,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                fail_path = LOG_DIR / f"{theme}_{int(time.time())}.json"
                fail_path.write_text(
                    json.dumps(fail_log, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    if out_fh:
        out_fh.close()

    # ── 汇总 ──
    total = stats["total"]
    ok = stats["first_try_ok"] + stats["repaired_ok"]
    print(f"\n{'═' * 50}")
    print(f"总主题数:     {total}")
    print(f"成功:         {ok}  (失败: {stats['failed']})")
    print(f"一次通过率:   {stats['first_try_ok']}/{total} = {_pct(stats['first_try_ok'], total)}")
    print(f"修复后通过率: {stats['repaired_ok']}/{total} = {_pct(stats['repaired_ok'], total)}")
    print(f"最终成功率:   {ok}/{total} = {_pct(ok, total)}")
    print(f"平均重试次数: {stats['total_calls'] / total:.2f} 次/主题")
    print(f"平均耗时:     {stats['total_ms'] / total:.0f} ms/主题")
    print(f"平均成本:     ¥{stats['total_cost'] / total:.6f}/主题")
    print(f"\n累计用量: {client.report()}")

    return 0 if stats["failed"] == 0 else 1


def _pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "N/A"


def _estimate_cost(tokens_before: int, tokens_now: int, client) -> float:
    """按当前 provider 单价估算增量成本。"""
    delta_in = client.total.prompt_tokens  # 已累加，直接用 report 中的单价
    cost_per_token = (
        client.config.price_in * 0.6 + client.config.price_out * 0.4
    ) / 1_000_000
    return (tokens_now - tokens_before) * cost_per_token


if __name__ == "__main__":
    raise SystemExit(main())
