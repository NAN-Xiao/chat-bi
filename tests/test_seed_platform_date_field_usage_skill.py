from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
BACKEND_DIR = ROOT / "backend"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

module = importlib.import_module("seed_platform_date_field_usage_skill")


def test_skill_is_platform_public_and_domain_agnostic() -> None:
    assert module.PLATFORM_TENANT_ID == 1
    assert module.VISIBILITY_SCOPE == "PLATFORM_PUBLIC"
    assert module.SPECIFIC_DS is False
    prompt = module.SKILL["prompt"]
    for token in (
        "range_filter",
        "display_only",
        "cohort_date",
        "event_time",
        "realtime_partition",
        "date_filter.time_field",
        "dashboard_start_yyyymmdd",
        "dashboard_end_yyyymmdd",
        "yyyymmdd_number",
        "yyyymmdd_text",
        "realtime_date_policy",
    ):
        assert token in prompt
    for business_token in (
        "Flam",
        "修仙",
        "event_realtime",
        "ServerPayLog",
        "userinfo.regdate",
        "$.money",
    ):
        assert business_token not in prompt


def test_skill_requires_date_field_and_parameter_contract() -> None:
    prompt = module.SKILL["prompt"]
    assert "必须等于 SQL 中实际参数化字段" in prompt
    assert "没有日期 token 时不能返回普通 `date_filter`" in prompt
    assert "默认实时查询不套用历史日期 pivot" in prompt
    assert "不得静默回退" in prompt


def test_dashboard_date_tokens_keep_double_braces_in_skill_and_model_prompt() -> None:
    from apps.chat.models.chat_model import AiModelQuestion

    start_token = "{{dashboard_start_yyyymmdd}}"
    end_token = "{{dashboard_end_yyyymmdd}}"
    prompt = module.SKILL["prompt"]

    assert start_token in prompt
    assert end_token in prompt
    assert prompt.count(start_token) == 1
    assert prompt.count(end_token) == 1

    model_prompt = AiModelQuestion(
        engine="MySQL 8.0",
        db_schema="【DB_ID】 test\n【Schema】",
        data_skill=prompt,
    ).sql_sys_question("mysql")["data_skill"]
    assert start_token in model_prompt
    assert end_token in model_prompt


class FakeBackend:
    def __init__(self, *, marker_count: int = 0) -> None:
        self.marker_count = marker_count
        self.events: list[str] = []

    def acquire_lock(self) -> None:
        self.events.append("acquire_lock")

    def release_lock(self) -> None:
        self.events.append("release_lock")

    def inspect(self, marker: str):
        self.events.append("inspect")
        if self.marker_count > 1:
            raise RuntimeError("marker duplicated")
        return module.TargetSnapshot(
            skill_id=321 if self.marker_count else None,
            row=None,
        )

    def backup(self, snapshot):
        self.events.append("backup")
        return {"snapshot": snapshot}

    def upsert(self, skill, snapshot):
        self.events.append("upsert")
        return module.AppliedState(
            skill_id=321,
            created=snapshot.skill_id is None,
            expected_name=skill["name"],
            expected_description=skill["description"],
            expected_prompt=skill["prompt"].strip(),
        )

    def refresh_embedding(self, skill_id: int) -> None:
        self.events.append("refresh_embedding")

    def verify(self, skill, state) -> None:
        self.events.append("verify")

    def restore(self, backup, state) -> None:
        self.events.append("restore")


def test_dry_run_is_read_only_and_apply_uses_publish_protocol() -> None:
    backend = FakeBackend()
    dry_run = module.publish_skill(backend, apply=False)
    assert dry_run.mode == "dry-run"
    assert backend.events == ["inspect"]

    applied = module.publish_skill(backend, apply=True)
    assert applied.mode == "apply"
    assert applied.embedding_verified is True
    assert backend.events[1:] == [
        "acquire_lock",
        "inspect",
        "backup",
        "upsert",
        "refresh_embedding",
        "verify",
        "release_lock",
    ]


def test_duplicate_marker_is_rejected_before_write() -> None:
    backend = FakeBackend(marker_count=2)
    with pytest.raises(RuntimeError, match="marker"):
        module.publish_skill(backend, apply=True)
    assert backend.events == ["acquire_lock", "inspect", "release_lock"]


def test_cli_defaults_to_dry_run(monkeypatch, capsys) -> None:
    backend = FakeBackend()
    monkeypatch.setattr(module, "PsycopgPublishBackend", lambda: backend)
    assert module.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["updated"] is False
