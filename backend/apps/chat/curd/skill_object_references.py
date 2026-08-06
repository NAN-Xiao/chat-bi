"""Resolve Data Skill object projections against the current permission snapshot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from apps.chat.models.custom_prompt_model import CustomPrompt
from apps.knowledge_base.object_projection_models import (
    DataSkillObjectProjection,
    DataSkillProjectionStatus,
    SemanticObjectReference,
    SemanticObjectResolution,
)

SKILL_PROJECTOR_VERSION = "data-skill-object-v1"


def skill_source_hash(skill: Any) -> str:
    """Return the deterministic source identity used by the projection worker."""
    payload = {
        "name": str(getattr(skill, "name", "") or ""),
        "description": str(getattr(skill, "description", "") or ""),
        "prompt": str(getattr(skill, "prompt", "") or ""),
        "target_scope": str(getattr(skill, "target_scope", "") or ""),
        "visibility_scope": str(getattr(skill, "visibility_scope", "") or ""),
        "specific_ds": bool(getattr(skill, "specific_ds", False)),
        "datasource_ids": getattr(skill, "datasource_ids", None) or [],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def eligible_data_skill_ids(
    session: Session,
    *,
    snapshot: Any,
    skill_ids: Collection[int] | None = None,
    projector_version: str = SKILL_PROJECTOR_VERSION,
) -> frozenset[int]:
    """Return only ready, source-current and permission-authorized Skill IDs.

    A ready projection with no references is valid.  Any unresolved, stale or
    cross-datasource reference makes the Skill unavailable for this request.
    The function intentionally does not choose or rank Skills; that remains the
    responsibility of ``find_data_skills``.
    """
    requested = {int(value) for value in (skill_ids or ())}
    statement = select(DataSkillObjectProjection, CustomPrompt).join(
        CustomPrompt, CustomPrompt.id == DataSkillObjectProjection.skill_id
    ).where(
        DataSkillObjectProjection.status == DataSkillProjectionStatus.READY.value,
        DataSkillObjectProjection.projector_version == projector_version,
    )
    if requested:
        statement = statement.where(DataSkillObjectProjection.skill_id.in_(requested))

    result: set[int] = set()
    for projection, skill in session.exec(statement).all():
        skill_id = int(projection.skill_id)
        if requested and skill_id not in requested:
            continue
        if projection.source_hash != skill_source_hash(skill):
            continue
        references = session.exec(
            select(SemanticObjectReference).where(
                SemanticObjectReference.owner_type == "DATA_SKILL",
                SemanticObjectReference.skill_id == skill_id,
                SemanticObjectReference.tenant_id == int(projection.tenant_id),
            )
        ).all()
        if not references:
            if int(projection.reference_count or 0) == 0:
                result.add(skill_id)
            continue
        if not _references_allowed(session, references, snapshot):
            continue
        result.add(skill_id)
    return frozenset(result)


def _references_allowed(session: Session, references: list[Any], snapshot: Any) -> bool:
    for reference in references:
        if reference.datasource_id is not None and int(reference.datasource_id) != int(snapshot.datasource_id):
            return False
        resolution = session.exec(
            select(SemanticObjectResolution).where(
                SemanticObjectResolution.reference_id == int(reference.id),
                SemanticObjectResolution.tenant_id == int(snapshot.tenant_id),
                SemanticObjectResolution.datasource_id == int(snapshot.datasource_id),
                SemanticObjectResolution.physical_schema_hash == snapshot.schema_hash,
                SemanticObjectResolution.status == "RESOLVED",
            )
        ).first()
        if resolution is None or not resolution.canonical_key:
            return False
        if resolution.canonical_key not in snapshot.allowed_object_keys:
            return False
        if resolution.canonical_key in snapshot.denied_object_keys:
            return False
    return True
