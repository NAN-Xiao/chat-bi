"""Read-only readiness checks for the knowledge-base V2 cutover."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlmodel import Session

from apps.chat.curd.custom_prompt import CustomPromptTypeEnum
from apps.chat.curd.skill_object_references import (
    SKILL_PROJECTOR_VERSION,
    skill_source_hash,
)
from apps.chat.models.custom_prompt_model import CustomPrompt
from apps.knowledge_base.backfill import verify_legacy_v2_parity
from apps.knowledge_base.lifecycle_models import (
    ACTIVE_PUBLISH_JOB_STATUSES,
    KnowledgeBaseVersion,
    KnowledgeMigrationPhase,
    KnowledgePublishJob,
)
from apps.knowledge_base.models import KnowledgeBase
from apps.knowledge_base.object_projection_models import DataSkillObjectProjection
from apps.knowledge_base.repository import KnowledgeMigrationStateRepository
from apps.knowledge_base.storage_probe import publishing_workers_ready


@dataclass(frozen=True)
class CutoverReadinessReport:
    phase: str
    revision: int
    ready_for_cutover: bool
    legacy_backfill_remaining: int
    parity_mismatch_count: int
    mismatch_ids: tuple[int, ...]
    pending_index_count: int
    pending_projection_count: int
    active_publish_job_count: int
    overdue_publish_job_count: int
    storage_probe_ready: bool
    compatible_builds_confirmed: bool
    expected_worker_count: int
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def collect_cutover_readiness(
    session: Session,
    *,
    active_consumers: Iterable[tuple[str, str]] = (),
    compatible_builds_confirmed: bool = False,
    now: datetime | None = None,
) -> CutoverReadinessReport:
    """Collect fail-closed cutover gates without changing database state."""
    resolved_now = now or datetime.utcnow()
    consumers = tuple(
        sorted({(str(worker_id), str(queue_name)) for worker_id, queue_name in active_consumers})
    )
    migration = KnowledgeMigrationStateRepository.get(session)
    phase = _value(migration.phase)

    parity = verify_legacy_v2_parity(session)
    legacy_remaining = parity.remaining
    mismatch_ids = list(parity.mismatch_ids)
    pending_index_count = _pending_index_count(session)
    pending_projection_count = _pending_projection_count(session)
    active_publish_job_count = _active_publish_job_count(session)
    overdue_publish_job_count = _overdue_publish_job_count(session, resolved_now)
    storage_ready = publishing_workers_ready(
        session,
        active_consumers=consumers,
        now=resolved_now,
    )

    failures = []
    if phase not in {
        KnowledgeMigrationPhase.LEGACY_OPEN.value,
        KnowledgeMigrationPhase.CUTOVER_BARRIER.value,
    }:
        failures.append("数据库已经进入 V2_ACTIVE。")
    if legacy_remaining:
        failures.append(f"仍有 {legacy_remaining} 条旧知识未完成 V2 回填。")
    if parity.mismatch_count:
        failures.append(f"旧知识与 V2 版本存在 {parity.mismatch_count} 条不一致。")
    if pending_index_count:
        failures.append(f"仍有 {pending_index_count} 个当前版本索引未就绪。")
    if pending_projection_count:
        failures.append(f"仍有 {pending_projection_count} 个 Data Skill 对象投影未就绪。")
    if active_publish_job_count:
        failures.append(f"仍有 {active_publish_job_count} 个发布任务未结束。")
    if overdue_publish_job_count:
        failures.append(f"仍有 {overdue_publish_job_count} 个发布任务已经逾期。")
    if not consumers:
        failures.append("未提供活动发布 Worker 清单。")
    elif not storage_ready:
        failures.append("活动发布 Worker 尚未全部完成当前存储探针回执。")
    if not compatible_builds_confirmed:
        failures.append("尚未确认全部 API 和 Worker 已支持 phase 屏障协议。")

    ready = not failures
    return CutoverReadinessReport(
        phase=phase,
        revision=int(migration.revision or 0),
        ready_for_cutover=ready,
        legacy_backfill_remaining=legacy_remaining,
        parity_mismatch_count=parity.mismatch_count,
        mismatch_ids=tuple(mismatch_ids[:50]),
        pending_index_count=pending_index_count,
        pending_projection_count=pending_projection_count,
        active_publish_job_count=active_publish_job_count,
        overdue_publish_job_count=overdue_publish_job_count,
        storage_probe_ready=storage_ready,
        compatible_builds_confirmed=compatible_builds_confirmed,
        expected_worker_count=len(consumers),
        code="READY" if ready else "KNOWLEDGE_CUTOVER_NOT_READY",
        message="知识库已满足切换条件。" if ready else " ".join(failures),
    )


def _pending_index_count(session: Session) -> int:
    statement = (
        select(func.count())
        .select_from(KnowledgeBase)
        .join(
            KnowledgeBaseVersion,
            KnowledgeBaseVersion.id == KnowledgeBase.current_version_id,
        )
        .where(
            KnowledgeBase.archived.is_(False),
            KnowledgeBaseVersion.status == "PUBLISHED",
            KnowledgeBaseVersion.index_status != "READY",
        )
    )
    return _count(session, statement)


def _pending_projection_count(session: Session) -> int:
    rows = session.exec(
        select(CustomPrompt, DataSkillObjectProjection)
        .outerjoin(
            DataSkillObjectProjection,
            DataSkillObjectProjection.skill_id == CustomPrompt.id,
        )
        .where(CustomPrompt.type == CustomPromptTypeEnum.DATA_SKILL)
    ).all()
    pending = 0
    for skill, projection in rows:
        if projection is None:
            pending += 1
            continue
        if (
            _value(projection.status) != "READY"
            or projection.projector_version != SKILL_PROJECTOR_VERSION
            or projection.source_hash != skill_source_hash(skill)
        ):
            pending += 1
    return pending


def _active_publish_job_count(session: Session) -> int:
    return _count(
        session,
        select(func.count())
        .select_from(KnowledgePublishJob)
        .where(KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES)),
    )


def _overdue_publish_job_count(session: Session, now: datetime) -> int:
    return _count(
        session,
        select(func.count())
        .select_from(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES),
            KnowledgePublishJob.deadline_at.is_not(None),
            KnowledgePublishJob.deadline_at <= now,
        ),
    )


def _count(session: Session, statement: Any) -> int:
    return int(session.scalar(statement) or 0)


def _value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")
