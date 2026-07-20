# -*- coding: utf-8 -*-
"""定向同步修仙近15日活跃用户付费率看板组件与 Data Skill。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import psycopg

from core_system_db import core_system_db_config
from publish_xiuxian_dashboard_data_skills import (
    _connection_is_usable,
    _default_retrieval_checker,
    acquire_publish_lock,
    backup_and_write_skill_snapshot,
    refresh_and_verify_embeddings,
    release_publish_lock,
    restore_skills,
    utc_timestamp,
    verify_skill_backup,
)
from seed_xiuxian_data_skills import (
    _embedding_model,
    _save_embeddings,
    backup_existing_skills,
    dashboard_sql_block,
    load_skill_states_by_ids,
    upsert_skills,
    validate_prompt_length,
    verify_embeddings,
)
from xiuxian_dashboard_skill_catalog import TOPICS, build_topic_prompt
from xiuxian_dashboard_snapshot import (
    DashboardSnapshot,
    load_recommended_dashboards,
)


TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
DASHBOARD_ID = "afe201c9762c448aa0495f3508c01793"
VIEW_ID = "95d8497afac14f0a90342031fb43bc04"
SKILL_MARKER = "<!-- data-skill-source:xiuxian:dashboard:payer-penetration -->"
TITLE = "近15日活跃用户付费率趋势"
FIELDS = ("日期", "活跃用户数", "活跃付费用户数", "活跃用户付费率")
RETRIEVAL_QUESTION = TITLE
DEFAULT_BACKUP_ROOT = (
    Path(__file__).resolve().parents[1]
    / ".codex-runtime"
    / "xiuxian-active-payer-rate-skill-backups"
)
TARGET_BACKUP_VERSION = 1


class SourceDashboardChangedError(RuntimeError):
    """发布锁内发现目标看板已被并发修改。"""


class RetrievalVerificationError(RuntimeError):
    """更新后的 Data Skill 未按预期召回。"""


class SyncRecoveryError(RuntimeError):
    """同步失败后，看板或 Skill 恢复也失败。"""

    def __init__(self, sync_error: BaseException, recovery_error: BaseException):
        self.sync_error = sync_error
        self.recovery_error = recovery_error
        super().__init__(
            "活跃用户付费率同步失败且恢复失败: "
            f"sync={sync_error!r}; recovery={recovery_error!r}"
        )


@dataclass(frozen=True)
class DashboardSource:
    dashboard_id: str
    dashboard_name: str
    tenant_id: int
    datasource_id: int
    view_id: str
    sql: str
    original_canvas: str
    normalized_canvas: str
    update_time: int
    skill_id: int

    @property
    def guard(self) -> tuple[Any, ...]:
        return (
            self.dashboard_id,
            self.tenant_id,
            self.datasource_id,
            self.original_canvas,
            self.update_time,
            self.skill_id,
        )


@dataclass(frozen=True)
class SyncReport:
    mode: str
    skill_id: int | None
    backup_path: str
    updated: bool
    embedding_verified: bool
    retrieval_verified: bool


def dashboard_source_from_row(
    row: tuple[Any, ...], *, skill_id: int
) -> DashboardSource:
    dashboard_id, name, tenant_id, datasource_id, canvas_value, update_time = row
    if str(dashboard_id) != DASHBOARD_ID:
        raise ValueError(f"目标看板 ID 不匹配: {dashboard_id}")
    if int(tenant_id) != TENANT_ID or int(datasource_id) != DATASOURCE_ID:
        raise ValueError("目标看板不属于修仙工作空间 datasource 6")
    if isinstance(canvas_value, str):
        original_canvas = canvas_value
        try:
            canvas = json.loads(canvas_value)
        except json.JSONDecodeError as exc:
            raise ValueError("目标看板 canvas_view_info 不是有效 JSON") from exc
    elif isinstance(canvas_value, Mapping):
        canvas = copy.deepcopy(dict(canvas_value))
        original_canvas = json.dumps(
            canvas, ensure_ascii=False, separators=(",", ":")
        )
    else:
        raise ValueError("目标看板 canvas_view_info 不是 JSON 对象")
    if not isinstance(canvas, dict):
        raise ValueError("目标看板 canvas_view_info 不是 JSON 对象")
    view = canvas.get(VIEW_ID)
    if not isinstance(view, dict):
        raise ValueError(f"目标组件 {VIEW_ID} 缺失或不是 JSON 对象")
    normalized_view = normalize_target_view(view)
    normalized_canvas_value = copy.deepcopy(canvas)
    normalized_canvas_value[VIEW_ID] = normalized_view
    return DashboardSource(
        dashboard_id=str(dashboard_id),
        dashboard_name=str(name or ""),
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id),
        view_id=VIEW_ID,
        sql=str(normalized_view["sql"]).strip(),
        original_canvas=original_canvas,
        normalized_canvas=json.dumps(
            normalized_canvas_value,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        update_time=int(update_time),
        skill_id=int(skill_id),
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_metadata_path(backup_path: Path) -> Path:
    backup_path = Path(backup_path)
    return backup_path.parent / f"{backup_path.name}.active-payer-source.json"


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def write_target_dashboard_backup(
    source: DashboardSource, backup_root: Path, timestamp: str
) -> Path:
    """原子写入目标看板完整 JSON 和哈希清单。"""

    root = Path(backup_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / timestamp
    if target.exists():
        raise FileExistsError(target)
    staging = root / f".{timestamp}.{os.getpid()}.{uuid4().hex}.staging"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        dashboard_bytes = _json_bytes(
            {"version": TARGET_BACKUP_VERSION, "source": asdict(source)}
        )
        manifest = {
            "version": TARGET_BACKUP_VERSION,
            "tenant_id": TENANT_ID,
            "datasource_id": DATASOURCE_ID,
            "dashboard_id": DASHBOARD_ID,
            "view_id": VIEW_ID,
            "file_sha256": {
                "dashboard.json": hashlib.sha256(dashboard_bytes).hexdigest()
            },
        }
        (staging / "dashboard.json").write_bytes(dashboard_bytes)
        (staging / "manifest.json").write_bytes(_json_bytes(manifest))
        staging.replace(target)
    except BaseException:
        if staging.exists():
            for child in staging.iterdir():
                child.unlink()
            staging.rmdir()
        raise
    return target


def verify_target_dashboard_backup(backup_path: Path) -> DashboardSource:
    """回读目标看板备份并校验作用域、文件集合和 SHA-256。"""

    path = Path(backup_path)
    actual_files = {item.name for item in path.iterdir() if item.is_file()}
    if actual_files != {"dashboard.json", "manifest.json"}:
        raise ValueError("目标看板备份文件集合无效")
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        payload = json.loads((path / "dashboard.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("目标看板备份无法解析") from exc
    if (
        manifest.get("version") != TARGET_BACKUP_VERSION
        or manifest.get("tenant_id") != TENANT_ID
        or manifest.get("datasource_id") != DATASOURCE_ID
        or manifest.get("dashboard_id") != DASHBOARD_ID
        or manifest.get("view_id") != VIEW_ID
    ):
        raise ValueError("目标看板备份作用域无效")
    expected_hash = (manifest.get("file_sha256") or {}).get("dashboard.json")
    actual_hash = hashlib.sha256((path / "dashboard.json").read_bytes()).hexdigest()
    if not expected_hash or actual_hash != expected_hash:
        raise ValueError("目标看板备份文件哈希不一致")
    if payload.get("version") != TARGET_BACKUP_VERSION:
        raise ValueError("目标看板备份版本无效")
    try:
        source = DashboardSource(**payload["source"])
    except (KeyError, TypeError) as exc:
        raise ValueError("目标看板备份结构无效") from exc
    if (
        source.dashboard_id != DASHBOARD_ID
        or source.tenant_id != TENANT_ID
        or source.datasource_id != DATASOURCE_ID
        or source.view_id != VIEW_ID
    ):
        raise ValueError("目标看板备份来源不匹配")
    return source


def validate_target_sql(sql: str) -> None:
    """拒绝不是当前活跃用户与支付用户交集口径的 SQL。"""

    forbidden = ("110000038", "`累计付费率`", "$.paytotal")
    found = [value for value in forbidden if value in sql]
    if found:
        raise ValueError(f"活跃用户付费率 SQL 包含旧口径: {found}")
    required = (
        "INTERVAL 15 DAY",
        "INTERVAL 1 DAY",
        "e.prod = 110000047",
        "UserActive",
        "ServerPayLog",
        "`活跃用户数`",
        "`活跃付费用户数`",
        "`活跃用户付费率`",
    )
    missing = [value for value in required if value not in sql]
    if missing:
        raise ValueError(f"活跃用户付费率 SQL 缺少权威口径: {missing}")


def normalize_target_view(view: Mapping[str, Any]) -> dict[str, Any]:
    """校验权威 SQL，并清理目标组件残留的旧字段和 Builder 状态。"""

    normalized = copy.deepcopy(dict(view))
    if int(normalized.get("datasource") or 0) != DATASOURCE_ID:
        raise ValueError("目标组件不属于修仙 datasource 6")
    sql = str(normalized.get("sql") or "")
    if not sql.strip():
        raise ValueError("目标组件 SQL 为空")
    validate_target_sql(sql)
    source_config = normalized.setdefault("sourceConfig", {})
    if not isinstance(source_config, dict):
        raise ValueError("目标组件 sourceConfig 不是对象")
    sql_config = source_config.setdefault("sql", {})
    if not isinstance(sql_config, dict):
        raise ValueError("目标组件 sourceConfig.sql 不是对象")
    if str(sql_config.get("sql") or "") != sql:
        raise ValueError("目标组件直接 SQL 与 sourceConfig SQL 不一致")

    normalized["fields"] = list(FIELDS)
    chart = normalized.setdefault("chart", {})
    if not isinstance(chart, dict):
        raise ValueError("目标组件 chart 不是对象")
    chart["title"] = TITLE
    chart["xAxis"] = [{"value": "日期"}]
    chart["yAxis"] = [
        {
            "value": "活跃用户付费率",
            "metricType": "ratio",
            "pivotAggregation": "avg",
        }
    ]
    sql_config.pop("builder", None)
    return normalized


def extract_skill_sql(prompt: str) -> str:
    pattern = re.compile(
        rf"<!-- dashboard-sql:{re.escape(VIEW_ID)} -->\s*```sql\s*\n"
        r"(?P<sql>[\s\S]*?)\n```"
    )
    matches = [match.group("sql") for match in pattern.finditer(prompt)]
    if len(matches) != 1:
        raise ValueError("目标 Data Skill 必须包含且只包含一个活跃用户付费率 SQL 块")
    return matches[0]


def validate_skill_source(skill: Mapping[str, str], source: Any) -> None:
    prompt = str(skill.get("prompt") or "")
    if not prompt.startswith(SKILL_MARKER):
        raise ValueError("目标 Data Skill source marker 不匹配")
    if extract_skill_sql(prompt) != str(source.sql).strip():
        raise ValueError("目标 Data Skill SQL 与规范化后的看板 SQL 不一致")
    required = ("活跃用户付费率", "UserActive", "ServerPayLog", "同时", "按天")
    missing = [value for value in required if value not in prompt]
    if missing:
        raise ValueError(f"目标 Data Skill 缺少权威口径: {missing}")


def build_target_skill(dashboards: list[DashboardSnapshot]) -> dict[str, str]:
    """只从 payer-penetration 所属组件生成目标 Skill。"""

    topics = [topic for topic in TOPICS if topic.slug == "payer-penetration"]
    if len(topics) != 1:
        raise RuntimeError("payer-penetration TopicDefinition 必须唯一")
    topic = topics[0]
    wanted = set(topic.view_ids)
    drawers: dict[str, Any] = {}
    for dashboard in dashboards:
        if (
            int(dashboard.tenant_id) != TENANT_ID
            or int(dashboard.datasource) != DATASOURCE_ID
        ):
            raise ValueError(f"看板 {dashboard.id} 不属于修仙 datasource 6")
        for drawer in dashboard.drawers:
            view_id = str(drawer.view_id)
            if view_id not in wanted:
                continue
            if view_id in drawers:
                raise ValueError(f"目标主题组件重复: {view_id}")
            if not drawer.sql.strip():
                raise ValueError(f"目标主题组件 SQL 为空: {view_id}")
            drawers[view_id] = drawer
    missing = sorted(wanted.difference(drawers))
    if missing:
        raise ValueError(f"目标主题组件不完整: {missing}")
    blocks = [
        dashboard_sql_block(view_id, drawers[view_id].sql)
        for view_id in topic.view_ids
    ]
    sections = [
        SKILL_MARKER,
        build_topic_prompt(topic),
        "## 工作空间边界\n仅适用于修仙工作空间 datasource_id=6；不得传播到其他工作空间或数据源。",
        *blocks,
    ]
    prompt = "\n\n".join(sections).strip()
    validate_prompt_length(prompt)
    if len(blocks) > 6:
        raise ValueError("目标 Data Skill SQL 块超过上限")
    return {
        "name": topic.name,
        "description": topic.description,
        "prompt": prompt,
    }


def verify_retrieval_text(text: str) -> None:
    required = ("修仙付费用户、渗透与累计付费", "UserActive", "ServerPayLog", "活跃用户付费率")
    missing = [value for value in required if value not in str(text or "")]
    if missing:
        raise RetrievalVerificationError(f"活跃用户付费率 Skill 召回文本缺少: {missing}")


def sync_active_payer_rate(backend: Any, *, apply: bool) -> SyncReport:
    """执行 dry-run，或在发布锁内同步目标看板和单条 Data Skill。"""

    source = backend.load()
    skill = backend.build(source)
    validate_skill_source(skill, source)
    baseline_hashes = backend.load_other_hashes()
    backup_path = Path(backend.backup(source, skill))
    if not apply:
        return SyncReport(
            mode="dry-run",
            skill_id=int(source.skill_id),
            backup_path=str(backup_path),
            updated=False,
            embedding_verified=False,
            retrieval_verified=False,
        )

    wrote = False
    failure: BaseException | None = None
    skill_id: int | None = None
    backend.lock()
    try:
        backend.assert_unchanged(source)
        backend.update_dashboard(source)
        wrote = True
        skill_id = int(backend.upsert_skill(skill))
        backend.refresh_embedding(skill_id)
        backend.verify(source, skill, skill_id)
        backend.verify_other_hashes(baseline_hashes)
        verify_retrieval_text(backend.retrieve(RETRIEVAL_QUESTION))
    except BaseException as exc:
        failure = exc
        if wrote:
            try:
                backend.restore()
            except BaseException as recovery_error:
                combined = SyncRecoveryError(exc, recovery_error)
                failure = combined
                raise combined from recovery_error
        raise
    finally:
        try:
            backend.unlock()
        except BaseException as unlock_error:
            if failure is None:
                raise
            failure.add_note(f"发布锁释放失败: {unlock_error!r}")

    return SyncReport(
        mode="apply",
        skill_id=skill_id,
        backup_path=str(backup_path),
        updated=True,
        embedding_verified=True,
        retrieval_verified=True,
    )


class PsycopgBackend:
    """使用现有修仙发布能力实现单组件、单 Skill 的安全同步。"""

    def __init__(self, *, backup_root: Path = DEFAULT_BACKUP_ROOT):
        self.backup_root = Path(backup_root)
        self._write_connection: Any | None = None
        self._source: DashboardSource | None = None
        self._dashboards: list[DashboardSnapshot] | None = None
        self._target_backup: dict[str, list[dict[str, Any]]] | None = None
        self._expected_skill_states: dict[int, dict[str, Any]] = {}
        self._applied_update_time: int | None = None

    @staticmethod
    def _connection() -> Any:
        return psycopg.connect(**core_system_db_config())

    def _active_or_new_connection(self) -> tuple[Any, bool]:
        if self._write_connection is not None:
            return self._write_connection, False
        return self._connection(), True

    @staticmethod
    def _load_source_on(connection: Any) -> DashboardSource:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, tenant_id, datasource, canvas_view_info, update_time
                FROM core_dashboard
                WHERE id = %s
                  AND tenant_id = %s
                  AND datasource = %s
                  AND node_type = 'leaf'
                  AND COALESCE(delete_flag, 0) = 0
                """,
                (DASHBOARD_ID, TENANT_ID, DATASOURCE_ID),
            )
            dashboard_rows = cur.fetchall()
            cur.execute(
                """
                SELECT id
                FROM custom_prompt
                WHERE tenant_id = %s
                  AND type = 'DATA_SKILL'
                  AND specific_ds = TRUE
                  AND datasource_ids = %s::jsonb
                  AND position(%s in COALESCE(prompt, '')) > 0
                ORDER BY id
                """,
                (TENANT_ID, json.dumps([DATASOURCE_ID]), SKILL_MARKER),
            )
            skill_rows = cur.fetchall()
        if len(dashboard_rows) != 1:
            raise RuntimeError(f"目标看板记录必须唯一，实际 {len(dashboard_rows)}")
        if len(skill_rows) != 1:
            raise RuntimeError(f"目标 Data Skill marker 必须唯一，实际 {len(skill_rows)}")
        return dashboard_source_from_row(
            dashboard_rows[0], skill_id=int(skill_rows[0][0])
        )

    def load(self) -> DashboardSource:
        connection, should_close = self._active_or_new_connection()
        try:
            source = self._load_source_on(connection)
            if should_close:
                self._source = source
            return source
        finally:
            if should_close:
                connection.close()

    def build(self, source: DashboardSource) -> dict[str, str]:
        with self._connection() as connection:
            dashboards = load_recommended_dashboards(connection)
        normalized: list[DashboardSnapshot] = []
        found = 0
        for dashboard in dashboards:
            if dashboard.id != DASHBOARD_ID:
                normalized.append(dashboard)
                continue
            found += 1
            normalized.append(
                DashboardSnapshot.from_row(
                    (
                        dashboard.id,
                        dashboard.name,
                        dashboard.tenant_id,
                        dashboard.datasource,
                        source.normalized_canvas,
                    )
                )
            )
        if found != 1:
            raise RuntimeError(f"推荐看板快照中的目标看板必须唯一，实际 {found}")
        skill = build_target_skill(normalized)
        self._dashboards = dashboards
        validate_skill_source(skill, source)
        return skill

    def load_other_hashes(self) -> dict[int, tuple[str, str]]:
        source = self._source
        if source is None:
            raise RuntimeError("读取 Skill 哈希前必须先加载目标来源")
        with self._connection() as connection, connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, prompt, embedding_signature
                FROM custom_prompt
                WHERE tenant_id = %s
                  AND type = 'DATA_SKILL'
                  AND specific_ds = TRUE
                  AND datasource_ids = %s::jsonb
                  AND position('data-skill-source:xiuxian:' in COALESCE(prompt, '')) > 0
                ORDER BY id
                """,
                (TENANT_ID, json.dumps([DATASOURCE_ID])),
            )
            rows = cur.fetchall()
        markers = [str(row[1] or "").splitlines()[0].strip() for row in rows]
        if len(rows) != 13 or len(set(markers)) != 13 or "" in markers:
            raise RuntimeError("线上修仙 Data Skill 必须包含 13 个唯一 marker")
        ids = {int(row[0]) for row in rows}
        if source.skill_id not in ids:
            raise RuntimeError("目标 Data Skill ID 不在修仙 Skill 目录中")
        return {
            int(skill_id): (_sha256_text(str(prompt or "")), str(signature or ""))
            for skill_id, prompt, signature in rows
            if int(skill_id) != source.skill_id
        }

    def backup(self, source: DashboardSource, skill: Mapping[str, str]) -> Path:
        if self._dashboards is None:
            raise RuntimeError("写备份前必须先生成目标 Data Skill")
        backup_path = write_target_dashboard_backup(
            source,
            self.backup_root,
            f"{utc_timestamp()}-{uuid4().hex[:8]}",
        )
        if verify_target_dashboard_backup(backup_path) != source:
            raise RuntimeError("目标看板恢复工件验签不一致")
        with self._connection() as connection:
            captured = backup_and_write_skill_snapshot(
                connection, [skill], backup_path
            )
        verified = verify_skill_backup(backup_path)
        if captured != verified:
            raise RuntimeError("目标 Data Skill 恢复工件验签不一致")
        skills = list(verified.get("skills", ()))
        if len(skills) != 1 or int(skills[0].get("id")) != source.skill_id:
            raise RuntimeError("目标 Data Skill 备份记录不唯一或 ID 已变化")
        self._target_backup = verified
        source_metadata_path(backup_path).write_text(
            json.dumps(asdict(source), ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return backup_path

    def lock(self) -> None:
        if self._write_connection is not None:
            raise RuntimeError("发布锁连接已存在")
        self._write_connection = self._connection()
        acquire_publish_lock(self._write_connection)

    def unlock(self) -> None:
        if self._write_connection is None:
            return
        connection = self._write_connection
        self._write_connection = None
        try:
            if _connection_is_usable(connection):
                release_publish_lock(connection)
        finally:
            connection.close()

    def _require_write_connection(self) -> Any:
        if self._write_connection is None:
            raise RuntimeError("定向写入必须持有修仙发布锁")
        return self._write_connection

    def assert_unchanged(self, source: DashboardSource) -> None:
        current = self._load_source_on(self._require_write_connection())
        if current.guard != source.guard:
            raise SourceDashboardChangedError(
                "目标看板或 Data Skill 在备份后发生变化，拒绝覆盖"
            )

    def update_dashboard(self, source: DashboardSource) -> None:
        connection = self._require_write_connection()
        update_time = max(int(time.time()), source.update_time + 1)
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    UPDATE core_dashboard
                    SET canvas_view_info = %s,
                        update_time = %s
                    WHERE id = %s
                      AND tenant_id = %s
                      AND datasource = %s
                      AND canvas_view_info = %s
                      AND update_time = %s
                    """,
                    (
                        source.normalized_canvas,
                        update_time,
                        source.dashboard_id,
                        source.tenant_id,
                        source.datasource_id,
                        source.original_canvas,
                        source.update_time,
                    ),
                )
                if cur.rowcount != 1:
                    raise SourceDashboardChangedError("目标看板 CAS 更新失败")
            connection.commit()
            self._applied_update_time = update_time
        except BaseException:
            connection.rollback()
            raise

    def upsert_skill(self, skill: dict[str, str]) -> int:
        connection = self._require_write_connection()
        source = self._source
        if source is None or self._target_backup is None:
            raise RuntimeError("更新 Skill 前必须完成来源读取和备份")
        try:
            with connection.cursor() as cur:
                current = backup_existing_skills(cur, [SKILL_MARKER])
                if current != self._target_backup:
                    raise SourceDashboardChangedError(
                        "目标 Data Skill 在备份后发生变化，拒绝覆盖"
                    )
                ids = upsert_skills(cur, [skill])
                if ids != [source.skill_id]:
                    raise RuntimeError(f"定向更新返回了意外 Skill ID: {ids}")
                states = load_skill_states_by_ids(cur, ids)
                if set(states) != {source.skill_id}:
                    raise RuntimeError("无法构造目标 Data Skill 的发布期望态")
                self._expected_skill_states = states
            connection.commit()
            return source.skill_id
        except BaseException:
            connection.rollback()
            raise

    def refresh_embedding(self, skill_id: int) -> None:
        refresh_and_verify_embeddings(
            self._require_write_connection(),
            [skill_id],
            _save_embeddings,
        )

    def verify(
        self,
        source: DashboardSource,
        skill: Mapping[str, str],
        skill_id: int,
    ) -> None:
        if self._applied_update_time is None:
            raise RuntimeError("回读前缺少看板更新时间")
        connection = self._require_write_connection()
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT canvas_view_info, update_time
                FROM core_dashboard
                WHERE id = %s AND tenant_id = %s AND datasource = %s
                """,
                (source.dashboard_id, source.tenant_id, source.datasource_id),
            )
            rows = cur.fetchall()
            if len(rows) != 1 or rows[0] != (
                source.normalized_canvas,
                self._applied_update_time,
            ):
                raise RuntimeError("目标看板写入后回读不一致")
            cur.execute(
                """
                SELECT prompt
                FROM custom_prompt
                WHERE id = %s
                  AND tenant_id = %s
                  AND type = 'DATA_SKILL'
                  AND specific_ds = TRUE
                  AND datasource_ids = %s::jsonb
                """,
                (skill_id, TENANT_ID, json.dumps([DATASOURCE_ID])),
            )
            skill_rows = cur.fetchall()
            if len(skill_rows) != 1 or skill_rows[0][0] != str(skill["prompt"]).strip():
                raise RuntimeError("目标 Data Skill 写入后回读不一致")
            verify_embeddings(cur, [skill_id], model=_embedding_model())
        validate_skill_source(skill, source)

    def verify_other_hashes(
        self, baseline: Mapping[int, tuple[str, str]]
    ) -> None:
        current = self.load_other_hashes()
        if dict(current) != dict(baseline):
            raise RuntimeError("目标之外的 12 条修仙 Data Skill 发生变化")

    @staticmethod
    def retrieve(question: str) -> str:
        return _default_retrieval_checker(question)

    def restore(self) -> None:
        source = self._source
        backup = self._target_backup
        applied_update_time = self._applied_update_time
        if source is None or backup is None or applied_update_time is None:
            raise RuntimeError("恢复所需的看板或 Skill 快照不完整")
        original_lock_held = bool(
            self._write_connection is not None
            and _connection_is_usable(self._write_connection)
        )
        recovery = self._connection()
        recovery_lock_held = False
        try:
            if not original_lock_held:
                acquire_publish_lock(recovery)
                recovery_lock_held = True
            with recovery.cursor() as cur:
                if self._expected_skill_states:
                    restore_skills(
                        cur,
                        backup,
                        affected_ids=[source.skill_id],
                        expected_states=self._expected_skill_states,
                    )
                cur.execute(
                    """
                    UPDATE core_dashboard
                    SET canvas_view_info = %s,
                        update_time = %s
                    WHERE id = %s
                      AND tenant_id = %s
                      AND datasource = %s
                      AND canvas_view_info = %s
                      AND update_time = %s
                    """,
                    (
                        source.original_canvas,
                        source.update_time,
                        source.dashboard_id,
                        source.tenant_id,
                        source.datasource_id,
                        source.normalized_canvas,
                        applied_update_time,
                    ),
                )
                if cur.rowcount != 1:
                    raise SourceDashboardChangedError(
                        "目标看板恢复 CAS 失败，已保留并发修改"
                    )
            recovery.commit()
        except BaseException:
            recovery.rollback()
            raise
        finally:
            try:
                if recovery_lock_held and _connection_is_usable(recovery):
                    release_publish_lock(recovery)
            finally:
                recovery.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="默认只读校验并备份；显式 apply 才更新目标看板与 Data Skill",
    )
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = sync_active_payer_rate(
        PsycopgBackend(backup_root=args.backup_root),
        apply=args.mode == "apply",
    )
    print(
        json.dumps(
            {
                "mode": report.mode,
                "skill_id": report.skill_id,
                "updated": report.updated,
                "embedding_verified": report.embedding_verified,
                "retrieval_verified": report.retrieval_verified,
                "backup_path": str(Path(report.backup_path).resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
