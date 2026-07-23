from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
BACKEND_DIR = ROOT / "backend"
for path in (TOOLS_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.rowcount = -1
        self._one: tuple[int] | None = None
        self._all: list[tuple[int]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str) -> None:
        normalized = " ".join(sql.split())
        self.connection.executed_sql.append(normalized)
        if normalized == self.connection.fail_on_sql:
            raise RuntimeError("模拟数据库删除失败")
        if normalized.startswith("LOCK TABLE public.core_roi_dashboard_chart"):
            return
        if normalized == "DELETE FROM public.core_roi_dashboard_chart":
            self.connection.delete_sql.append(normalized)
            self.rowcount = self.connection.counts["roi_charts"]
            self.connection.counts["roi_charts"] = 0
            return
        if normalized == "DELETE FROM public.core_roi_dashboard":
            self.connection.delete_sql.append(normalized)
            self.rowcount = self.connection.counts["roi_dashboards"]
            self.connection.counts["roi_dashboards"] = 0
            return
        if normalized == "SELECT COUNT(*) FROM public.core_roi_dashboard_chart":
            self._one = (self.connection.counts["roi_charts"],)
            return
        if normalized == "SELECT COUNT(*) FROM public.core_roi_dashboard":
            self._one = (self.connection.counts["roi_dashboards"],)
            return
        if normalized == "SELECT COUNT(*) FROM public.core_dashboard":
            self._one = (self.connection.counts["core_dashboards"],)
            return
        if "SELECT DISTINCT tenant_id" in normalized:
            self._all = [(tenant_id,) for tenant_id in self.connection.tenant_ids]
            return
        raise AssertionError(f"出现未预期 SQL: {normalized}")

    def fetchone(self) -> tuple[int]:
        assert self._one is not None
        return self._one

    def fetchall(self) -> list[tuple[int]]:
        return list(self._all)

    def copy(self, sql: str):
        normalized = " ".join(sql.split())
        for table_name, payload in self.connection.copy_payloads.items():
            if f"COPY public.{table_name} " in normalized:
                return FakeCopy(payload)
        raise AssertionError(f"出现未预期 COPY: {normalized}")


class FakeCopy:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.read_count = 0

    def __enter__(self) -> FakeCopy:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self) -> bytes:
        if self.read_count:
            return b""
        self.read_count += 1
        return self.payload


class FakeConnection:
    def __init__(
        self,
        *,
        counts: dict[str, int],
        tenant_ids: list[int],
        fail_on_sql: str | None = None,
        copy_payloads: dict[str, bytes] | None = None,
    ) -> None:
        self.counts = dict(counts)
        self.tenant_ids = list(tenant_ids)
        self.fail_on_sql = fail_on_sql
        self.copy_payloads = dict(copy_payloads or {})
        self.executed_sql: list[str] = []
        self.delete_sql: list[str] = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeRedis:
    def __init__(self) -> None:
        self.patterns: list[str] = []
        self.deleted_keys: list[str] = []

    def scan_iter(self, *, match: str, count: int):
        assert count == 200
        self.patterns.append(match)
        yield f"cached:{len(self.patterns)}"

    def delete(self, *keys: str) -> int:
        self.deleted_keys.extend(keys)
        return len(keys)


def test_purge_defaults_to_read_only_preview() -> None:
    try:
        from purge_all_roi_dashboards import PurgeCounts, purge_all_roi_dashboards
    except ModuleNotFoundError:
        pytest.fail("purge_all_roi_dashboards 模块尚未实现")

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101, 202],
    )

    result = purge_all_roi_dashboards(
        apply=False,
        connection_factory=lambda: connection,
        redis_factory=lambda: pytest.fail("只读预检不应连接 Redis"),
    )

    assert result.applied is False
    assert result.before == PurgeCounts(
        roi_charts=8,
        roi_dashboards=3,
        core_dashboards=17,
    )
    assert result.after is None
    assert result.cleared_cache_keys == 0
    assert connection.committed is False
    assert connection.rolled_back is True


def test_apply_deletes_only_roi_tables_then_clears_scoped_roi_cache() -> None:
    from purge_all_roi_dashboards import PurgeCounts, purge_all_roi_dashboards

    from common.core.redis_client import user_redis_key

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101, 202],
    )
    redis = FakeRedis()

    result = purge_all_roi_dashboards(
        apply=True,
        connection_factory=lambda: connection,
        redis_factory=lambda: redis,
    )

    assert connection.delete_sql == [
        "DELETE FROM public.core_roi_dashboard_chart",
        "DELETE FROM public.core_roi_dashboard",
    ]
    assert result.before == PurgeCounts(8, 3, 17)
    assert result.after == PurgeCounts(0, 0, 17)
    assert result.deleted_charts == 8
    assert result.deleted_dashboards == 3
    assert result.cleared_cache_keys == 2
    assert connection.committed is True
    assert redis.patterns == [
        user_redis_key(101, "*", "roi-chart", "*", "*", "*", "*", "*"),
        user_redis_key(202, "*", "roi-chart", "*", "*", "*", "*", "*"),
    ]


def test_apply_rolls_back_and_skips_cache_when_parent_delete_fails() -> None:
    from purge_all_roi_dashboards import purge_all_roi_dashboards

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101],
        fail_on_sql="DELETE FROM public.core_roi_dashboard",
    )
    redis_created = False

    def create_redis():
        nonlocal redis_created
        redis_created = True
        return FakeRedis()

    with pytest.raises(RuntimeError, match="模拟数据库删除失败"):
        purge_all_roi_dashboards(
            apply=True,
            connection_factory=lambda: connection,
            redis_factory=create_redis,
        )

    assert connection.committed is False
    assert connection.rolled_back is True
    assert redis_created is False


def test_cli_requires_explicit_apply_flag() -> None:
    from purge_all_roi_dashboards import parse_args

    assert parse_args([]).apply is False
    assert parse_args(["--apply"]).apply is True


def test_main_prints_auditable_preview_json(capsys: pytest.CaptureFixture[str]) -> None:
    from purge_all_roi_dashboards import main

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101, 202],
    )

    main(
        [],
        connection_factory=lambda: connection,
        redis_factory=lambda: pytest.fail("只读预检不应连接 Redis"),
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "applied": False,
        "before": {
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        "after": None,
        "cleared_cache_keys": 0,
        "deleted_charts": 0,
        "deleted_dashboards": 0,
    }


def test_cache_failure_reports_that_database_delete_was_committed() -> None:
    from purge_all_roi_dashboards import purge_all_roi_dashboards

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101],
    )

    def fail_redis():
        raise RuntimeError("redis unavailable")

    with pytest.raises(RuntimeError, match="数据已删除但 ROI 缓存清理失败"):
        purge_all_roi_dashboards(
            apply=True,
            connection_factory=lambda: connection,
            redis_factory=fail_redis,
        )

    assert connection.committed is True
    assert connection.rolled_back is False


def test_backup_writes_both_roi_tables_and_auditable_manifest(tmp_path: Path) -> None:
    from purge_all_roi_dashboards import backup_roi_tables

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101, 202],
        copy_payloads={
            "core_roi_dashboard_chart": b'id,title\n1,"ROI"\n',
            "core_roi_dashboard": b"id,name\n2,ROI Dashboard\n",
        },
    )

    backup_path = backup_roi_tables(
        connection_factory=lambda: connection,
        backup_dir=tmp_path,
    )

    chart_file = backup_path / "core_roi_dashboard_chart.csv"
    dashboard_file = backup_path / "core_roi_dashboard.csv"
    manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
    assert chart_file.read_bytes() == b'id,title\n1,"ROI"\n'
    assert dashboard_file.read_bytes() == b"id,name\n2,ROI Dashboard\n"
    assert manifest["counts"] == {
        "roi_charts": 8,
        "roi_dashboards": 3,
        "core_dashboards": 17,
    }
    assert manifest["tables"]["core_roi_dashboard_chart"]["sha256"]
    assert manifest["tables"]["core_roi_dashboard"]["sha256"]
    assert connection.committed is False
    assert connection.rolled_back is True


def test_apply_cli_creates_backup_before_delete(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from purge_all_roi_dashboards import main

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101],
        copy_payloads={
            "core_roi_dashboard_chart": b"id,title\n1,ROI\n",
            "core_roi_dashboard": b"id,name\n2,ROI Dashboard\n",
        },
    )

    main(
        ["--apply", "--backup-dir", str(tmp_path)],
        connection_factory=lambda: connection,
        redis_factory=FakeRedis,
    )

    payload = json.loads(capsys.readouterr().out)
    backup_path = Path(payload["backup"])
    assert backup_path.parent == tmp_path
    assert (backup_path / "manifest.json").is_file()
    assert payload["applied"] is True
    assert connection.delete_sql == [
        "DELETE FROM public.core_roi_dashboard_chart",
        "DELETE FROM public.core_roi_dashboard",
    ]


def test_apply_with_backup_uses_one_locked_transaction(tmp_path: Path) -> None:
    from purge_all_roi_dashboards import apply_with_backup

    connection = FakeConnection(
        counts={
            "roi_charts": 8,
            "roi_dashboards": 3,
            "core_dashboards": 17,
        },
        tenant_ids=[101],
        copy_payloads={
            "core_roi_dashboard_chart": b"id,title\n1,ROI\n",
            "core_roi_dashboard": b"id,name\n2,ROI Dashboard\n",
        },
    )
    connection_calls = 0

    def connect() -> FakeConnection:
        nonlocal connection_calls
        connection_calls += 1
        return connection

    result, backup_path = apply_with_backup(
        connection_factory=connect,
        redis_factory=FakeRedis,
        backup_dir=tmp_path,
    )

    assert connection_calls == 1
    assert connection.executed_sql[0] == (
        "LOCK TABLE public.core_roi_dashboard_chart, public.core_roi_dashboard "
        "IN SHARE ROW EXCLUSIVE MODE"
    )
    assert connection.delete_sql == [
        "DELETE FROM public.core_roi_dashboard_chart",
        "DELETE FROM public.core_roi_dashboard",
    ]
    assert connection.committed is True
    assert result.after is not None
    assert result.after.roi_charts == 0
    assert result.after.roi_dashboards == 0
    assert backup_path.parent == tmp_path
