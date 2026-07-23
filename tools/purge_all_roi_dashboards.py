# -*- coding: utf-8 -*-
"""一次性物理清理全部工作空间的 ROI 看板与图表。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import psycopg
from redis import Redis

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ROI_BACKUP_TABLES = (
    "core_roi_dashboard_chart",
    "core_roi_dashboard",
)



@dataclass(frozen=True)
class PurgeCounts:
    roi_charts: int
    roi_dashboards: int
    core_dashboards: int


@dataclass(frozen=True)
class PurgeSnapshot:
    counts: PurgeCounts
    tenant_ids: tuple[int, ...]


@dataclass(frozen=True)
class PurgeResult:
    applied: bool
    before: PurgeCounts
    after: PurgeCounts | None
    cleared_cache_keys: int
    deleted_charts: int = 0
    deleted_dashboards: int = 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="物理删除全部工作空间的 ROI 看板和图表；默认仅预检",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=ROOT / ".codex-runtime" / "pg-backups",
        help="--apply 前保存两张 ROI 表备份的目录",
    )
    return parser.parse_args(argv)


def create_system_db_connection() -> Any:
    return psycopg.connect(**core_system_db_config())


def create_redis_client() -> Redis:
    from common.core.redis_client import build_redis_url

    return Redis.from_url(build_redis_url(), decode_responses=True)


def _copy_table_to_file(cursor: Any, table_name: str, target: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with cursor.copy(
        f"COPY public.{table_name} TO STDOUT WITH (FORMAT CSV, HEADER TRUE)"
    ) as copy:
        with target.open("wb") as output:
            while chunk := copy.read():
                data = bytes(chunk)
                output.write(data)
                digest.update(data)
                size += len(data)
    return {
        "file": target.name,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "format": "postgresql_csv_header",
    }


def _write_roi_backup(
    cursor: Any,
    snapshot: PurgeSnapshot,
    backup_dir: Path,
) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    target_dir = backup_dir / f"roi-dashboard-purge-{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=False)
    tables = {
        table_name: _copy_table_to_file(
            cursor,
            table_name,
            target_dir / f"{table_name}.csv",
        )
        for table_name in ROI_BACKUP_TABLES
    }
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "counts": asdict(snapshot.counts),
        "tables": tables,
    }
    (target_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_dir


def backup_roi_tables(
    *,
    connection_factory: Callable[[], Any],
    backup_dir: Path,
) -> Path:

    with connection_factory() as connection:
        try:
            with connection.cursor() as cursor:
                snapshot = collect_purge_snapshot(cursor)
                target_dir = _write_roi_backup(cursor, snapshot, backup_dir)
                connection.rollback()
        except Exception:
            connection.rollback()
            raise
    return target_dir


def clear_roi_chart_cache(
    tenant_ids: tuple[int, ...],
    redis_factory: Callable[[], Any],
) -> int:
    if not tenant_ids:
        return 0
    from common.core.redis_client import user_redis_key

    client = redis_factory()
    cleared = 0
    for tenant_id in tenant_ids:
        pattern = user_redis_key(
            tenant_id,
            "*",
            "roi-chart",
            "*",
            "*",
            "*",
            "*",
            "*",
        )
        keys = list(client.scan_iter(match=pattern, count=200))
        if keys:
            cleared += int(client.delete(*keys))
    return cleared


def collect_purge_snapshot(cursor: Any) -> PurgeSnapshot:
    cursor.execute("SELECT COUNT(*) FROM public.core_roi_dashboard_chart")
    roi_charts = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM public.core_roi_dashboard")
    roi_dashboards = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM public.core_dashboard")
    core_dashboards = int(cursor.fetchone()[0])
    cursor.execute(
        """
        SELECT DISTINCT tenant_id
        FROM (
            SELECT tenant_id FROM public.core_roi_dashboard_chart
            UNION
            SELECT tenant_id FROM public.core_roi_dashboard
        ) AS roi_tenants
        ORDER BY tenant_id
        """
    )
    tenant_ids = tuple(int(row[0]) for row in cursor.fetchall())
    return PurgeSnapshot(
        counts=PurgeCounts(
            roi_charts=roi_charts,
            roi_dashboards=roi_dashboards,
            core_dashboards=core_dashboards,
        ),
        tenant_ids=tenant_ids,
    )


def _delete_roi_records(
    connection: Any,
    cursor: Any,
    snapshot: PurgeSnapshot,
) -> PurgeResult:
    cursor.execute("DELETE FROM public.core_roi_dashboard_chart")
    deleted_charts = int(cursor.rowcount)
    cursor.execute("DELETE FROM public.core_roi_dashboard")
    deleted_dashboards = int(cursor.rowcount)
    after = collect_purge_snapshot(cursor).counts
    if after.roi_charts or after.roi_dashboards:
        raise RuntimeError("ROI 表物理删除后仍存在记录，事务已回滚")
    if after.core_dashboards != snapshot.counts.core_dashboards:
        raise RuntimeError("普通看板记录数异常，事务已回滚")
    connection.commit()
    return PurgeResult(
        applied=True,
        before=snapshot.counts,
        after=after,
        cleared_cache_keys=0,
        deleted_charts=deleted_charts,
        deleted_dashboards=deleted_dashboards,
    )


def _clear_cache_after_commit(
    result: PurgeResult,
    tenant_ids: tuple[int, ...],
    redis_factory: Callable[[], Any],
) -> PurgeResult:
    try:
        cleared_cache_keys = clear_roi_chart_cache(tenant_ids, redis_factory)
    except Exception as exc:
        raise RuntimeError("数据已删除但 ROI 缓存清理失败") from exc
    return replace(result, cleared_cache_keys=cleared_cache_keys)


def purge_all_roi_dashboards(
    *,
    apply: bool,
    connection_factory: Callable[[], Any],
    redis_factory: Callable[[], Any],
) -> PurgeResult:
    with connection_factory() as connection:
        try:
            with connection.cursor() as cursor:
                snapshot = collect_purge_snapshot(cursor)
                if not apply:
                    connection.rollback()
                    return PurgeResult(
                        applied=False,
                        before=snapshot.counts,
                        after=None,
                        cleared_cache_keys=0,
                    )
                result = _delete_roi_records(connection, cursor, snapshot)
        except Exception:
            connection.rollback()
            raise

    return _clear_cache_after_commit(result, snapshot.tenant_ids, redis_factory)


def apply_with_backup(
    *,
    connection_factory: Callable[[], Any],
    redis_factory: Callable[[], Any],
    backup_dir: Path,
) -> tuple[PurgeResult, Path]:
    with connection_factory() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "LOCK TABLE public.core_roi_dashboard_chart, "
                    "public.core_roi_dashboard IN SHARE ROW EXCLUSIVE MODE"
                )
                snapshot = collect_purge_snapshot(cursor)
                backup_path = _write_roi_backup(cursor, snapshot, backup_dir)
                result = _delete_roi_records(connection, cursor, snapshot)
        except Exception:
            connection.rollback()
            raise

    result = _clear_cache_after_commit(result, snapshot.tenant_ids, redis_factory)
    return result, backup_path


def main(
    argv: Sequence[str] | None = None,
    *,
    connection_factory: Callable[[], Any] = create_system_db_connection,
    redis_factory: Callable[[], Any] = create_redis_client,
) -> None:
    args = parse_args(argv)
    if args.apply:
        result, backup_path = apply_with_backup(
            connection_factory=connection_factory,
            redis_factory=redis_factory,
            backup_dir=args.backup_dir,
        )
    else:
        backup_path = None
        result = purge_all_roi_dashboards(
            apply=False,
            connection_factory=connection_factory,
            redis_factory=redis_factory,
        )
    payload = asdict(result)
    if backup_path is not None:
        payload["backup"] = str(backup_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
