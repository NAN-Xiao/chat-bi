"""Monotonic epochs for semantic authority changes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlmodel import Session

from apps.datasource.models.semantic_scope import SemanticScopeEpoch, SemanticScopeType


@dataclass(frozen=True)
class SemanticScopeCoordinate:
    scope_type: SemanticScopeType
    tenant_id: int
    datasource_id: int | None = None
    subject_id: int | None = None


def _coordinate(
    *,
    coordinate: SemanticScopeCoordinate | None,
    scope_type: SemanticScopeType | str | None,
    tenant_id: int | None,
    datasource_id: int | None,
    subject_id: int | None,
) -> SemanticScopeCoordinate:
    if coordinate is not None:
        return coordinate
    if scope_type is None or tenant_id is None:
        raise ValueError("scope_type and tenant_id are required")
    return SemanticScopeCoordinate(
        scope_type=SemanticScopeType(scope_type),
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id) if datasource_id is not None else None,
        subject_id=int(subject_id) if subject_id is not None else None,
    )


def bump_semantic_scope_epoch(
    session: Session,
    *,
    coordinate: SemanticScopeCoordinate | None = None,
    scope_type: SemanticScopeType | str | None = None,
    tenant_id: int | None = None,
    datasource_id: int | None = None,
    subject_id: int | None = None,
) -> int:
    """Increment one authority epoch without committing the caller's transaction."""
    target = _coordinate(
        coordinate=coordinate,
        scope_type=scope_type,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        subject_id=subject_id,
    )
    dialect_name = session.get_bind().dialect.name
    if dialect_name != "postgresql":
        return _locked_increment(session, target)

    statement = postgresql_insert(SemanticScopeEpoch).values(
        scope_type=target.scope_type.value,
        tenant_id=target.tenant_id,
        datasource_id=target.datasource_id,
        subject_id=target.subject_id,
        epoch=1,
        update_time=func.now(),
    )
    statement = statement.on_conflict_do_update(
        index_elements=(
            SemanticScopeEpoch.scope_type,
            SemanticScopeEpoch.tenant_id,
            text("COALESCE(datasource_id, 0)"),
            text("COALESCE(subject_id, 0)"),
        ),
        set_={
            "epoch": SemanticScopeEpoch.epoch + 1,
            "update_time": func.now(),
        },
    ).returning(SemanticScopeEpoch.epoch)
    return int(session.execute(statement).scalar_one())


def _locked_increment(
    session: Session,
    coordinate: SemanticScopeCoordinate,
) -> int:
    statement = select(SemanticScopeEpoch).where(
        SemanticScopeEpoch.scope_type == coordinate.scope_type,
        SemanticScopeEpoch.tenant_id == coordinate.tenant_id,
        SemanticScopeEpoch.datasource_id.is_(coordinate.datasource_id)
        if coordinate.datasource_id is None
        else SemanticScopeEpoch.datasource_id == coordinate.datasource_id,
        SemanticScopeEpoch.subject_id.is_(coordinate.subject_id)
        if coordinate.subject_id is None
        else SemanticScopeEpoch.subject_id == coordinate.subject_id,
    ).with_for_update()
    row = session.execute(statement).scalar_one_or_none()
    if row is None:
        row = SemanticScopeEpoch(
            scope_type=coordinate.scope_type,
            tenant_id=coordinate.tenant_id,
            datasource_id=coordinate.datasource_id,
            subject_id=coordinate.subject_id,
            epoch=1,
            update_time=datetime.now(),
        )
    else:
        row.epoch = int(row.epoch) + 1
        row.update_time = datetime.now()
    session.add(row)
    session.flush()
    return int(row.epoch)


def load_semantic_scope_epochs(
    session: Session,
    *,
    coordinates: Iterable[SemanticScopeCoordinate],
) -> dict[SemanticScopeCoordinate, int]:
    """Load exact epoch coordinates, returning zero for scopes never written."""
    requested = tuple(dict.fromkeys(coordinates))
    if not requested:
        return {}
    conditions = [
        and_(
            SemanticScopeEpoch.scope_type == coordinate.scope_type,
            SemanticScopeEpoch.tenant_id == coordinate.tenant_id,
            SemanticScopeEpoch.datasource_id.is_(coordinate.datasource_id)
            if coordinate.datasource_id is None
            else SemanticScopeEpoch.datasource_id == coordinate.datasource_id,
            SemanticScopeEpoch.subject_id.is_(coordinate.subject_id)
            if coordinate.subject_id is None
            else SemanticScopeEpoch.subject_id == coordinate.subject_id,
        )
        for coordinate in requested
    ]
    rows = session.execute(select(SemanticScopeEpoch).where(or_(*conditions))).scalars().all()
    values = {
        SemanticScopeCoordinate(
            scope_type=SemanticScopeType(row.scope_type),
            tenant_id=int(row.tenant_id),
            datasource_id=int(row.datasource_id) if row.datasource_id is not None else None,
            subject_id=int(row.subject_id) if row.subject_id is not None else None,
        ): int(row.epoch)
        for row in rows
    }
    return {coordinate: values.get(coordinate, 0) for coordinate in requested}
