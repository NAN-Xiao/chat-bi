from __future__ import annotations

import importlib.util
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = ROOT / "tools" / "seed_xiuxian_data_skills.py"


def _load_seed_module():
    if not SEED_SCRIPT.exists():
        pytest.fail("缺少修仙 Data Skill 种子脚本")
    tools_path = str(ROOT / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    spec = importlib.util.spec_from_file_location("seed_xiuxian_data_skills", SEED_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_xiuxian_date_partition_skill_is_scoped_and_actionable():
    module = _load_seed_module()

    assert module.TENANT_ID == 7482727237662281728
    assert module.DATASOURCE_ID == 6
    assert len(module.DATA_SKILLS) == 1

    skill = module.DATA_SKILLS[0]
    prompt = skill["prompt"]
    assert prompt.lstrip().startswith(
        "<!-- data-skill-source:xiuxian:date-partition-aggregation -->"
    )
    assert "`dt` 是 `YYYYMMDD` 格式的整数业务日期分区字段" in prompt
    assert "WHERE e.dt BETWEEN" in prompt
    assert "GROUP BY e.dt" in prompt
    assert "ORDER BY e.dt" in prompt
    assert "STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')" in prompt
    assert "'%Y-%m-%d'" in prompt
    assert "AS dt" in prompt
    assert "MAX(e.dt) AS end_dt" in prompt
    assert "INTERVAL 27 DAY" in prompt
    assert "## 最近 30 个完整自然日窗口" in prompt
    assert "仅当问题明确要求最近 30 个完整自然日" in prompt
    assert "DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 29 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
    assert "AS start_dt" in prompt


class _FakeCursor:
    def __init__(self):
        self.skill_id = None
        self.fetchone_result = None
        self.rowcount = 0
        self.statements: list[str] = []

    def execute(self, sql, _params=None):
        normalized = " ".join(str(sql).split())
        self.statements.append(normalized)
        self.rowcount = 0
        if "pg_advisory_xact_lock" in normalized:
            self.fetchone_result = (None,)
        elif normalized.startswith("SELECT id FROM custom_prompt"):
            self.fetchone_result = (self.skill_id,) if self.skill_id is not None else None
        elif normalized.startswith("INSERT INTO custom_prompt"):
            self.skill_id = 255
            self.fetchone_result = (self.skill_id,)
            self.rowcount = 1
        elif normalized.startswith("UPDATE custom_prompt"):
            self.fetchone_result = None
            self.rowcount = 1

    def fetchone(self):
        return self.fetchone_result


class _FakeConnection:
    def __init__(self):
        self.cursor_instance = _FakeCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return nullcontext(self.cursor_instance)

    def commit(self):
        self.committed = True


def test_upsert_is_serialized_and_reuses_the_existing_record():
    module = _load_seed_module()
    cursor = _FakeCursor()
    now = datetime(2026, 7, 15, 14, 0, 0)

    first_id = module._upsert_skill(cursor, skill=module.DATA_SKILLS[0], now=now)
    second_id = module._upsert_skill(cursor, skill=module.DATA_SKILLS[0], now=now)

    assert first_id == second_id == 255
    assert sum("pg_advisory_xact_lock" in sql for sql in cursor.statements) == 2
    assert sum(sql.startswith("INSERT INTO custom_prompt") for sql in cursor.statements) == 1
    assert sum(sql.startswith("UPDATE custom_prompt") for sql in cursor.statements) == 1
    written_sql = " ".join(cursor.statements)
    assert "visibility_scope = 'ADMIN_PUBLIC'" in written_sql
    assert "specific_ds = TRUE" in written_sql
    assert "active = TRUE" in written_sql


def test_main_fails_when_embedding_cannot_be_saved(monkeypatch):
    module = _load_seed_module()
    connection = _FakeConnection()
    monkeypatch.setattr(module.psycopg, "connect", lambda **_kwargs: connection)
    monkeypatch.setattr(module, "_save_embeddings", lambda _ids: 0)

    with pytest.raises(RuntimeError, match="embedding"):
        module.main()

    assert connection.committed is True
