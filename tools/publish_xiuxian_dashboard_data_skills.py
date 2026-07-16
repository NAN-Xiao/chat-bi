# -*- coding: utf-8 -*-
"""安全编排修仙推荐看板 SQL 修复与工作空间 Data Skill 发布。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence
from uuid import uuid4

import psycopg
import sqlglot

from core_system_db import core_system_db_config, export_postgres_compat_env
from seed_xiuxian_data_skills import (
    BACKEND_DIR,
    DATASOURCE_ID,
    LEGACY_PAYMENT_MARKER,
    TENANT_ID,
    _acquire_publish_lock,
    _embedding_model,
    _release_publish_lock,
    _save_embeddings,
    backup_existing_skills,
    build_data_skills,
    restore_skills,
    upsert_skills,
    verify_embeddings,
)
from xiuxian_dashboard_snapshot import (
    DEFAULT_BACKUP_ROOT,
    DashboardSnapshot,
    load_recommended_dashboards,
    verify_backup,
    write_verified_backup,
)
from xiuxian_dashboard_sql_repair import (
    REPAIR_SPECS,
    ResultMismatchError,
    apply_dashboard_repairs,
    compare_query_results,
    execute_query,
    freeze_curdate,
    rewrite_bounds_sql,
    validate_explain_plan,
)


EXPECTED_REPAIR_COUNT = 11
SKILL_BACKUP_VERSION = 1
SKILL_BACKUP_SUFFIX = ".skill-recovery"
SKILL_BACKUP_FILENAME = "skills.json"
LEGACY_PAYMENT_MARKER_TEXT = "paybuyret-monetization-arppu"


class PublishPhase(Enum):
    """发布状态机已经通过的最后一道门禁。"""

    LOADED = auto()
    BACKED_UP = auto()
    BACKUP_VERIFIED = auto()
    SQL_EQUIVALENT = auto()
    PLANS_VERIFIED = auto()
    SKILLS_BUILT = auto()
    DASHBOARDS_APPLIED = auto()
    SKILLS_APPLIED = auto()
    EMBEDDINGS_VERIFIED = auto()
    RETRIEVAL_VERIFIED = auto()


class RetrievalSmokeError(RuntimeError):
    """发布后的 Data Skill 未通过 Smart Q&A 召回门禁。"""


@dataclass(frozen=True)
class RetrievalSmokeCase:
    question: str
    expected_skill: str
    require_serverpaylog: bool = False


RETRIEVAL_SMOKE_CASES = (
    RetrievalSmokeCase("最近七天新增用户趋势", "修仙新增用户总量与系统归因"),
    RetrievalSmokeCase("最近一个月 DAU WAU MAU", "修仙 DAU、WAU 与 MAU"),
    RetrievalSmokeCase("各渠道新增用户次日留存", "修仙新增 cohort 留存"),
    RetrievalSmokeCase(
        "最近七天收入和 ARPPU",
        "修仙 ServerPayLog 收入与 ARPU/ARPPU",
        require_serverpaylog=True,
    ),
    RetrievalSmokeCase("英雄升级与升星情况", "修仙英雄养成"),
)


@dataclass(frozen=True)
class PublishReport:
    mode: str
    phase: PublishPhase
    backup_path: Path
    repaired_view_count: int
    skill_count: int
    dashboard_update_count: int = 0
    skill_ids: tuple[int, ...] = ()
    retrieval_results: Mapping[str, str] | None = None


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


@contextmanager
def _connection_scope(factory: Callable[[], Any]) -> Iterator[Any]:
    connection = factory()
    if connection is None:
        raise RuntimeError("连接工厂未返回数据库连接")
    try:
        yield connection
    finally:
        close = getattr(connection, "close", None)
        if callable(close):
            close()


@contextmanager
def _cursor_scope(connection: Any) -> Iterator[Any]:
    cursor = connection.cursor()
    enter = getattr(cursor, "__enter__", None)
    if callable(enter):
        with cursor as entered:
            yield entered
        return
    try:
        yield cursor
    finally:
        close = getattr(cursor, "close", None)
        if callable(close):
            close()


def _repair_drawers(dashboards: Sequence[Any]) -> dict[str, Any]:
    wanted = set(REPAIR_SPECS)
    drawers: dict[str, Any] = {}
    for dashboard in dashboards:
        for drawer in dashboard.drawers:
            view_id = str(drawer.view_id)
            if view_id not in wanted:
                continue
            if view_id in drawers:
                raise ValueError(f"待修复抽屉重复：{view_id}")
            drawers[view_id] = drawer
    missing = sorted(wanted.difference(drawers))
    if missing or len(drawers) != EXPECTED_REPAIR_COUNT:
        raise ValueError(
            f"待修复抽屉必须严格为 {EXPECTED_REPAIR_COUNT} 条，missing={missing}"
        )
    return drawers


def _has_order_by(sql: str) -> bool:
    return bool(sqlglot.parse_one(sql, read="mysql").args.get("order"))


def validate_all_repairs(
    dashboards: Sequence[Any], datasource_connection: Any
) -> dict[str, str]:
    """同一数据源会话中逐条验证 11 对原 SQL 与改写 SQL。"""

    drawers = _repair_drawers(dashboards)
    rewritten_by_view: dict[str, str] = {}
    with _cursor_scope(datasource_connection) as cursor:
        cursor.execute("SELECT CURDATE()")
        row = cursor.fetchone()
        if not row or row[0] is None:
            raise RuntimeError("无法从数据源读取统一业务日期")
        business_date = row[0]
        if isinstance(business_date, dt.datetime):
            business_date = business_date.date()
        if not isinstance(business_date, dt.date):
            business_date = dt.date.fromisoformat(str(business_date))

        for view_id in REPAIR_SPECS:
            original_sql = drawers[view_id].sql
            rewritten_sql = rewrite_bounds_sql(view_id, original_sql)
            original_result = execute_query(
                cursor, freeze_curdate(original_sql, business_date)
            )
            rewritten_result = execute_query(
                cursor, freeze_curdate(rewritten_sql, business_date)
            )
            try:
                compare_query_results(
                    original_result,
                    rewritten_result,
                    ordered=_has_order_by(original_sql),
                )
            except ResultMismatchError as exc:
                raise ResultMismatchError(f"view={view_id} {exc}") from exc
            rewritten_by_view[view_id] = rewritten_sql
    return rewritten_by_view


def validate_all_plans(
    rewritten_sql_by_view: Mapping[str, str], datasource_connection: Any
) -> None:
    """逐条执行只读 EXPLAIN，并拒绝日期边界广播 Hash Join。"""

    if set(rewritten_sql_by_view) != set(REPAIR_SPECS):
        raise ValueError("EXPLAIN 输入必须完整覆盖 11 条修复目录")
    with _cursor_scope(datasource_connection) as cursor:
        for view_id in REPAIR_SPECS:
            cursor.execute(f"EXPLAIN {rewritten_sql_by_view[view_id]}")
            plan = "\n".join(
                " ".join(str(value) for value in row)
                for row in cursor.fetchall()
            )
            try:
                validate_explain_plan(plan)
            except Exception as exc:
                raise type(exc)(f"view={view_id} {exc}") from exc


def apply_repairs_in_memory(
    dashboards: Sequence[DashboardSnapshot],
    rewritten_sql_by_view: Mapping[str, str],
) -> list[DashboardSnapshot]:
    """只在内存快照中替换已验证 SQL，供 Skill 生成器消费。"""

    if set(rewritten_sql_by_view) != set(REPAIR_SPECS):
        raise ValueError("内存改写必须完整覆盖 11 条修复目录")
    applied: set[str] = set()
    repaired: list[DashboardSnapshot] = []
    for dashboard in dashboards:
        canvas = json.loads(dashboard.canvas_view_info)
        for view_id, view in canvas.items():
            view_id = str(view_id)
            if view_id not in rewritten_sql_by_view:
                continue
            view["sql"] = rewritten_sql_by_view[view_id]
            applied.add(view_id)
        repaired.append(
            DashboardSnapshot.from_row(
                (
                    dashboard.id,
                    dashboard.name,
                    dashboard.tenant_id,
                    dashboard.datasource,
                    json.dumps(canvas, ensure_ascii=False, separators=(",", ":")),
                )
            )
        )
    if applied != set(REPAIR_SPECS):
        raise ValueError("内存改写未覆盖完整修复目录")
    return repaired


def _skill_markers(skills: Sequence[Mapping[str, str]]) -> list[str]:
    markers = []
    for skill in skills:
        prompt = str(skill.get("prompt") or "")
        marker = prompt.splitlines()[0].strip() if prompt else ""
        if not marker:
            raise ValueError("Data Skill 缺少 source marker")
        markers.append(marker)
    markers.append(LEGACY_PAYMENT_MARKER)
    return markers


def _json_default(value: Any) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def skill_recovery_path(backup_path: Path) -> Path:
    """返回与看板备份目录相邻、互不污染 manifest 的恢复目录。"""

    backup_path = Path(backup_path)
    return backup_path.parent / f"{backup_path.name}{SKILL_BACKUP_SUFFIX}"


def backup_and_write_skill_snapshot(
    connection: Any,
    skills: Sequence[Mapping[str, str]],
    backup_path: Path,
) -> dict[str, list[dict[str, Any]]]:
    """读取现有 Skill，并原子写入独立的恢复工件目录。"""

    markers = _skill_markers(skills)
    with _cursor_scope(connection) as cursor:
        backup = backup_existing_skills(cursor, markers)
    target = skill_recovery_path(backup_path)
    if target.exists():
        raise FileExistsError(target)
    staging = target.with_name(
        f".{target.name}.{os.getpid()}.{uuid4().hex}.staging"
    )
    staging.mkdir(parents=False, exist_ok=False)
    try:
        skills_payload = {"markers": markers, "backup": backup}
        skills_bytes = _json_bytes(skills_payload)
        (staging / SKILL_BACKUP_FILENAME).write_bytes(skills_bytes)
        manifest = {
            "version": SKILL_BACKUP_VERSION,
            "tenant_id": TENANT_ID,
            "datasource_id": DATASOURCE_ID,
            "skill_count": len(backup.get("skills", ())),
            "preference_count": len(backup.get("preferences", ())),
            "markers": markers,
            "file_sha256": {
                SKILL_BACKUP_FILENAME: _sha256_bytes(skills_bytes)
            },
        }
        (staging / "manifest.json").write_bytes(_json_bytes(manifest))
        staging.replace(target)
    except BaseException:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()
        raise
    return backup


def verify_skill_backup(
    backup_path: Path,
) -> dict[str, list[dict[str, Any]]]:
    """重新读取并验签独立 Skill 恢复工件。"""

    recovery_path = skill_recovery_path(backup_path)
    manifest_path = recovery_path / "manifest.json"
    skills_path = recovery_path / SKILL_BACKUP_FILENAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = json.loads(skills_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取有效的 Skill 恢复工件") from exc
    if not isinstance(manifest, dict) or not isinstance(payload, dict):
        raise ValueError("Skill 恢复工件结构无效")
    actual_files = {path.name for path in recovery_path.iterdir() if path.is_file()}
    if actual_files != {"manifest.json", SKILL_BACKUP_FILENAME}:
        raise ValueError("Skill 恢复工件文件集合无效")
    if (
        manifest.get("version") != SKILL_BACKUP_VERSION
        or manifest.get("tenant_id") != TENANT_ID
        or manifest.get("datasource_id") != DATASOURCE_ID
    ):
        raise ValueError("Skill 恢复工件版本或作用域无效")
    expected_hashes = manifest.get("file_sha256")
    if not isinstance(expected_hashes, dict) or set(expected_hashes) != {
        SKILL_BACKUP_FILENAME
    }:
        raise ValueError("Skill 恢复工件哈希清单无效")
    if _sha256_bytes(skills_path.read_bytes()) != expected_hashes[
        SKILL_BACKUP_FILENAME
    ]:
        raise ValueError("Skill 恢复工件文件哈希不一致")
    markers = payload.get("markers")
    backup = payload.get("backup")
    if not isinstance(markers, list) or markers != manifest.get("markers"):
        raise ValueError("Skill 恢复工件 marker 清单不一致")
    if not isinstance(backup, dict):
        raise ValueError("Skill 恢复快照结构无效")
    skills = backup.get("skills")
    preferences = backup.get("preferences")
    if not isinstance(skills, list) or not isinstance(preferences, list):
        raise ValueError("Skill 恢复快照记录结构无效")
    if (
        len(skills) != manifest.get("skill_count")
        or len(preferences) != manifest.get("preference_count")
    ):
        raise ValueError("Skill 恢复工件记录数量不一致")
    if manifest_path.read_bytes() != _json_bytes(manifest):
        raise ValueError("Skill 恢复 manifest 不是规范化文件")
    return {"skills": skills, "preferences": preferences}


def acquire_publish_lock(connection: Any) -> None:
    with _cursor_scope(connection) as cursor:
        _acquire_publish_lock(cursor)


def release_publish_lock(connection: Any) -> None:
    with _cursor_scope(connection) as cursor:
        _release_publish_lock(cursor)


def upsert_and_commit_skills(
    connection: Any, skills: Sequence[dict[str, str]]
) -> list[int]:
    try:
        with _cursor_scope(connection) as cursor:
            ids = upsert_skills(cursor, skills, now=dt.datetime.now())
        connection.commit()
        return ids
    except BaseException:
        try:
            connection.rollback()
        except BaseException:
            pass
        raise


def refresh_and_verify_embeddings(
    connection: Any,
    ids: Sequence[int],
    embedding_refresher: Callable[[list[int]], int],
    model_factory: Callable[[], Any] | None = None,
) -> None:
    normalized_ids = [int(skill_id) for skill_id in ids]
    saved = embedding_refresher(normalized_ids)
    if saved != len(normalized_ids):
        raise RuntimeError(
            f"Data Skill embedding 保存不完整: 期望 {len(normalized_ids)}，实际 {saved}"
        )
    model = (model_factory or _embedding_model)()
    with _cursor_scope(connection) as cursor:
        verify_embeddings(cursor, normalized_ids, model=model)


def restore_published_skills(
    connection: Any,
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
    markers: Sequence[str],
) -> None:
    """按本轮 marker 查询当前记录，再用原快照恢复。"""

    try:
        connection.rollback()
    except BaseException:
        pass
    try:
        with _cursor_scope(connection) as cursor:
            current = backup_existing_skills(cursor, markers)
            affected_ids = [int(row["id"]) for row in current.get("skills", ())]
            restore_skills(cursor, backup, affected_ids=affected_ids)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _connection_is_usable(connection: Any) -> bool:
    return not bool(getattr(connection, "closed", False)) and not bool(
        getattr(connection, "broken", False)
    )


def _restore_with_new_connection(
    system_connection_factory: Callable[[], Any],
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
    markers: Sequence[str],
    *,
    original_lock_held: bool,
) -> None:
    """始终使用新连接恢复；原 session 失效时重新获取发布锁。"""

    with _connection_scope(system_connection_factory) as recovery_connection:
        recovery_lock_held = False
        if not original_lock_held:
            acquire_publish_lock(recovery_connection)
            recovery_lock_held = True
        try:
            restore_published_skills(recovery_connection, backup, markers)
        finally:
            if recovery_lock_held and _connection_is_usable(recovery_connection):
                release_publish_lock(recovery_connection)


def _retrieval_text(result: Any) -> str:
    if isinstance(result, tuple):
        result = result[0] if result else ""
    return str(result or "")


def verify_retrieval(
    retrieval_checker: Callable[[str], Any]
) -> dict[str, str]:
    results: dict[str, str] = {}
    for case in RETRIEVAL_SMOKE_CASES:
        text = _retrieval_text(retrieval_checker(case.question))
        if case.expected_skill not in text:
            raise RetrievalSmokeError(
                f"问题“{case.question}”未召回主题 Skill：{case.expected_skill}"
            )
        if case.require_serverpaylog and "ServerPayLog" not in text:
            raise RetrievalSmokeError("ARPPU 召回文本缺少 ServerPayLog")
        if case.require_serverpaylog and LEGACY_PAYMENT_MARKER_TEXT in text:
            raise RetrievalSmokeError("ARPPU 召回文本仍包含旧付费 marker")
        results[case.question] = text
    return results


def run_publish(
    mode: str = "dry-run",
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    system_connection_factory: Callable[[], Any] | None = None,
    datasource_connection_factory: Callable[[], Any] | None = None,
    embedding_refresher: Callable[[list[int]], int] | None = None,
    retrieval_checker: Callable[[str], Any] | None = None,
) -> PublishReport:
    """按不可绕过的门禁顺序执行 dry-run 或 apply。"""

    if mode not in {"dry-run", "apply"}:
        raise ValueError("mode 只允许 dry-run 或 apply")
    system_factory = system_connection_factory or _default_system_connection_factory
    datasource_factory = (
        datasource_connection_factory or _default_datasource_connection_factory
    )

    with _connection_scope(system_factory) as system_read_connection:
        dashboards = load_recommended_dashboards(system_read_connection)
    phase = PublishPhase.LOADED
    backup_path = write_verified_backup(
        dashboards, Path(backup_root), utc_timestamp()
    )
    phase = PublishPhase.BACKED_UP
    verify_backup(backup_path)
    phase = PublishPhase.BACKUP_VERIFIED

    with _connection_scope(datasource_factory) as datasource_connection:
        repairs = validate_all_repairs(dashboards, datasource_connection)
        phase = PublishPhase.SQL_EQUIVALENT
        validate_all_plans(repairs, datasource_connection)
    phase = PublishPhase.PLANS_VERIFIED
    repaired_dashboards = apply_repairs_in_memory(dashboards, repairs)
    skills = build_data_skills(repaired_dashboards)
    phase = PublishPhase.SKILLS_BUILT

    if mode == "dry-run":
        return PublishReport(
            mode=mode,
            phase=phase,
            backup_path=backup_path,
            repaired_view_count=len(repairs),
            skill_count=len(skills),
        )

    refresher = embedding_refresher or _save_embeddings
    checker = retrieval_checker or _default_retrieval_checker
    with _connection_scope(system_factory) as system_write_connection:
        acquire_publish_lock(system_write_connection)
        publish_error: BaseException | None = None
        ids: list[int] = []
        skill_backup: dict[str, list[dict[str, Any]]] | None = None
        skill_publish_started = False
        markers = _skill_markers(skills)
        try:
            updated = apply_dashboard_repairs(
                system_write_connection,
                dashboards,
                repairs,
                tenant_id=TENANT_ID,
                update_time=dt.datetime.now(),
            )
            phase = PublishPhase.DASHBOARDS_APPLIED
            backup_and_write_skill_snapshot(
                system_write_connection, skills, backup_path
            )
            skill_backup = verify_skill_backup(backup_path)
            skill_publish_started = True
            ids = upsert_and_commit_skills(system_write_connection, skills)
            phase = PublishPhase.SKILLS_APPLIED
            refresh_and_verify_embeddings(
                system_write_connection, ids, refresher
            )
            phase = PublishPhase.EMBEDDINGS_VERIFIED
            retrieval_results = verify_retrieval(checker)
            phase = PublishPhase.RETRIEVAL_VERIFIED
        except BaseException as exc:
            publish_error = exc
            if skill_backup is not None and skill_publish_started:
                _restore_with_new_connection(
                    system_factory,
                    skill_backup,
                    markers,
                    original_lock_held=_connection_is_usable(
                        system_write_connection
                    ),
                )
            raise
        finally:
            if _connection_is_usable(system_write_connection):
                try:
                    release_publish_lock(system_write_connection)
                except BaseException:
                    if publish_error is None:
                        raise

    return PublishReport(
        mode=mode,
        phase=phase,
        backup_path=backup_path,
        repaired_view_count=len(repairs),
        skill_count=len(skills),
        dashboard_update_count=updated,
        skill_ids=tuple(ids),
        retrieval_results=retrieval_results,
    )


def _default_system_connection_factory() -> Any:
    return psycopg.connect(**core_system_db_config())


def _setup_backend_imports() -> None:
    export_postgres_compat_env(core_system_db_config())
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def _default_datasource_connection_factory() -> Any:
    import pymysql

    _setup_backend_imports()
    from apps.datasource.models.datasource import DatasourceConf
    from apps.datasource.utils.utils import aes_decrypt

    with psycopg.connect(**core_system_db_config()) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT type, configuration
                FROM core_datasource
                WHERE id = %s AND tenant_id = %s
                """,
                (DATASOURCE_ID, TENANT_ID),
            )
            row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"未找到修仙数据源 {DATASOURCE_ID}")
    datasource_type, configuration = row
    if str(datasource_type).lower() != "mysql":
        raise RuntimeError(
            f"修仙数据源 {DATASOURCE_ID} 类型不是 mysql：{datasource_type}"
        )
    conf = DatasourceConf(**json.loads(aes_decrypt(configuration)))
    return pymysql.connect(
        host=conf.host,
        port=int(conf.port),
        user=conf.username,
        password=conf.password,
        database=conf.database,
        charset="utf8mb4",
        connect_timeout=20,
        read_timeout=180,
        write_timeout=180,
    )


def _default_retrieval_checker(question: str) -> str:
    _setup_backend_imports()
    from sqlmodel import Session

    from apps.chat.curd.custom_prompt import find_data_skills
    from common.core.db import engine

    with Session(engine) as session:
        text, _logs, _model = find_data_skills(
            session,
            datasource=DATASOURCE_ID,
            tenant_id=TENANT_ID,
            target_scope="SMART_QA",
            question=question,
        )
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="默认只执行备份和全部只读门禁；显式 apply 才写系统库",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=DEFAULT_BACKUP_ROOT,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_publish(mode=args.mode, backup_root=args.backup_root)
    print(
        json.dumps(
            {
                "mode": report.mode,
                "phase": report.phase.name,
                "backup_path": str(report.backup_path.resolve()),
                "repaired_view_count": report.repaired_view_count,
                "skill_count": report.skill_count,
                "dashboard_update_count": report.dashboard_update_count,
                "skill_ids": list(report.skill_ids),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
