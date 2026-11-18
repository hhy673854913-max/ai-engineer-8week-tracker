"""Day 09 · 多模态：图片 → 可检索结构化描述。

对应 docs/week-02/day-09.md 四个任务：
- 任务 1/2：describe() 最小视觉调用 + ImageDesc schema
- 任务 3：batch() 异步批量（信号量限并发），核算成本
- 任务 4：check_compliance() 素材合规初筛

验收：对一批图片输出结构化 JSON 落盘 output/images.jsonl。

用法（仓库根目录）：
    python code/week02/day09_vision.py --images data/images          # 批量描述 → images.jsonl
    python code/week02/day09_vision.py --images data/images --limit 3
    python code/week02/day09_vision.py --compliance data/images/bad.jpg  # 合规初筛

注意：视觉能力取决于供应商与模型，脚本不假设当前 provider 支持图像；
调用失败会给出明确报错。PIL 为可选依赖，缺失时给出安装提示。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.structured import generate_with_repair, model_from_text  # noqa: E402

OUTPUT_DIR = ROOT / "output"

DESCRIBE_PROMPT = """描述这张图片，输出 JSON：
{
  "scene": "一句话场景描述",
  "main_objects": ["主体物体，1-8 个"],
  "people": "人物描述，没有则 null",
  "text_in_image": "图中文字，逐字转录；不确定的单词写 unclear；没有则 null",
  "style": "色调/画风，如 暖色调/卡通",
  "search_tags": ["检索标签，3-10 个"],
  "confidence": 0.0
}
只输出 JSON，不要 markdown 代码块，不要解释。"""

_vl_client = None


def get_vl_client():
    """独立的视觉模型 client，不污染全局单例的 model 字段。"""
    global _vl_client
    if _vl_client is None:
        from dataclasses import replace

        from code.shared.llm_client import LLMClient, load_config
        cfg = load_config()  # 这一步会加载 .env
        # qwen-plus 是纯文本模型，看不到图；视觉必须走 VL 系列（如 qwen3-vl-plus）。
        vl_model = os.getenv("DASHSCOPE_VL_MODEL") or cfg.model
        cfg = replace(cfg, model=vl_model)
        _vl_client = LLMClient(cfg)
    return _vl_client

COMPLIANCE_PROMPT = """你是素材合规审核员。检查这张图片是否可用于广告投放：
1. 是否含敏感元素（暴力、政治、暴露等）；
2. 是否有夸大宣传用语（"最强""第一""100%有效"等）；
3. 是否含二维码、联系方式、水印。
输出 JSON：
{
  "pass": true,
  "issues": ["问题列表，没有则为空数组"],
  "suggestion": "修改建议，通过则为空字符串"
}
只输出 JSON，不要解释。"""


# ---------------------------------------------------------------------------
# 输出契约
# ---------------------------------------------------------------------------


class ImageDesc(BaseModel):
    scene: str = Field(description="一句话场景描述")
    main_objects: list[str] = Field(min_length=1, max_length=8)
    people: str | None = None
    text_in_image: str | None = Field(default=None, description="图中文字，逐字转录；无则 null")
    style: str
    search_tags: list[str] = Field(min_length=3, max_length=10)
    confidence: float = Field(ge=0, le=1)


class ComplianceResult(BaseModel):
    passed: bool = Field(alias="pass", description="是否通过合规初筛")
    issues: list[str] = Field(default_factory=list)
    suggestion: str = ""


# ---------------------------------------------------------------------------
# 图片编码：先压缩再上传（4K 原图可能上千 token，1024 是"够看清又不烧钱"的经验值）
# ---------------------------------------------------------------------------


def to_data_url(path: Path, max_side: int = 1024, quality: int = 80) -> str:
    """本地图片 → JPEG base64 data URL。要读小字就调大 max_side 并配合 detail='high'。"""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("需要先安装 Pillow：uv pip install pillow") from exc
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def build_content(prompt: str, path: Path, *, detail: str = "high", max_side: int = 1024) -> list[dict]:
    """messages 的 content 可以是数组——这是视觉调用与文本调用的唯一结构差异。"""
    return [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": to_data_url(path, max_side), "detail": detail}},
    ]


# ---------------------------------------------------------------------------
# 任务 1/2：单图描述（同步版便于调试，异步版供批量）
# ---------------------------------------------------------------------------


def describe(path: Path, *, detail: str = "high", max_side: int = 1024) -> ImageDesc:
    client = get_vl_client()
    content = build_content(DESCRIBE_PROMPT, path, detail=detail, max_side=max_side)

    def chat_fn(messages, **_kw):
        full = list(messages)
        # generate_with_repair 首轮只传文本 prompt；修复轮会带上 assistant/user 历史，
        # 图片始终追加在最新的 user 消息里，保证每轮都"看得见图"。
        if not full:
            full = [{"role": "user", "content": content}]
        else:
            full.append({"role": "user", "content": content})
        return client.chat(full, temperature=0.2, max_tokens=600)

    desc, _ = generate_with_repair(chat_fn, DESCRIBE_PROMPT, ImageDesc, max_repair=2)
    return desc


async def describe_async(path: Path, *, detail: str = "high", max_side: int = 1024) -> ImageDesc:
    # generate_with_repair 是同步修复循环；图片已经编码成 data URL，
    # 重发时不需要重新读盘/压缩，直接复用 describe 即可。
    return describe(path, detail=detail, max_side=max_side)


# ---------------------------------------------------------------------------
# 多图对比实验：验证图片顺序对结论的影响（position bias）
# ---------------------------------------------------------------------------

COMPARE_PROMPT = """对比这两张图片，判断哪张更适合作为"高端花艺品牌"的主视觉。
从以下维度评分（1-10）：
1. 色彩和谐度
2. 构图美感
3. 品牌调性契合度
输出 JSON：
{
  "winner": "第一张" 或 "第二张",
  "first_scores": {"色彩": 0, "构图": 0, "调性": 0},
  "second_scores": {"色彩": 0, "构图": 0, "调性": 0},
  "reason": "一句话理由"
}
只输出 JSON，不要解释。"""


class CompareResult(BaseModel):
    winner: str = Field(description="哪张赢：第一张 或 第二张")
    first_scores: dict[str, int]
    second_scores: dict[str, int]
    reason: str


def compare_two(img_a: Path, img_b: Path, *, max_side: int = 1024) -> CompareResult:
    """同时发两张图给模型对比。img_a 在前，img_b 在后。

    返回的 winner 是"第一张"或"第二张"，对应传入顺序。
    要验证 position bias，就调两次：compare(A,B) 和 compare(B,A)，看结论是否一致。
    """
    client = get_vl_client()
    content = [
        {"type": "text", "text": COMPARE_PROMPT},
        {"type": "image_url", "image_url": {"url": to_data_url(img_a, max_side), "detail": "high"}},
        {"type": "image_url", "image_url": {"url": to_data_url(img_b, max_side), "detail": "high"}},
    ]
    resp = client.chat([{"role": "user", "content": content}], temperature=0.0, max_tokens=500)
    return model_from_text(resp.content, CompareResult)


# ---------------------------------------------------------------------------
# 任务 4：合规初筛
# ---------------------------------------------------------------------------


def check_compliance(path: Path, *, max_side: int = 1024) -> ComplianceResult:
    client = get_vl_client()
    content = build_content(COMPLIANCE_PROMPT, path, detail="high", max_side=max_side)
    resp = client.chat([{"role": "user", "content": content}], temperature=0.0, max_tokens=400)
    return model_from_text(resp.content, ComplianceResult)


# ---------------------------------------------------------------------------
# 任务 3：批量处理（信号量限并发防 429）
# ---------------------------------------------------------------------------


async def batch(paths: list[Path], concurrency: int = 3) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)

    async def one(p: Path) -> dict:
        async with sem:
            try:
                desc = await describe_async(p)
                return {"path": str(p), "ok": True, "desc": desc.model_dump(), "error": ""}
            except Exception as exc:  # noqa: BLE001 - 单张失败不中断整批
                return {"path": str(p), "ok": False, "desc": None, "error": f"{type(exc).__name__}: {exc}"}

    return await asyncio.gather(*(one(p) for p in paths))


def collect_images(target: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    if target.is_file():
        return [target]
    return sorted(p for p in target.iterdir() if p.suffix.lower() in exts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Day09 图片结构化描述 + 合规初筛")
    parser.add_argument("--images", type=str, default="", help="图片文件或目录")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 张")
    parser.add_argument("--detail", default="high", choices=["low", "high", "auto"], help="视觉 detail 档位")
    parser.add_argument("--max-side", type=int, default=1024, help="压缩后的最长边像素")
    parser.add_argument("--compliance", type=str, default="", metavar="IMAGE", help="对单张图做合规初筛")
    parser.add_argument("--compare", nargs=2, metavar=("IMG_A", "IMG_B"), help="对比两张图（A 在前 B 在后）")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR / "images.jsonl")
    args = parser.parse_args(argv)

    if args.compliance:
        result = check_compliance(Path(args.compliance), max_side=args.max_side)
        print(result.model_dump_json(indent=2))
        return 0

    if args.compare:
        img_a, img_b = Path(args.compare[0]), Path(args.compare[1])
        result = compare_two(img_a, img_b, max_side=args.max_side)
        print(result.model_dump_json(indent=2))
        return 0

    if not args.images:
        parser.error("需要 --images <文件或目录>，或 --compliance <图片>，或 --compare <图A> <图B>")

    paths = collect_images(Path(args.images))
    if args.limit > 0:
        paths = paths[: args.limit]
    if not paths:
        print(f"在 {args.images} 下没有找到图片", file=sys.stderr)
        return 2

    print(f"共 {len(paths)} 张图，开始批量描述（并发 3）…", flush=True)
    results = asyncio.run(batch(paths))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = [r for r in results if r["ok"]]
    failed = len(results) - len(ok)
    print(f"\n完成：{len(ok)} 成功 / {failed} 失败 → {args.out}")
    print("提示：Day 11 检索实验直接使用这份 images.jsonl（scene/search_tags 是检索文本）")
    print(f"累计用量：{json.dumps(get_vl_client().report(), ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
