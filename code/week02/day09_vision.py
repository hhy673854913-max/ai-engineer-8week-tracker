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
import sys
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.shared.llm_client import get_client  # noqa: E402
from code.shared.structured import model_from_text  # noqa: E402

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
    client = get_client()
    content = build_content(DESCRIBE_PROMPT, path, detail=detail, max_side=max_side)
    resp = client.chat([{"role": "user", "content": content}], temperature=0.2, max_tokens=600)
    return model_from_text(resp.content, ImageDesc)


async def describe_async(path: Path, *, detail: str = "high", max_side: int = 1024) -> ImageDesc:
    client = get_client()
    content = build_content(DESCRIBE_PROMPT, path, detail=detail, max_side=max_side)
    resp = await client.achat([{"role": "user", "content": content}], temperature=0.2, max_tokens=600)
    return model_from_text(resp.content, ImageDesc)


# ---------------------------------------------------------------------------
# 任务 4：合规初筛
# ---------------------------------------------------------------------------


def check_compliance(path: Path, *, max_side: int = 1024) -> ComplianceResult:
    client = get_client()
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
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR / "images.jsonl")
    args = parser.parse_args(argv)

    if args.compliance:
        result = check_compliance(Path(args.compliance), max_side=args.max_side)
        print(result.model_dump_json(indent=2))
        return 0

    if not args.images:
        parser.error("需要 --images <文件或目录>，或 --compliance <图片>")

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
    print(f"累计用量：{json.dumps(get_client().report(), ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
