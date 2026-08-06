"""Build datasource-neutral object projections for existing Data Skills.

The projection is an indexing aid only.  Data Skill selection remains in
``custom_prompt.find_data_skills`` and existing personal/workspace/platform
visibility rules are deliberately left unchanged.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from apps.chat.curd.custom_prompt import CustomPromptTypeEnum
from apps.chat.curd.skill_object_references import (
    SKILL_PROJECTOR_VERSION,
    skill_source_hash,
)
from apps.chat.models.custom_prompt_model import CustomPrompt
from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.object_projection_models import (
    DataSkillObjectProjection,
    DataSkillProjectionStatus,
    SemanticObjectOwnerType,
    SemanticObjectReference,
    SemanticObjectResolution,
)
from apps.knowledge_base.object_references import ProjectedObjectReference
from apps.knowledge_base.object_sql import (
    SqlObjectExtractionError,
    extract_sql_object_paths,
)

_SQL_BLOCK = re.compile(r"```sql\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)
_REQUIRED_TABLES = re.compile(
    r"<!--\s*data-skill-requires-tables\s*:\s*(\[[\s\S]*?\])\s*-->",
    re.IGNORECASE,
)
SKILL_PROJECTION_ERROR = "DATA_SKILL_OBJECT_PROJECTION_FAILED"
skill_projection_source_hash = skill_source_hash


@dataclass(frozen=True)
class SkillProjectionReport:
    skill_id: int
    status: str
    reference_count: int
    source_hash: str
    error_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "status": self.status,
            "reference_count": self.reference_count,
            "source_hash": self.source_hash,
            "error_code": self.error_code,
        }


def rebuild_skill_object_projection(
    session: Session,
    skill_id: int,
    *,
    projector_version: str = SKILL_PROJECTOR_VERSION,
    source_hash: str | None = None,
) -> SkillProjectionReport:
    """Rebuild one Skill projection atomically and idempotently."""
    skill = session.get(CustomPrompt, int(skill_id))
    if source_hash is None and skill is not None:
        source_hash = skill_source_hash(skill)
    source_hash = str(source_hash or "")
    if skill is None or _value(skill.type) != CustomPromptTypeEnum.DATA_SKILL.value:
        _delete_projection(session, int(skill_id))
        session.flush()
        return SkillProjectionReport(int(skill_id), "DELETED", 0, source_hash)

    status = DataSkillProjectionStatus.READY.value
    error_code: str | None = None
    references: list[ProjectedObjectReference] = []
    try:
        references = project_skill_references(skill)
    except SqlObjectExtractionError as exc:
        status = DataSkillProjectionStatus.FAILED.value
        error_code = str(exc.code or SKILL_PROJECTION_ERROR)
    except (ValueError, TypeError, json.JSONDecodeError):
        status = DataSkillProjectionStatus.FAILED.value
        error_code = SKILL_PROJECTION_ERROR

    _delete_references(session, int(skill.id))
    projection = session.exec(
        select(DataSkillObjectProjection).where(
            DataSkillObjectProjection.skill_id == int(skill.id)
        )
    ).first()
    if projection is None:
        projection = DataSkillObjectProjection(
            skill_id=int(skill.id), tenant_id=int(skill.tenant_id)
        )
    projection.tenant_id = int(skill.tenant_id)
    projection.user_id = int(skill.create_by) if skill.create_by is not None else None
    projection.target_scope = _value(skill.target_scope) or None
    projection.source_hash = source_hash
    projection.projector_version = projector_version
    projection.status = status
    projection.reference_count = len(references) if status == DataSkillProjectionStatus.READY.value else 0
    projection.error_code = error_code
    projection.checked_at = datetime.utcnow()
    session.add(projection)
    session.flush()

    if status == DataSkillProjectionStatus.READY.value:
        datasource_id = _single_datasource_id(skill)
        for reference in references:
            session.add(_reference_row(reference, skill=skill, datasource_id=datasource_id))
        session.flush()
    return SkillProjectionReport(int(skill.id), status, len(references), source_hash, error_code)


def rebuild_all_skill_object_projections(
    session: Session,
    *,
    projector_version: str,
    limit: int = 500,
    after_skill_id: int = 0,
) -> list[SkillProjectionReport]:
    """Rebuild a bounded batch; callers can repeat until the batch is empty."""
    statement = (
        select(CustomPrompt)
        .where(
            CustomPrompt.type == CustomPromptTypeEnum.DATA_SKILL.value,
            CustomPrompt.id > max(0, int(after_skill_id)),
        )
        .order_by(CustomPrompt.id)
        .limit(max(1, int(limit)))
    )
    skills = session.exec(statement).all()
    reports = [
        rebuild_skill_object_projection(
            session,
            int(skill.id),
            projector_version=projector_version,
            source_hash=skill_source_hash(skill),
        )
        for skill in skills
    ]
    session.commit()
    return reports


def project_skill_references(skill: Any) -> list[ProjectedObjectReference]:
    """Extract declared tables/fields/JSON paths from a Skill's existing text."""
    prompt = str(getattr(skill, "prompt", "") or "")
    references: list[ProjectedObjectReference] = []
    for table_name in _required_tables(prompt):
        references.append(_projected(DeclaredObjectPath(**_table_path(table_name)), "SKILL_RULE"))
    for sql in _SQL_BLOCK.findall(prompt):
        for path in extract_sql_object_paths([sql], dialect="postgres"):
            references.append(_projected(path, "SQL_AST"))
    result: list[ProjectedObjectReference] = []
    seen: set[tuple[str, str, str]] = set()
    for reference in references:
        key = (reference.declared_key, reference.source_kind, reference.object_type)
        if key not in seen:
            seen.add(key)
            result.append(reference)
    return result


def _projected(path: DeclaredObjectPath, source_kind: str) -> ProjectedObjectReference:
    from apps.knowledge_base.object_references import _declared_key

    return ProjectedObjectReference(
        object_type=path.object_type,
        declared_path=path,
        declared_key=_declared_key(path),
        source_kind=source_kind,
    )


def _reference_row(reference: ProjectedObjectReference, *, skill: Any, datasource_id: int | None) -> SemanticObjectReference:
    path = reference.declared_path
    return SemanticObjectReference(
        tenant_id=int(skill.tenant_id),
        owner_type=SemanticObjectOwnerType.DATA_SKILL.value,
        owner_id=int(skill.id),
        skill_id=int(skill.id),
        object_type=reference.object_type,
        datasource_id=datasource_id,
        catalog_name=path.catalog,
        schema_name=path.schema,
        table_name=path.table,
        field_name=path.field,
        json_path=path.json_path,
        event_name=path.event_name,
        event_property_key=path.event_property_key,
        declared_key=reference.declared_key,
        resolution_status=reference.resolution_status,
        source_kind=reference.source_kind,
        create_time=datetime.utcnow(),
    )


def _delete_references(session: Session, skill_id: int, tenant_id: int | None = None) -> None:
    conditions = [
        SemanticObjectReference.owner_type == SemanticObjectOwnerType.DATA_SKILL.value,
        SemanticObjectReference.skill_id == skill_id,
    ]
    if tenant_id is not None:
        conditions.append(SemanticObjectReference.tenant_id == tenant_id)
    reference_ids = session.exec(
        select(SemanticObjectReference.id).where(*conditions)
    ).all()
    if reference_ids:
        session.exec(
            delete(SemanticObjectResolution).where(
                SemanticObjectResolution.reference_id.in_([int(value) for value in reference_ids])
            )
        )
    session.exec(
        delete(SemanticObjectReference).where(*conditions)
    )


def _delete_projection(session: Session, skill_id: int) -> None:
    _delete_references(session, skill_id)
    projection = session.exec(
        select(DataSkillObjectProjection).where(DataSkillObjectProjection.skill_id == skill_id)
    ).first()
    if projection is not None:
        session.delete(projection)


def _required_tables(prompt: str) -> list[str]:
    match = _REQUIRED_TABLES.search(prompt)
    if match is None:
        return []
    values = json.loads(match.group(1))
    if not isinstance(values, list) or not values:
        raise ValueError("Data Skill required tables 必须是非空数组")
    normalized = [str(value).strip(' `"[]') for value in values]
    if any(not value for value in normalized) or len({value.casefold() for value in normalized}) != len(normalized):
        raise ValueError("Data Skill required tables 包含空值或重复项")
    return normalized


def _table_path(value: str) -> dict[str, Any]:
    parts = [part.strip(' `"[]') for part in str(value).split(".") if part.strip(' `"[]')]
    if len(parts) == 1:
        return {"object_type": "TABLE", "table": parts[0]}
    if len(parts) == 2:
        return {"object_type": "TABLE", "schema": parts[0], "table": parts[1]}
    return {"object_type": "TABLE", "catalog": parts[-3], "schema": parts[-2], "table": parts[-1]}


def _single_datasource_id(skill: Any) -> int | None:
    if not bool(getattr(skill, "specific_ds", False)):
        return None
    raw = getattr(skill, "datasource_ids", None) or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    values = [] if not isinstance(raw, (list, tuple, set)) else raw
    try:
        normalized = sorted({int(value) for value in values})
    except (TypeError, ValueError):
        return None
    return normalized[0] if len(normalized) == 1 else None


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")
