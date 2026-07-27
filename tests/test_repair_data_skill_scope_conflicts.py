from __future__ import annotations

import copy
import hashlib
import importlib
import sys
from pathlib import Path

import pytest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _module():
    sys.modules.pop("repair_data_skill_scope_conflicts", None)
    return importlib.import_module("repair_data_skill_scope_conflicts")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _valid_rows() -> dict[int, dict[str, object]]:
    common = {
        "type": "DATA_SKILL",
        "target_scope": "ALL",
        "ai_model_id": None,
        "active": True,
        "visible": True,
        "specific_ds": False,
        "datasource_ids": [],
        "embedding": "old-vector",
        "embedding_signature": "old-signature",
    }
    return {
        171: {
            **common,
            "id": 171,
            "name": "平台通用 Data Skill：时间字段、观察窗口与日期边界",
            "description": "通用时间规则",
            "tenant_id": 1,
            "create_by": None,
            "visibility_scope": "PLATFORM_PUBLIC",
            "prompt": "平台时间规则正文",
        },
        234: {
            **common,
            "id": 234,
            "name": "平台通用 Data Skill：取数据的约束",
            "description": "取数的优化",
            "tenant_id": 1,
            "create_by": 1,
            "visibility_scope": "PLATFORM_PUBLIC",
            "prompt": "不要全表扫描 应该先用时间过滤再查询对应数据",
        },
        280: {
            **common,
            "id": 280,
            "name": "示例：修仙 资源获取与消耗统计口径",
            "description": "资源统计口径",
            "tenant_id": 7482727237662281728,
            "create_by": 7482253745313550336,
            "visibility_scope": "USER_PRIVATE",
            "prompt": "用户私有资源偏好正文",
        },
    }


class FakeBackend:
    def __init__(
        self,
        rows: dict[int, dict[str, object]],
        *,
        fail_embedding=False,
        apply_error_after_write: BaseException | None = None,
    ):
        self.rows = copy.deepcopy(rows)
        self.fail_embedding = fail_embedding
        self.apply_error_after_write = apply_error_after_write
        self.events: list[str] = []
        self.updated_ids: tuple[int, ...] = ()
        self.restored = False

    def acquire_lock(self) -> None:
        self.events.append("lock")

    def release_lock(self) -> None:
        self.events.append("unlock")

    def inspect(self, *, for_update: bool = False):
        self.events.append("inspect-for-update" if for_update else "inspect")
        return copy.deepcopy(self.rows)

    def backup(self, rows):
        self.events.append("backup")
        return copy.deepcopy(rows)

    def apply_updates(self, originals, desired):
        self.events.append("apply")
        assert self.rows == originals
        changed = tuple(
            skill_id for skill_id in sorted(desired) if desired[skill_id] != originals[skill_id]
        )
        self.rows = copy.deepcopy(desired)
        self.updated_ids = changed
        if self.apply_error_after_write is not None:
            raise self.apply_error_after_write
        return changed

    def refresh_embeddings(self, skill_ids):
        self.events.append("embedding")
        if self.fail_embedding:
            raise RuntimeError("embedding failed")
        for skill_id in skill_ids:
            self.rows[skill_id]["embedding"] = f"vector-{skill_id}"
            self.rows[skill_id]["embedding_signature"] = f"signature-{skill_id}"

    def verify(self, desired):
        self.events.append("verify")
        for skill_id, expected in desired.items():
            for key, value in expected.items():
                if key not in {"embedding", "embedding_signature"}:
                    assert self.rows[skill_id][key] == value
        assert self.rows[171]["embedding_signature"]
        assert self.rows[280]["embedding_signature"]
        assert self.rows[234]["embedding"] is None
        assert self.rows[234]["embedding_signature"] is None

    def restore(self, backup, expected):
        self.events.append("restore")
        self.rows = copy.deepcopy(backup)
        self.restored = True


@pytest.fixture
def configured_module(monkeypatch):
    module = _module()
    rows = _valid_rows()
    monkeypatch.setattr(
        module,
        "EXPECTED_PROMPT_SHA256",
        {skill_id: _sha256(str(row["prompt"])) for skill_id, row in rows.items()},
    )
    return module


def test_expected_live_prompt_hashes_are_fixed() -> None:
    module = _module()
    assert module.EXPECTED_PROMPT_SHA256 == {
        171: "96f7fb760fb14b62cd84df9ba3a4e21da615ead3c12cc7324bceb2a5a8145c2c",
        234: "a7330d9e46175e1a991d058492a0b2d72323ef0e780a62d3e66a1320257c09ec",
        280: "3073d524631de743c6b87019cf28fd717ef4ea7314b86ff5284be082b7bd9514",
    }


def test_dry_run_validates_without_writing(configured_module) -> None:
    backend = FakeBackend(_valid_rows())
    before = copy.deepcopy(backend.rows)

    report = configured_module.repair_skills(backend, apply=False)

    assert report.updated is False
    assert report.target_ids == (171, 234, 280)
    assert backend.rows == before
    assert backend.events == ["inspect"]


def test_apply_merges_234_into_171_and_scopes_280(configured_module) -> None:
    backend = FakeBackend(_valid_rows())
    protected_280 = copy.deepcopy(backend.rows[280])

    report = configured_module.repair_skills(backend, apply=True)

    assert report.updated_ids == (171, 234, 280)
    assert backend.rows[280]["specific_ds"] is True
    assert backend.rows[280]["datasource_ids"] == [6]
    assert backend.rows[234]["active"] is False
    assert backend.rows[234]["visible"] is False
    assert backend.rows[234]["embedding"] is None
    assert backend.rows[234]["embedding_signature"] is None
    assert configured_module.BOUNDED_SCAN_MARKER in backend.rows[171]["prompt"]
    for key, value in protected_280.items():
        if key not in {"specific_ds", "datasource_ids", "embedding", "embedding_signature"}:
            assert backend.rows[280][key] == value
    assert backend.events[:4] == ["lock", "inspect-for-update", "backup", "apply"]
    assert backend.events[-1] == "unlock"


@pytest.mark.parametrize(
    ("skill_id", "field", "value"),
    [
        (171, "name", "漂移名称"),
        (234, "visibility_scope", "USER_PRIVATE"),
        (280, "create_by", 1),
        (280, "prompt", "漂移正文"),
    ],
)
def test_apply_rejects_any_precondition_drift(
    configured_module, skill_id: int, field: str, value: object
) -> None:
    rows = _valid_rows()
    rows[skill_id][field] = value
    backend = FakeBackend(rows)

    with pytest.raises(RuntimeError, match="前置状态"):
        configured_module.repair_skills(backend, apply=True)

    assert "backup" not in backend.events
    assert "apply" not in backend.events
    assert backend.events[-1] == "unlock"


def test_embedding_failure_restores_all_three_rows(configured_module) -> None:
    original = _valid_rows()
    backend = FakeBackend(original, fail_embedding=True)

    with pytest.raises(RuntimeError, match="embedding failed"):
        configured_module.repair_skills(backend, apply=True)

    assert backend.restored is True
    assert backend.rows == original
    assert backend.events[-2:] == ["restore", "unlock"]


def test_unknown_commit_state_restores_when_write_was_applied(configured_module) -> None:
    original = _valid_rows()
    backend = FakeBackend(
        original,
        apply_error_after_write=configured_module.CommitStateUnknownError(
            "commit acknowledgement lost"
        ),
    )

    with pytest.raises(
        configured_module.CommitStateUnknownError,
        match="commit acknowledgement lost",
    ):
        configured_module.repair_skills(backend, apply=True)

    assert backend.restored is True
    assert backend.rows == original
    assert backend.events[-2:] == ["restore", "unlock"]


def test_repeated_apply_keeps_one_managed_section(configured_module) -> None:
    backend = FakeBackend(_valid_rows())
    configured_module.repair_skills(backend, apply=True)

    report = configured_module.repair_skills(backend, apply=True)

    assert backend.rows[171]["prompt"].count(configured_module.BOUNDED_SCAN_MARKER) == 1
    assert report.updated_ids == ()
