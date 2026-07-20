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

module = importlib.import_module("sync_xiuxian_realtime_payment_skill")


CURRENT_SQL = """SELECT DATE_FORMAT(FROM_UNIXTIME(e.time / 1000), '%H:00') AS `小时`,
       COUNT(*) AS `支付记录数`,
       COALESCE(SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18, 4))), 0) AS `收入金额`
FROM event_realtime e
WHERE e.dt = 20260720 AND e.event = 'ServerPayLog' AND e.prod = 110000047
GROUP BY DATE_FORMAT(FROM_UNIXTIME(e.time / 1000), '%H:00')"""


def _source(*, update_time: int = 1784515307, sql: str = CURRENT_SQL):
    canvas = {
        module.REALTIME_VIEW_ID: {
            "sql": sql,
            "chart": {"title": "每小时付费数据"},
        }
    }
    return module.dashboard_source_from_row(
        (
            module.REALTIME_DASHBOARD_ID,
            "实时看板",
            module.TENANT_ID,
            module.DATASOURCE_ID,
            json.dumps(canvas, ensure_ascii=False),
            update_time,
        )
    )


def _skill(prompt_sql: str = CURRENT_SQL) -> dict[str, str]:
    return {
        "name": "修仙实时付费趋势",
        "description": "实时每小时支付记录数与收入金额。",
        "prompt": (
            f"{module.REALTIME_SKILL_MARKER}\n\n"
            "# 修仙实时付费趋势\n\n"
            f"<!-- dashboard-sql:{module.REALTIME_VIEW_ID} -->\n"
            f"```sql\n{prompt_sql}\n```"
        ),
    }


class FakeBackend:
    def __init__(
        self,
        *,
        sources=None,
        embedding_error: BaseException | None = None,
        duplicate_marker: bool = False,
    ):
        self.sources = list(sources or [_source(), _source()])
        self.embedding_error = embedding_error
        self.duplicate_marker = duplicate_marker
        self.events: list[str] = []
        self.updated_skill_ids: list[int] = []
        self.embedding_ids: list[int] = []
        self.restored_skill_ids: list[int] = []

    def load_source(self):
        self.events.append("load_source")
        return self.sources.pop(0)

    def build_skill(self):
        self.events.append("build_skill")
        return _skill()

    def load_skill_hashes(self):
        self.events.append("load_skill_hashes")
        return {skill_id: f"hash-{skill_id}" for skill_id in range(269, 282)}

    def load_target_backup(self):
        self.events.append("load_target_backup")
        if self.duplicate_marker:
            raise RuntimeError("Data Skill marker 重复")
        return {"skills": [{"id": module.EXPECTED_SKILL_ID}], "preferences": []}

    def write_backup(self, source, backup):
        self.events.append("write_backup")
        return Path("backup")

    def acquire_lock(self):
        self.events.append("acquire_lock")

    def release_lock(self):
        self.events.append("release_lock")

    def upsert_target(self, skill):
        self.events.append("upsert_target")
        self.updated_skill_ids.append(module.EXPECTED_SKILL_ID)
        return {module.EXPECTED_SKILL_ID: {"id": module.EXPECTED_SKILL_ID}}

    def refresh_embedding(self, skill_id):
        self.events.append("refresh_embedding")
        self.embedding_ids.append(skill_id)
        if self.embedding_error is not None:
            raise self.embedding_error

    def verify_target(self, skill):
        self.events.append("verify_target")

    def verify_other_hashes(self, hashes):
        self.events.append("verify_other_hashes")

    def retrieve(self, question):
        self.events.append("retrieve")
        assert question == module.RETRIEVAL_QUESTION
        return "修仙实时付费趋势 event_realtime ServerPayLog $.money"

    def restore(self, backup, expected_states):
        self.events.append("restore")
        self.restored_skill_ids.extend(sorted(expected_states))


def test_dashboard_source_extracts_current_single_view_and_sql():
    source = _source()

    assert source.dashboard_id == module.REALTIME_DASHBOARD_ID
    assert source.view_id == module.REALTIME_VIEW_ID
    assert source.sql == CURRENT_SQL
    assert source.title == "每小时付费数据"
    assert len(source.sql_sha256) == 64


def test_sync_dry_run_never_updates_skill_or_embedding():
    backend = FakeBackend(sources=[_source()])

    report = module.sync_realtime_skill(backend, apply=False)

    assert report.updated is False
    assert report.skill_id == module.EXPECTED_SKILL_ID
    assert backend.updated_skill_ids == []
    assert backend.embedding_ids == []
    assert "acquire_lock" not in backend.events


def test_sync_apply_writes_only_skill_269_and_verifies_retrieval():
    backend = FakeBackend()

    report = module.sync_realtime_skill(backend, apply=True)

    assert report.updated is True
    assert report.embedding_verified is True
    assert report.retrieval_verified is True
    assert backend.updated_skill_ids == [269]
    assert backend.embedding_ids == [269]
    assert backend.restored_skill_ids == []
    assert backend.events[-1] == "release_lock"


def test_sync_rejects_changed_dashboard_before_skill_write():
    backend = FakeBackend(sources=[_source(), _source(update_time=1784515308)])

    with pytest.raises(module.SourceDashboardChangedError, match="发生变化"):
        module.sync_realtime_skill(backend, apply=True)

    assert backend.updated_skill_ids == []
    assert backend.embedding_ids == []
    assert backend.restored_skill_ids == []
    assert backend.events[-1] == "release_lock"


def test_embedding_failure_restores_skill_269_only():
    backend = FakeBackend(embedding_error=RuntimeError("embedding failed"))

    with pytest.raises(RuntimeError, match="embedding failed"):
        module.sync_realtime_skill(backend, apply=True)

    assert backend.updated_skill_ids == [269]
    assert backend.restored_skill_ids == [269]
    assert backend.events[-1] == "release_lock"


def test_duplicate_realtime_marker_is_rejected_before_lock():
    backend = FakeBackend(sources=[_source()], duplicate_marker=True)

    with pytest.raises(RuntimeError, match="marker 重复"):
        module.sync_realtime_skill(backend, apply=True)

    assert backend.updated_skill_ids == []
    assert "acquire_lock" not in backend.events


def test_verify_retrieval_requires_skill_and_authoritative_fields():
    module.verify_retrieval_text(
        "修仙实时付费趋势 event_realtime ServerPayLog $.money"
    )

    with pytest.raises(module.RetrievalVerificationError, match="缺少"):
        module.verify_retrieval_text("修仙实时付费趋势 ServerPayLog")


def test_source_metadata_does_not_pollute_signed_recovery_directory(tmp_path):
    backup_path = tmp_path / "20260720-120000"

    metadata_path = module.source_metadata_path(backup_path)

    assert metadata_path.parent == backup_path.parent
    assert metadata_path.name == "20260720-120000.realtime-source.json"
    assert metadata_path.parent != module.skill_recovery_path(backup_path)
