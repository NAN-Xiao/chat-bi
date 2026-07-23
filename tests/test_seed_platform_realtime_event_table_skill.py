from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

module = importlib.import_module("seed_platform_realtime_event_table_skill")


class FakeBackend:
    def __init__(
        self,
        *,
        marker_count: int = 0,
        embedding_error: BaseException | None = None,
    ) -> None:
        self.marker_count = marker_count
        self.embedding_error = embedding_error
        self.events: list[str] = []
        self.updated_markers: list[str] = []
        self.restored_markers: list[str] = []

    def acquire_lock(self) -> None:
        self.events.append("acquire_lock")

    def release_lock(self) -> None:
        self.events.append("release_lock")

    def inspect(self, marker: str):
        self.events.append("inspect")
        if self.marker_count > 1:
            raise RuntimeError("平台实时选表 Skill marker 重复")
        return module.TargetSnapshot(
            skill_id=321 if self.marker_count == 1 else None,
            row=None,
        )

    def backup(self, snapshot):
        self.events.append("backup")
        return {"snapshot": snapshot}

    def upsert(self, skill, snapshot):
        self.events.append("upsert")
        self.updated_markers.append(module.SKILL_MARKER)
        return module.AppliedState(skill_id=321, created=snapshot.skill_id is None)

    def refresh_embedding(self, skill_id: int) -> None:
        self.events.append("refresh_embedding")
        if self.embedding_error is not None:
            raise self.embedding_error

    def verify(self, skill, state) -> None:
        self.events.append("verify")

    def restore(self, backup, state) -> None:
        self.events.append("restore")
        self.restored_markers.append(module.SKILL_MARKER)


def test_skill_is_platform_public_and_keeps_business_semantics_out() -> None:
    assert module.PLATFORM_TENANT_ID == 1
    assert module.VISIBILITY_SCOPE == "PLATFORM_PUBLIC"
    assert module.SPECIFIC_DS is False
    prompt = module.SKILL["prompt"]
    for token in (
        "event_realtime",
        "event",
        "今天",
        "当天",
        "截至目前",
        "按小时",
    ):
        assert token in prompt
    for business_token in ("UserRegister", "ServerPayLog", "110000047", "$.money"):
        assert business_token not in prompt


def test_skill_forbids_silent_fallback_and_requires_current_schema() -> None:
    prompt = module.SKILL["prompt"]
    assert "同时存在" in prompt
    assert "不得静默" in prompt
    assert "权限" in prompt
    assert "工作空间" in prompt
    assert "UNION ALL" in prompt


def test_dry_run_never_writes_or_refreshes_embedding() -> None:
    backend = FakeBackend()

    report = module.publish_skill(backend, apply=False)

    assert report.updated is False
    assert report.embedding_verified is False
    assert backend.events == ["inspect"]


def test_apply_updates_only_target_and_verifies_embedding() -> None:
    backend = FakeBackend()

    report = module.publish_skill(backend, apply=True)

    assert report.updated is True
    assert report.embedding_verified is True
    assert report.skill_id == 321
    assert backend.updated_markers == [module.SKILL_MARKER]
    assert backend.restored_markers == []
    assert backend.events == [
        "acquire_lock",
        "inspect",
        "backup",
        "upsert",
        "refresh_embedding",
        "verify",
        "release_lock",
    ]


def test_embedding_failure_restores_only_target() -> None:
    backend = FakeBackend(embedding_error=RuntimeError("embedding failed"))

    with pytest.raises(RuntimeError, match="embedding failed"):
        module.publish_skill(backend, apply=True)

    assert backend.updated_markers == [module.SKILL_MARKER]
    assert backend.restored_markers == [module.SKILL_MARKER]
    assert backend.events[-2:] == ["restore", "release_lock"]


def test_duplicate_marker_is_rejected_before_write() -> None:
    backend = FakeBackend(marker_count=2)

    with pytest.raises(RuntimeError, match="marker"):
        module.publish_skill(backend, apply=True)

    assert "upsert" not in backend.events
    assert backend.events == ["acquire_lock", "inspect", "release_lock"]


def test_cli_defaults_to_dry_run(monkeypatch, capsys) -> None:
    backend = FakeBackend()
    monkeypatch.setattr(module, "PsycopgPublishBackend", lambda: backend)

    assert module.main([]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["updated"] is False
    assert "upsert" not in backend.events
