"""M3 的角色实现：离线规则版 + LLM 版。

离线版让整条流水线在没有 API Key 时也能跑通（CI 与演示），
同时它也是 LLM 版的 baseline。
"""

from __future__ import annotations

import json
import re
from typing import Any

try:  # lxml 可选
    from lxml import etree
except ImportError:  # pragma: no cover
    etree = None  # type: ignore[assignment]

from .models import AssetPlan, CodeArtifact, Requirement, ReviewIssue, ReviewReport

# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------


def offline_analyst(text: str) -> Requirement:
    """规则版需求解析：足够把离线链路跑通。"""
    rewards = re.findall(r"奖励(?:是|为)?([^，。；\n]+)", text) or ["待确认奖励"]
    mechanics = [m for m in ("组队", "签到", "抽奖", "分享", "对战") if m in text] or ["待确认玩法"]
    missing = []
    if not re.search(r"\d+\s*月|\d+/\d+|春节|情人节|周年庆|国庆|元旦", text):
        missing.append("活动时间")
    if "奖励" not in text:
        missing.append("奖励内容")
    return Requirement(
        title=text[:12].strip() or "活动",
        goal=text,
        target_users="全体玩家",
        mechanics=[f"{m}玩法" for m in mechanics],
        rewards=rewards,
        constraints=["不得使用绝对化用语", "需适配移动端"],
        missing=missing,
    )


def llm_analyst(client: Any, text: str) -> Requirement:
    from code.shared.structured import extract_json, loads_lenient
    from .prompts import ANALYST_PROMPT

    raw = client.chat(
        [{"role": "user", "content": ANALYST_PROMPT.format(requirement=text)}],
        temperature=0.2,
        response_format={"type": "json_object"},
    ).content
    return Requirement.model_validate(loads_lenient(extract_json(raw)))


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------


def offline_assets(req: Requirement) -> AssetPlan:
    return AssetPlan(
        images=[{"name": "kv", "size": "750x400", "purpose": "主视觉"}],
        copywriting={
            "headline": req.title,
            "sub": req.goal[:30],
            "rules": "；".join(req.mechanics),
            "cta": "立即参与",
        },
        configs={"activity_id": "auto_generated", "start_time": "待配置", "end_time": "待配置"},
        data_needs=["page_view", "join_click", "reward_claim"],
    )


# ---------------------------------------------------------------------------
# Coder
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: -apple-system, "PingFang SC", sans-serif; background:#fff4f6; color:#3a2b2f; }}
  .card {{ max-width: 420px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 24px; margin: 12px 0; }}
  .rules {{ list-style: none; padding: 0; }}
  .rules li {{ background:#fff; border-radius: 12px; padding: 10px 14px; margin: 8px 0; font-size: 14px; }}
  .reward {{ background:#ffe3ea; border-radius: 12px; padding: 14px; font-size: 15px; }}
  button {{ width: 100%; margin-top: 16px; padding: 14px; font-size: 16px;
            border: 0; border-radius: 999px; background:#e8487a; color:#fff; }}
  #toast {{ position: fixed; left: 50%; bottom: 40px; transform: translateX(-50%);
            background: rgba(0,0,0,.78); color:#fff; padding: 10px 18px; border-radius: 20px;
            font-size: 14px; opacity: 0; transition: opacity .25s; }}
  #toast.show {{ opacity: 1; }}
</style>
</head>
<body>
<div class="card">
  <h1>{title}</h1>
  <p>{goal}</p>
  <ul class="rules">{rules}</ul>
  <div class="reward">奖励：{rewards}</div>
  <button id="join" type="button">立即参与</button>
</div>
<div id="toast" role="status" aria-live="polite"></div>
<script>
  const toast = document.getElementById('toast');
  document.getElementById('join').addEventListener('click', () => {{
    toast.textContent = '已记录参与意向（演示）';
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 1600);
  }});
</script>
</body>
</html>
"""


def offline_coder(req: Requirement) -> CodeArtifact:
    html = HTML_TEMPLATE.format(
        title=req.title,
        goal=req.goal,
        rules="".join(f"<li>{m}</li>" for m in req.mechanics),
        rewards="、".join(req.rewards),
    )
    return CodeArtifact(files=[{"path": "index.html", "content": html}], entry="index.html", notes="离线模板生成")


def llm_coder(client: Any, req: Requirement) -> CodeArtifact:
    from code.shared.structured import extract_json, loads_lenient
    from .prompts import CODER_PROMPT

    raw = client.chat(
        [{"role": "user", "content": CODER_PROMPT.format(requirement=req.model_dump_json())}],
        temperature=0.4,
        response_format={"type": "json_object"},
        max_tokens=3000,
    ).content
    return CodeArtifact.model_validate(loads_lenient(extract_json(raw)))


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------


def rule_checks(html: str) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if 'name="viewport"' not in html:
        issues.append(ReviewIssue(severity="warn", rule="responsive", message="缺少 viewport meta"))
    if "onclick=" in html:
        issues.append(ReviewIssue(severity="info", rule="a11y", message="建议用 addEventListener"))
    if re.search(r"https?://(?!127\.0\.0\.1)", html):
        issues.append(ReviewIssue(severity="warn", rule="external", message="存在外部资源引用"))
    if etree is not None:
        try:
            etree.fromstring(html, etree.HTMLParser())
        except Exception as exc:  # noqa: BLE001
            issues.append(ReviewIssue(severity="error", rule="syntax", message=str(exc)))
    return issues


def offline_reviewer(code: CodeArtifact) -> ReviewReport:
    html = next((f["content"] for f in code.files if f["path"].endswith(".html")), "")
    issues = rule_checks(html)
    has_error = any(i.severity == "error" for i in issues)
    return ReviewReport(
        scores={"compliance": 80, "responsive": 90 if 'name="viewport"' in html else 50, "a11y": 70, "tracking": 60},
        issues=issues,
        verdict="revise" if has_error else "pass",
    )


def llm_reviewer(client: Any, code: CodeArtifact) -> ReviewReport:
    from code.shared.structured import extract_json, loads_lenient
    from .prompts import REVIEW_PROMPT

    html = next((f["content"] for f in code.files if f["path"].endswith(".html")), "")
    raw = client.chat(
        [{"role": "user", "content": REVIEW_PROMPT.format(code=html[:6000])}],
        temperature=0,
        response_format={"type": "json_object"},
    ).content
    parsed = loads_lenient(extract_json(raw))
    llm_report = ReviewReport.model_validate(parsed)
    llm_report.issues.extend(rule_checks(html))  # 规则问题合并进来，硬错误一票否决
    if llm_report.has_error:
        llm_report.verdict = "revise"
    return llm_report


def to_json(model: Any) -> str:
    return json.dumps(model.model_dump(), ensure_ascii=False, indent=2)
