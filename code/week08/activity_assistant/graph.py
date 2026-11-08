"""M3 流水线：需求解析 → 素材 → 代码生成 → 质量检查 → 落盘。

用最朴素的"状态字典 + 顺序执行"实现，等你看懂之后再换成 Day 24 的 LangGraph 状态图。
这样你能对比两者的差别：框架带来的是可持久化、可路由、可中断，不是"更聪明"。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AssetPlan, CodeArtifact, Requirement, ReviewReport
from .roles import (
    llm_analyst,
    llm_coder,
    llm_reviewer,
    offline_analyst,
    offline_assets,
    offline_coder,
    offline_reviewer,
)

ROOT = Path(__file__).resolve().parents[3]


def _write_run(out_root: Path, run_id: str, state: dict[str, Any]) -> Path:
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    req: Requirement = state["requirement"]
    assets: AssetPlan = state["assets"]
    code: CodeArtifact = state["code"]
    review: ReviewReport = state["review"]

    (run_dir / "requirement.json").write_text(req.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "assets.json").write_text(assets.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "timeline.json").write_text(json.dumps(state["timeline"], ensure_ascii=False, indent=2), encoding="utf-8")

    for file in code.files:
        target = run_dir / file["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file["content"], encoding="utf-8")

    review_md = ["# 自检报告", "", f"结论：**{review.verdict}**", "", "## 评分"]
    review_md += [f"- {k}: {v}" for k, v in review.scores.items()]
    review_md += ["", "## 问题"]
    if review.issues:
        review_md += [f"- [{i.severity}] {i.rule}: {i.message}" for i in review.issues]
    else:
        review_md.append("- 无")
    (run_dir / "review.md").write_text("\n".join(review_md), encoding="utf-8")

    assets_md = ["# 素材清单", "", "## 图片"] + [f"- {i['name']} ({i['size']})：{i['purpose']}" for i in assets.images]
    assets_md += ["", "## 文案"] + [f"- {k}: {v}" for k, v in assets.copywriting.items()]
    assets_md += ["", "## 配置"] + [f"- {k}: {v}" for k, v in assets.configs.items()]
    assets_md += ["", "## 埋点"] + [f"- {d}" for d in assets.data_needs]
    (run_dir / "assets.md").write_text("\n".join(assets_md), encoding="utf-8")
    return run_dir


def run_pipeline(
    requirement_text: str,
    *,
    offline: bool = True,
    client: Any | None = None,
    out_root: Path | None = None,
) -> dict[str, Any]:
    out_root = out_root or ROOT / "runs"
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    timeline: list[dict[str, Any]] = []

    def step(name: str, fn, *args):
        t0 = time.perf_counter()
        result = fn(*args)
        timeline.append({"name": name, "ms": int((time.perf_counter() - t0) * 1000)})
        return result

    if offline or client is None:
        requirement = step("analyst", offline_analyst, requirement_text)
        assets = step("asset", offline_assets, requirement)
        code = step("coder", offline_coder, requirement)
        review = step("reviewer", offline_reviewer, code)
    else:
        requirement = step("analyst", llm_analyst, client, requirement_text)
        assets = step("asset", offline_assets, requirement)  # 素材为模板生成，无需模型
        code = step("coder", llm_coder, client, requirement)
        review = step("reviewer", llm_reviewer, client, code)
        if review.has_error:  # 一轮修复
            code = step("coder_revise", llm_coder, client, requirement)
            review = step("reviewer_revise", llm_reviewer, client, code)

    state = {
        "run_id": run_id,
        "requirement": requirement,
        "assets": assets,
        "code": code,
        "review": review,
        "timeline": timeline,
        "blocked_by": requirement.missing,
    }
    run_dir = _write_run(out_root, run_id, state)
    state["run_dir"] = str(run_dir)
    return state
