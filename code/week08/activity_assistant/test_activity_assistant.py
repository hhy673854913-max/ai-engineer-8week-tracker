"""M3 单测：契约 + 离线角色 + 规则检查。"""

from __future__ import annotations

from code.week08.activity_assistant.models import CodeArtifact, Requirement, ReviewReport
from code.week08.activity_assistant.roles import offline_analyst, offline_assets, offline_coder, offline_reviewer, rule_checks


def test_requirement_contract():
    req = offline_analyst("做一个春节签到活动，7天领奖励，奖励是金币")
    assert req.title
    assert req.mechanics
    assert req.rewards
    assert isinstance(req.missing, list)
    assert req.complete == (len(req.missing) == 0)


def test_asset_plan():
    req = offline_analyst("做一个春节签到活动，7天领奖励，奖励是金币")
    assets = offline_assets(req)
    assert assets.images
    assert assets.copywriting
    assert assets.data_needs


def test_coder_produces_valid_html():
    req = offline_analyst("做一个春节签到活动，7天领奖励，奖励是金币")
    code = offline_coder(req)
    assert code.entry == "index.html"
    html = code.files[0]["content"]
    assert "<!doctype html>" in html.lower()
    assert 'name="viewport"' in html


def test_rule_checks_detects_issues():
    bad_html = "<html><body><div></body></html>"
    issues = rule_checks(bad_html)
    severities = [i.severity for i in issues]
    assert "error" in severities or "warn" in severities


def test_reviewer_passes_valid_code():
    req = offline_analyst("做一个春节签到活动，7天领奖励，奖励是金币")
    code = offline_coder(req)
    report = offline_reviewer(code)
    assert report.verdict in ("pass", "revise")
    assert isinstance(report.has_error, bool)
