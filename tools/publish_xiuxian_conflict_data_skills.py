"""定向发布本次冲突修复涉及的修仙 Data Skill 255/257/276。"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from core_system_db import core_system_db_config, export_postgres_compat_env
from psycopg.types.json import Jsonb
from seed_xiuxian_data_skills import (
    BACKEND_DIR,
    DATA_SKILLS,
    DATASOURCE_ID,
    EMPTY_DASHBOARD_VIEW_ID,
    SERVERPAYLOG_MANAGED_SECTION,
    SERVERPAYLOG_MARKER,
    SERVERPAYLOG_VALIDATION,
    TENANT_ID,
    _acquire_publish_lock,
    _embedding_model,
    _release_publish_lock,
    _save_embeddings,
    _topic_authority,
    _topic_marker,
    _topic_prompt_view_ids,
    backup_existing_skills,
    dashboard_sql_block,
    load_skill_states_by_ids,
    restore_skills,
    upsert_skills,
    verify_embeddings,
)
from xiuxian_dashboard_skill_catalog import (
    TOPICS,
    build_topic_prompt,
    validate_catalog,
    validate_prompt_length,
)
from xiuxian_dashboard_snapshot import load_recommended_dashboards


ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = ROOT / ".codex-runtime" / "xiuxian-conflict-skill-backups"
TARGET_IDS = (255, 257, 276)
TARGET_TOPIC_SLUGS = ("serverpaylog-revenue", "payer-penetration")
TARGET_MARKERS = (
    "<!-- data-skill-source:xiuxian:date-partition-aggregation -->",
    SERVERPAYLOG_MARKER,
    "<!-- data-skill-source:xiuxian:dashboard:payer-penetration -->",
)
EXPECTED_PROMPT_SHA256 = {
    255: "7cd08a4e2eb004da53c2f7c4cbb4d51e876e135102f7bd8f15c185e24152e698",
    257: "3f4e71604bc26aef9489b7ef5abf0f9bcc9c813c8b82c2d4031968179206116a",
    276: "21028189d3e6bb09a1e4e19be21a0e5457d6322b687de722a7d3353c6a60d669",
}
EXPECTED_MANAGED_PROMPT_SHA256 = {
    255: frozenset(
        {"c6bb80e11e23b974e314848b12cf60275bd87a742f51e995c8de454c0b27f8f0"}
    ),
    257: frozenset(
        {
            "cab8dd8f0e86d5fcfaf91ba7c2e94b4601fbbc6ab2e5ecae61bec119ebd09ee9",
            "f10f5eeacabc878c25f041a66d0762cae45e9552a710db8870b0e546aef9babd",
        }
    ),
    276: frozenset(
        {
            "9bbfd4ab33b1f78a6db5c5c9182f7781a4d46f84ef4c8cb3e27508b6f84fa2c4",
            "cc37009eb7aff627ac83ddd04c219e8ea958e82fdb1ee5d7513259479d981145",
            "c3e8b93933999b5b2f34eb12a487ca56a9062c4cbf033b9560da7ef443051051",
        }
    ),
}
EXPECTED_INITIAL_DESCRIPTIONS = {
    255: "修仙 datasource_id=6 日期趋势口径：最近15天补齐新增趋势、按日补零、固定非递归日期骨架。",
    257: "真实收入、付费人均指标与新增首日付费 cohort。",
    276: "付费用户、渗透率与累计金额。",
}


@dataclass(frozen=True)
class PublishReport:
    mode: str
    target_ids: tuple[int, ...]
    updated: bool
    embedding_verified: bool
    backup_path: str | None = None


def _target_topic(slug: str):
    return next(topic for topic in TOPICS if topic.slug == slug)


def build_target_skills(dashboards: Sequence[Any]) -> list[dict[str, str]]:
    """只重建目标主题；无关主题缺少抽屉不会降低本次发布安全性。"""

    validate_catalog()
    drawers: dict[str, Any] = {}
    for dashboard in dashboards:
        if int(dashboard.tenant_id) != TENANT_ID or int(dashboard.datasource) != DATASOURCE_ID:
            raise ValueError("推荐看板不属于修仙 datasource 6")
        for drawer in dashboard.drawers:
            view_id = str(drawer.view_id)
            if view_id in drawers:
                raise ValueError(f"推荐看板抽屉重复：{view_id}")
            drawers[view_id] = drawer

    skills = [copy.deepcopy(DATA_SKILLS[0])]
    for slug in TARGET_TOPIC_SLUGS:
        topic = _target_topic(slug)
        view_ids = _topic_prompt_view_ids(topic)
        missing = sorted(set(view_ids).difference(drawers))
        if missing:
            raise ValueError(f"目标主题抽屉缺失：{slug}, view_ids={missing}")
        effective_topic = replace(topic, view_ids=view_ids)
        sections = [_topic_marker(slug)]
        if slug == "serverpaylog-revenue":
            sections.append(SERVERPAYLOG_VALIDATION)
        sections.extend(
            [
                build_topic_prompt(effective_topic),
                "## 工作空间边界\n仅适用于修仙工作空间 datasource_id=6；不得传播到其他工作空间或数据源。",
            ]
        )
        authority = _topic_authority(slug)
        if authority:
            sections.append(authority)
        sections.extend(
            dashboard_sql_block(view_id, str(drawers[view_id].sql or ""))
            for view_id in view_ids
        )
        if slug == "serverpaylog-revenue":
            sections.append(SERVERPAYLOG_MANAGED_SECTION)
        prompt = "\n\n".join(sections).strip()
        validate_prompt_length(prompt)
        skills.append(
            {
                "name": topic.name,
                "description": topic.description,
                "prompt": prompt,
            }
        )
    if tuple(skill["prompt"].splitlines()[0] for skill in skills) != TARGET_MARKERS:
        raise RuntimeError("定向发布 Skill marker 顺序不一致")
    return skills


def _prompt_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").strip().encode("utf-8")).hexdigest()


def _load_target_rows(cursor: Any, *, for_update: bool) -> dict[int, dict[str, Any]]:
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT to_jsonb(cp)
        FROM custom_prompt cp
        WHERE cp.id = ANY(%s)
        ORDER BY cp.id{suffix}
        """,
        (list(TARGET_IDS),),
    )
    return {int(row[0]["id"]): dict(row[0]) for row in cursor.fetchall()}


def _validate_target_rows(
    rows: Mapping[int, Mapping[str, Any]],
    skills: Sequence[Mapping[str, str]],
) -> None:
    if set(rows) != set(TARGET_IDS):
        raise RuntimeError(f"定向 Skill ID 不完整：{tuple(sorted(rows))}")
    desired_by_id = dict(zip(TARGET_IDS, skills, strict=True))
    for skill_id, marker in zip(TARGET_IDS, TARGET_MARKERS, strict=True):
        row = rows[skill_id]
        identity = {
            "tenant_id": TENANT_ID,
            "type": "DATA_SKILL",
            "create_by": None,
            "target_scope": "ALL",
            "active": True,
            "visible": True,
            "visibility_scope": "ADMIN_PUBLIC",
            "specific_ds": True,
            "datasource_ids": [DATASOURCE_ID],
        }
        mismatched = [key for key, value in identity.items() if row.get(key) != value]
        if mismatched:
            raise RuntimeError(f"Skill {skill_id} 前置作用域漂移：{mismatched}")
        desired_skill = desired_by_id[skill_id]
        if row.get("name") != str(desired_skill["name"])[:255]:
            raise RuntimeError(f"Skill {skill_id} 前置名称漂移")
        if row.get("description") not in {
            EXPECTED_INITIAL_DESCRIPTIONS[skill_id],
            desired_skill["description"],
        }:
            raise RuntimeError(f"Skill {skill_id} 前置描述漂移")
        prompt = str(row.get("prompt") or "")
        if prompt.count(marker) != 1:
            raise RuntimeError(f"Skill {skill_id} source marker 漂移")
        allowed_hashes = {
            EXPECTED_PROMPT_SHA256[skill_id],
            _prompt_hash(desired_by_id[skill_id]["prompt"]),
            *EXPECTED_MANAGED_PROMPT_SHA256[skill_id],
        }
        if _prompt_hash(prompt) not in allowed_hashes:
            raise RuntimeError(f"Skill {skill_id} prompt SHA256 前置状态漂移")


def _other_skill_hashes(cursor: Any) -> dict[int, str]:
    cursor.execute(
        """
        SELECT id, name, description, prompt, embedding_signature
        FROM custom_prompt
        WHERE tenant_id = %s
          AND type = 'DATA_SKILL'
          AND specific_ds = TRUE
          AND datasource_ids = %s::jsonb
          AND position('data-skill-source:xiuxian:' in COALESCE(prompt, '')) > 0
          AND NOT (id = ANY(%s))
        ORDER BY id
        """,
        (TENANT_ID, Jsonb([DATASOURCE_ID]), list(TARGET_IDS)),
    )
    hashes = {
        int(skill_id): hashlib.sha256(
            json.dumps(
                [name, description, prompt, signature],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for skill_id, name, description, prompt, signature in cursor.fetchall()
    }
    if len(hashes) != 10:
        raise RuntimeError(f"目标之外的修仙 Data Skill 应为 10 条，实际 {len(hashes)}")
    return hashes


def _write_backup(
    backup_root: Path,
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = Path(backup_root) / timestamp / "recovery.json"
    target.parent.mkdir(parents=True, exist_ok=False)
    payload = json.dumps(
        {"target_ids": TARGET_IDS, "markers": TARGET_MARKERS, "backup": backup},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    target.write_bytes(payload)
    manifest = target.with_name("manifest.json")
    manifest.write_text(
        json.dumps(
            {"recovery_sha256": hashlib.sha256(payload).hexdigest()},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    saved = target.read_bytes()
    saved_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        saved_manifest.get("recovery_sha256") != hashlib.sha256(saved).hexdigest()
        or json.loads(saved)["target_ids"] != list(TARGET_IDS)
    ):
        raise RuntimeError("定向 Skill 恢复备份验签失败")
    return target


def _setup_backend() -> None:
    export_postgres_compat_env(core_system_db_config())
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def _verify_published(
    cursor: Any,
    skills: Sequence[Mapping[str, str]],
) -> None:
    rows = _load_target_rows(cursor, for_update=False)
    for skill_id, skill in zip(TARGET_IDS, skills, strict=True):
        row = rows[skill_id]
        expected = {
            "name": str(skill["name"])[:255],
            "description": skill["description"],
            "prompt": str(skill["prompt"]).strip(),
            "tenant_id": TENANT_ID,
            "type": "DATA_SKILL",
            "create_by": None,
            "target_scope": "ALL",
            "active": True,
            "visible": True,
            "visibility_scope": "ADMIN_PUBLIC",
            "specific_ds": True,
            "datasource_ids": [DATASOURCE_ID],
        }
        mismatched = [key for key, value in expected.items() if row.get(key) != value]
        if mismatched:
            raise RuntimeError(f"Skill {skill_id} 发布后字段不一致：{mismatched}")
    verify_embeddings(cursor, list(TARGET_IDS), model=_embedding_model())


def _restore(
    backup: Mapping[str, Sequence[Mapping[str, Any]]],
    expected_states: Mapping[int, Mapping[str, Any]],
) -> None:
    with psycopg.connect(**core_system_db_config()) as connection:
        with connection.cursor() as cursor:
            _acquire_publish_lock(cursor)
        try:
            with connection.cursor() as cursor:
                restore_skills(
                    cursor,
                    backup,
                    affected_ids=list(TARGET_IDS),
                    expected_states=expected_states,
                )
            connection.commit()
        finally:
            with connection.cursor() as cursor:
                _release_publish_lock(cursor)


def run_publish(*, apply: bool, backup_root: Path = BACKUP_ROOT) -> PublishReport:
    with psycopg.connect(**core_system_db_config()) as read_connection:
        dashboards = load_recommended_dashboards(read_connection)
        skills = build_target_skills(dashboards)
        with read_connection.cursor() as cursor:
            rows = _load_target_rows(cursor, for_update=False)
            _validate_target_rows(rows, skills)
    if not apply:
        return PublishReport(
            mode="dry-run",
            target_ids=TARGET_IDS,
            updated=False,
            embedding_verified=False,
        )

    backup: Mapping[str, Sequence[Mapping[str, Any]]] | None = None
    expected_states: dict[int, dict[str, Any]] = {}
    write_started = False
    lock_held = False
    connection = psycopg.connect(**core_system_db_config())
    try:
        with connection.cursor() as cursor:
            _acquire_publish_lock(cursor)
        lock_held = True
        locked_dashboards = load_recommended_dashboards(connection)
        locked_skills = build_target_skills(locked_dashboards)
        if [_prompt_hash(skill["prompt"]) for skill in locked_skills] != [
            _prompt_hash(skill["prompt"]) for skill in skills
        ]:
            raise RuntimeError("发布锁内目标看板 SQL 已漂移")
        with connection.cursor() as cursor:
            rows = _load_target_rows(cursor, for_update=True)
            _validate_target_rows(rows, skills)
            other_hashes = _other_skill_hashes(cursor)
            backup = backup_existing_skills(cursor, list(TARGET_MARKERS))
        backup_path = _write_backup(backup_root, backup)
        write_started = True
        with connection.cursor() as cursor:
            ids = upsert_skills(cursor, list(skills), now=dt.datetime.now())
            if tuple(ids) != TARGET_IDS:
                raise RuntimeError(f"定向 upsert 改变了 Skill ID：{ids}")
            expected_states.update(load_skill_states_by_ids(cursor, ids))
        connection.commit()

        _setup_backend()
        saved = _save_embeddings(list(TARGET_IDS))
        if saved != len(TARGET_IDS):
            raise RuntimeError(
                f"定向 Skill embedding 刷新不完整：期望 {len(TARGET_IDS)}，实际 {saved}"
            )
        with connection.cursor() as cursor:
            _verify_published(cursor, skills)
            if _other_skill_hashes(cursor) != other_hashes:
                raise RuntimeError("目标之外的修仙 Data Skill 发生变化")
        return PublishReport(
            mode="apply",
            target_ids=TARGET_IDS,
            updated=True,
            embedding_verified=True,
            backup_path=str(backup_path),
        )
    except BaseException as exc:
        if not connection.closed and not connection.broken:
            try:
                connection.rollback()
            except BaseException:
                pass
        if write_started and backup is not None and expected_states:
            try:
                if lock_held and not connection.closed and not connection.broken:
                    with connection.cursor() as cursor:
                        restore_skills(
                            cursor,
                            backup,
                            affected_ids=list(TARGET_IDS),
                            expected_states=expected_states,
                        )
                    connection.commit()
                else:
                    lock_held = False
                    _restore(backup, expected_states)
            except BaseException as restore_error:
                exc.add_note(f"定向 Skill 恢复失败：{restore_error}")
        raise
    finally:
        if lock_held and not connection.closed and not connection.broken:
            try:
                with connection.cursor() as cursor:
                    _release_publish_lock(cursor)
            finally:
                connection.close()
        else:
            connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mode", choices=("dry-run", "apply"), default="dry-run")
    parser.add_argument("--backup-root", type=Path, default=BACKUP_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_publish(
        apply=args.mode == "apply",
        backup_root=args.backup_root,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
