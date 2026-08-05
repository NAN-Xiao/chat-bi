"""发布平台通用的实时事件表与历史事件表选表 Data Skill。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from core_system_db import core_system_db_config, export_postgres_compat_env
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


SKILL_MARKER = (
    "<!-- data-skill-source:platform:realtime-event-table-selection -->"
)
PLATFORM_TENANT_ID = 1
VISIBILITY_SCOPE = "PLATFORM_PUBLIC"
SPECIFIC_DS = False
ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
BACKUP_ROOT = ROOT / ".codex-runtime" / "platform-data-skill-backups"
DB = core_system_db_config()

EVENT_TABLE_SCOPE_PATTERN = r"\b(?:from|join)\s+`?event(?:_realtime)?`?(?=\s|,|$)"
REALTIME_TABLE_PATTERN = r"\b(?:from|join)\s+`?event_realtime`?(?=\s|,|$)"
HISTORY_TABLE_PATTERN = r"\b(?:from|join)\s+`?event`?(?=\s|,|$)"
REALTIME_TRIGGER_TERMS = (
    "今天",
    "当天",
    "今日",
    "实时",
    "当前小时",
    "当前分钟",
    "当前整点",
)
SQL_VALIDATION_RULE = json.dumps(
    {
        "match": list(REALTIME_TRIGGER_TERMS),
        "when_sql_patterns": [EVENT_TABLE_SCOPE_PATTERN],
        "required_sql_patterns": [REALTIME_TABLE_PATTERN],
        "forbidden_sql_patterns": [HISTORY_TABLE_PATTERN],
        "message": (
            "未完成当天的事件类查询必须使用 event_realtime，不能读取完整历史表 event；"
            "请按当前业务日分区重写 SQL。"
        ),
    },
    ensure_ascii=False,
    separators=(",", ":"),
)

SKILL = {
    "name": "平台通用 Data Skill：当天实时事件与完整历史事件选表",
    "description": (
        "当已授权数据源同时存在 event_realtime 与 event 时，"
        "区分今天、当天、今日、实时、当前小时、当前分钟、当前整点与完整历史查询。"
    ),
    "prompt": f"""{SKILL_MARKER}
<!-- platform-foundation-skill:realtime-event-table-selection:v1 -->
<!-- data-skill-requires-tables:["event","event_realtime"] -->
<!-- data-skill-sql-validation:{SQL_VALIDATION_RULE} -->
# 平台通用 Data Skill：当天实时事件与完整历史事件选表

## 适用前提

- 仅当当前会话已明确选择一个已授权数据源，且当前实时 Schema 或工作空间元数据确认同时存在 `event_realtime` 和 `event` 时生效。
- 结构化 SQL 校验仅在生成 SQL 已引用 `event` 或 `event_realtime` 时生效；`user` 等非事件快照表不因“当前”等时间词被强制改表。
- 工作空间 Data Skill、事件字典或字段元数据必须已经提供问题所需的事件语义、主体键和指标字段。本 Skill 只决定选表，不定义业务口径。
- 当前数据源权限、实时 Schema 和工作空间配置优先级高于本 Skill；本 Skill 不得扩大任何数据访问范围。

## 选表规则

- 未完成当日：问题包含“今天”“当天”“今日”“实时”“当前小时”“当前分钟”“当前整点”，或要求今天按分钟、按小时统计时，必须查询 `event_realtime`。
- 反例：“当前”“截至目前”“截至当前”单独出现时，不能触发实时选表；必须结合上述明确的当天或实时触发词判断。
- 完整历史日：问题指定“昨天”“截至昨天”、某个已经结束的日期、完整自然日，或只分析完整历史分区时，查询 `event`。
- 多日趋势：不包含今天的多日趋势查询使用 `event`。
- 包含今天的跨日窗口：已完成历史日期读取 `event`，今天读取 `event_realtime`。只有工作空间口径确认两表字段语义一致且允许合并时，才可使用 `UNION ALL`，并在外层统一聚合，避免重复计算。
- 用户明确指定表名时，仍须验证当前数据源权限、实时 Schema 和工作空间配置。

## 当天日期模板契约

- 当天查询生成非 `metric` 时间序列图时，SQL 必须依据当前 Schema 的日期字段及编码保存成对的 `{{{{dashboard_start_yyyymmdd}}}}` 和 `{{{{dashboard_end_yyyymmdd}}}}` token，不得保存固定 `yyyyMMdd` 日期。
- 同一响应必须返回完整 `date_filter`，其中 `time_field` 和 `date_parameter_type` 来自当前 Schema，`date_expression` 必须是 `{{"version":1,"mode":"preset","preset":"today"}}`。
- 实际业务日期只在执行阶段由看板日期参数渲染；保存和复制图表时继续保留 token 与 `preset=today`。
- 固定语义的 `metric` 图表保持自身日期语义，不返回 `date_filter` 或看板日期 token。

## 禁止静默回退

- 当 `event_realtime` 不存在、无权限、缺少所需字段或工作空间未配置业务口径时，不得静默改查 `event`、第一张事件表或相似表名。
- 必须明确说明缺少的 Schema、权限或工作空间语义配置，并要求用户切换数据源、申请权限或补充配置。
- 不得根据其他数据源、历史问答或相似字段名推断当前数据源的事件名、主体键、金额字段或产品过滤条件。
""",
}


@dataclass(frozen=True)
class TargetSnapshot:
    skill_id: int | None
    row: Mapping[str, Any] | None


@dataclass(frozen=True)
class AppliedState:
    skill_id: int
    created: bool
    expected_name: str
    expected_description: str
    expected_prompt: str


class CommitStateUnknownError(RuntimeError):
    """数据库提交可能已生效，但客户端未收到明确确认。"""

    def __init__(self, state: AppliedState, message: str) -> None:
        super().__init__(message)
        self.state = state


@dataclass(frozen=True)
class PublishReport:
    mode: str
    skill_id: int | None
    updated: bool
    embedding_verified: bool
    backup_path: str | None = None


@dataclass(frozen=True)
class BackupArtifact:
    path: Path
    snapshot: TargetSnapshot


class PublishBackend(Protocol):
    def acquire_lock(self) -> None: ...

    def release_lock(self) -> None: ...

    def inspect(self, marker: str) -> TargetSnapshot: ...

    def backup(self, snapshot: TargetSnapshot) -> Any: ...

    def upsert(
        self,
        skill: Mapping[str, str],
        snapshot: TargetSnapshot,
    ) -> AppliedState: ...

    def refresh_embedding(self, skill_id: int) -> None: ...

    def verify(
        self,
        skill: Mapping[str, str],
        state: AppliedState,
    ) -> None: ...

    def restore(self, backup: Any, state: AppliedState) -> None: ...


def publish_skill(backend: PublishBackend, *, apply: bool) -> PublishReport:
    """只读预检或发布唯一目标 Skill，并在发布失败时恢复目标记录。"""

    if not apply:
        snapshot = backend.inspect(SKILL_MARKER)
        return PublishReport(
            mode="dry-run",
            skill_id=snapshot.skill_id,
            updated=False,
            embedding_verified=False,
        )

    state: AppliedState | None = None
    backup: Any = None
    primary_error: BaseException | None = None
    backend.acquire_lock()
    try:
        snapshot = backend.inspect(SKILL_MARKER)
        backup = backend.backup(snapshot)
        state = backend.upsert(SKILL, snapshot)
        backend.refresh_embedding(state.skill_id)
        backend.verify(SKILL, state)
        return PublishReport(
            mode="apply",
            skill_id=state.skill_id,
            updated=True,
            embedding_verified=True,
            backup_path=(
                str(getattr(backup, "path", backup))
                if backup is not None
                else None
            ),
        )
    except BaseException as exc:
        if state is None and isinstance(exc, CommitStateUnknownError):
            state = exc.state
        if state is not None:
            try:
                backend.restore(backup, state)
            except BaseException as restore_error:
                exc.add_note(f"目标 Skill 恢复失败：{restore_error}")
        primary_error = exc
        raise
    finally:
        try:
            backend.release_lock()
        except BaseException as release_error:
            if primary_error is None:
                raise
            primary_error.add_note(f"发布锁释放失败：{release_error}")


def validate_marker_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    """拒绝重复 marker 以及被错误类型或作用域占用的 marker。"""

    if len(rows) > 1:
        raise RuntimeError("平台实时选表 Skill marker 必须唯一")
    if not rows:
        return
    row = rows[0]
    if row.get("type") != "DATA_SKILL":
        raise RuntimeError("平台实时选表 Skill marker 的 type 必须为 DATA_SKILL")
    if row.get("visibility_scope") != VISIBILITY_SCOPE:
        raise RuntimeError(
            "平台实时选表 Skill marker 的 visibility_scope 必须为 PLATFORM_PUBLIC"
        )


class PsycopgPublishBackend:
    """使用系统 PostgreSQL 和平台 embedding 服务发布单条 Skill。"""

    def __init__(self, *, backup_root: Path = BACKUP_ROOT) -> None:
        self._backup_root = backup_root
        self._connection: psycopg.Connection | None = None

    @staticmethod
    def _connect() -> psycopg.Connection:
        return psycopg.connect(**DB, row_factory=dict_row)

    def _require_connection(self) -> psycopg.Connection:
        if self._connection is None or self._connection.closed:
            raise RuntimeError("平台实时选表 Skill 发布锁尚未获取")
        return self._connection

    def acquire_lock(self) -> None:
        if self._connection is not None:
            raise RuntimeError("平台实时选表 Skill 发布锁已获取")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_lock(hashtext(%s))",
                    (SKILL_MARKER,),
                )
            self._connection = connection
        except BaseException:
            connection.close()
            raise

    def release_lock(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            if not connection.closed and not connection.broken:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtext(%s))",
                        (SKILL_MARKER,),
                    )
        finally:
            connection.close()

    @staticmethod
    def _select_marker_rows(connection: psycopg.Connection) -> list[dict[str, Any]]:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, type, create_time, name, prompt, specific_ds,
                       datasource_ids, description, ai_model_id, create_by,
                       target_scope, active, visibility_scope, tenant_id,
                       visible, embedding, embedding_signature
                FROM custom_prompt
                WHERE position(%s in COALESCE(prompt, '')) > 0
                ORDER BY id
                """,
                (SKILL_MARKER,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def inspect(self, marker: str) -> TargetSnapshot:
        if marker != SKILL_MARKER:
            raise ValueError("拒绝检查未知的平台 Data Skill marker")
        if self._connection is not None:
            rows = self._select_marker_rows(self._require_connection())
        else:
            with self._connect() as connection:
                rows = self._select_marker_rows(connection)
        validate_marker_rows(rows)
        if not rows:
            return TargetSnapshot(skill_id=None, row=None)
        return TargetSnapshot(skill_id=int(rows[0]["id"]), row=rows[0])

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (dt.date, dt.datetime)):
            return value.isoformat()
        return str(value)

    def backup(self, snapshot: TargetSnapshot) -> BackupArtifact:
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_dir = self._backup_root / timestamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        path = backup_dir / "skill.json"
        payload = {
            "marker": SKILL_MARKER,
            "skill_id": snapshot.skill_id,
            "row": dict(snapshot.row) if snapshot.row is not None else None,
            "created_at": timestamp,
        }
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=self._json_default,
            ),
            encoding="utf-8",
        )
        return BackupArtifact(path=path, snapshot=snapshot)

    def upsert(
        self,
        skill: Mapping[str, str],
        snapshot: TargetSnapshot,
    ) -> AppliedState:
        connection = self._require_connection()
        prompt = str(skill["prompt"]).strip()
        now = dt.datetime.now()
        with connection.cursor() as cursor:
            if snapshot.skill_id is None:
                cursor.execute(
                    """
                    INSERT INTO custom_prompt (
                        tenant_id, type, create_time, name, description,
                        target_scope, active, visible, ai_model_id, create_by,
                        visibility_scope, prompt, specific_ds, datasource_ids,
                        embedding, embedding_signature
                    )
                    SELECT
                        %s, 'DATA_SKILL', %s, %s, %s,
                        'ALL', TRUE, TRUE, NULL, NULL,
                        %s, %s, FALSE, %s, NULL, NULL
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM custom_prompt
                        WHERE position(%s in COALESCE(prompt, '')) > 0
                    )
                    RETURNING id
                    """,
                    (
                        PLATFORM_TENANT_ID,
                        now,
                        skill["name"][:255],
                        skill["description"],
                        VISIBILITY_SCOPE,
                        prompt,
                        Jsonb([]),
                        SKILL_MARKER,
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    raise RuntimeError(
                        "平台实时选表 Skill 缺失态 CAS 冲突，拒绝重复插入"
                    )
                skill_id = int(inserted["id"])
                created = True
            else:
                original_prompt = str((snapshot.row or {}).get("prompt") or "")
                cursor.execute(
                    """
                    UPDATE custom_prompt
                    SET tenant_id = %s,
                        name = %s,
                        description = %s,
                        target_scope = 'ALL',
                        active = TRUE,
                        visible = TRUE,
                        ai_model_id = NULL,
                        create_by = NULL,
                        visibility_scope = %s,
                        prompt = %s,
                        specific_ds = FALSE,
                        datasource_ids = %s,
                        embedding = NULL,
                        embedding_signature = NULL
                    WHERE id = %s
                      AND type IS NOT DISTINCT FROM %s
                      AND name IS NOT DISTINCT FROM %s
                      AND description IS NOT DISTINCT FROM %s
                      AND prompt IS NOT DISTINCT FROM %s
                      AND tenant_id IS NOT DISTINCT FROM %s
                      AND target_scope IS NOT DISTINCT FROM %s
                      AND active IS NOT DISTINCT FROM %s
                      AND visible IS NOT DISTINCT FROM %s
                      AND ai_model_id IS NOT DISTINCT FROM %s
                      AND create_by IS NOT DISTINCT FROM %s
                      AND visibility_scope IS NOT DISTINCT FROM %s
                      AND specific_ds IS NOT DISTINCT FROM %s
                      AND datasource_ids IS NOT DISTINCT FROM %s
                      AND embedding IS NOT DISTINCT FROM %s
                      AND embedding_signature IS NOT DISTINCT FROM %s
                    """,
                    (
                        PLATFORM_TENANT_ID,
                        skill["name"][:255],
                        skill["description"],
                        VISIBILITY_SCOPE,
                        prompt,
                        Jsonb([]),
                        snapshot.skill_id,
                        (snapshot.row or {}).get("type"),
                        (snapshot.row or {}).get("name"),
                        (snapshot.row or {}).get("description"),
                        original_prompt,
                        (snapshot.row or {}).get("tenant_id"),
                        (snapshot.row or {}).get("target_scope"),
                        (snapshot.row or {}).get("active"),
                        (snapshot.row or {}).get("visible"),
                        (snapshot.row or {}).get("ai_model_id"),
                        (snapshot.row or {}).get("create_by"),
                        (snapshot.row or {}).get("visibility_scope"),
                        (snapshot.row or {}).get("specific_ds"),
                        (
                            Jsonb((snapshot.row or {}).get("datasource_ids"))
                            if (snapshot.row or {}).get("datasource_ids") is not None
                            else None
                        ),
                        (snapshot.row or {}).get("embedding"),
                        (snapshot.row or {}).get("embedding_signature"),
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("平台实时选表 Skill CAS 更新失败")
                skill_id = snapshot.skill_id
                created = False
        state = AppliedState(
            skill_id=skill_id,
            created=created,
            expected_name=skill["name"][:255],
            expected_description=skill["description"],
            expected_prompt=prompt,
        )
        try:
            connection.commit()
        except BaseException as exc:
            raise CommitStateUnknownError(state, f"Skill 提交状态未知：{exc}") from exc
        return state

    def refresh_embedding(self, skill_id: int) -> None:
        saved = _save_embeddings([skill_id])
        if saved != 1:
            raise RuntimeError(
                f"平台实时选表 Skill embedding 刷新失败：saved={saved}"
            )

    def verify(
        self,
        skill: Mapping[str, str],
        state: AppliedState,
    ) -> None:
        connection = self._require_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, type, name, description, prompt, tenant_id,
                       target_scope, active, visible, visibility_scope,
                       specific_ds, datasource_ids, embedding,
                       embedding_signature
                FROM custom_prompt
                WHERE id = %s
                """,
                (state.skill_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("平台实时选表 Skill 写入后不存在")
        expected = {
            "type": "DATA_SKILL",
            "name": skill["name"][:255],
            "description": skill["description"],
            "prompt": str(skill["prompt"]).strip(),
            "tenant_id": PLATFORM_TENANT_ID,
            "target_scope": "ALL",
            "active": True,
            "visible": True,
            "visibility_scope": VISIBILITY_SCOPE,
            "specific_ds": SPECIFIC_DS,
            "datasource_ids": [],
        }
        mismatches = [key for key, value in expected.items() if row[key] != value]
        if mismatches:
            raise RuntimeError(
                f"平台实时选表 Skill 回读字段不一致：{mismatches}"
            )
        validate_embedding_row(row, model=_embedding_model())

    def restore(self, backup: BackupArtifact, state: AppliedState) -> None:
        original_connection = self._connection
        owns_connection = bool(
            original_connection is None
            or original_connection.closed
            or original_connection.broken
        )
        connection = self._connect() if owns_connection else self._require_connection()
        if not owns_connection:
            try:
                connection.rollback()
            except BaseException:
                connection.close()
                self._connection = None
                connection = self._connect()
                owns_connection = True
        snapshot = backup.snapshot
        try:
            if owns_connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_lock(hashtext(%s))",
                        (SKILL_MARKER,),
                    )
            with connection.cursor() as cursor:
                expected_definition = (
                    state.expected_name,
                    state.expected_description,
                    state.expected_prompt,
                    PLATFORM_TENANT_ID,
                    VISIBILITY_SCOPE,
                    Jsonb([]),
                )
                if state.created:
                    cursor.execute(
                        """
                        DELETE FROM custom_prompt
                        WHERE id = %s
                          AND name IS NOT DISTINCT FROM %s
                          AND description IS NOT DISTINCT FROM %s
                          AND prompt IS NOT DISTINCT FROM %s
                          AND tenant_id = %s
                          AND type = 'DATA_SKILL'
                          AND visibility_scope = %s
                          AND specific_ds = FALSE
                          AND datasource_ids = %s
                          AND target_scope = 'ALL'
                          AND active = TRUE
                          AND visible = TRUE
                          AND ai_model_id IS NULL
                          AND create_by IS NULL
                        """,
                        (state.skill_id, *expected_definition),
                    )
                else:
                    row = dict(snapshot.row or {})
                    cursor.execute(
                        """
                        UPDATE custom_prompt
                        SET type = %s,
                            create_time = %s,
                            name = %s,
                            prompt = %s,
                            specific_ds = %s,
                            datasource_ids = %s,
                            description = %s,
                            ai_model_id = %s,
                            create_by = %s,
                            target_scope = %s,
                            active = %s,
                            visibility_scope = %s,
                            tenant_id = %s,
                            visible = %s,
                            embedding = %s,
                            embedding_signature = %s
                        WHERE id = %s
                          AND name IS NOT DISTINCT FROM %s
                          AND description IS NOT DISTINCT FROM %s
                          AND prompt IS NOT DISTINCT FROM %s
                          AND tenant_id = %s
                          AND type = 'DATA_SKILL'
                          AND visibility_scope = %s
                          AND specific_ds = FALSE
                          AND datasource_ids = %s
                          AND target_scope = 'ALL'
                          AND active = TRUE
                          AND visible = TRUE
                          AND ai_model_id IS NULL
                          AND create_by IS NULL
                        """,
                        (
                            row["type"],
                            row["create_time"],
                            row["name"],
                            row["prompt"],
                            row["specific_ds"],
                            (
                                Jsonb(row["datasource_ids"])
                                if row["datasource_ids"] is not None
                                else None
                            ),
                            row["description"],
                            row["ai_model_id"],
                            row["create_by"],
                            row["target_scope"],
                            row["active"],
                            row["visibility_scope"],
                            row["tenant_id"],
                            row["visible"],
                            row["embedding"],
                            row["embedding_signature"],
                            state.skill_id,
                            *expected_definition,
                        ),
                    )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "平台实时选表 Skill 恢复 CAS 冲突，拒绝覆盖并发修改"
                    )
            connection.commit()
        finally:
            if owns_connection:
                try:
                    if not connection.closed and not connection.broken:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "SELECT pg_advisory_unlock(hashtext(%s))",
                                (SKILL_MARKER,),
                            )
                finally:
                    connection.close()


def _save_embeddings(ids: list[int]) -> int:
    if not ids:
        return 0
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from sqlalchemy.orm import scoped_session, sessionmaker

    from apps.chat.curd.custom_prompt_embedding import (
        save_custom_prompt_skill_embedding,
    )
    from common.core.db import engine

    session_maker = scoped_session(sessionmaker(bind=engine))
    return save_custom_prompt_skill_embedding(
        session_maker,
        ids,
        tenant_id=PLATFORM_TENANT_ID,
    )


def _embedding_model() -> Any:
    export_postgres_compat_env(DB)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from apps.ai_model.embedding import EmbeddingModelCache

    return EmbeddingModelCache.get_model()


def validate_embedding_row(
    row: Mapping[str, Any],
    *,
    model: Any,
    signature_factory: Any | None = None,
) -> None:
    """确认向量可用且签名对应当前完整 Skill 定义。"""

    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from apps.chat.curd.custom_prompt_embedding import (
        embedding_vector_from_json,
        skill_definition_signature,
    )

    vector = embedding_vector_from_json(row.get("embedding"))
    if not vector:
        raise RuntimeError(f"平台实时选表 Skill {row.get('id')} embedding 缺失")
    signature_builder = signature_factory or skill_definition_signature
    expected_signature = signature_builder(
        row.get("name"),
        row.get("description"),
        row.get("prompt"),
        model,
        len(vector),
    )
    if row.get("embedding_signature") != expected_signature:
        raise RuntimeError(
            f"平台实时选表 Skill {row.get('id')} embedding_signature 不一致"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--mode",
        choices=("dry-run", "apply"),
        default="dry-run",
        help="默认只读预检；显式 apply 才发布平台 Skill",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = publish_skill(
        PsycopgPublishBackend(),
        apply=args.mode == "apply",
    )
    print(json.dumps(asdict(report), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
