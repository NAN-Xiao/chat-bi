from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import inspect
from sqlmodel import Session, select

from apps.system.models.tenant import TenantSchemaFieldModel, TenantSchemaTableModel
from common.utils.snowflake import snowflake
from common.utils.time import get_timestamp


@dataclass(frozen=True)
class SchemaFieldKey:
    table_name: str
    field_name: str


def clean_schema_comment(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _table_names(values: Iterable[str | None]) -> list[str]:
    names = sorted({str(value).strip() for value in values if str(value or "").strip()})
    return names


def _field_keys(values: Iterable[SchemaFieldKey]) -> list[SchemaFieldKey]:
    keys = {
        SchemaFieldKey(str(value.table_name).strip(), str(value.field_name).strip())
        for value in values
        if str(value.table_name or "").strip() and str(value.field_name or "").strip()
    }
    return sorted(keys, key=lambda item: (item.table_name, item.field_name))


def _has_table(session: Session, table_name: str) -> bool:
    try:
        return inspect(session.connection()).has_table(table_name)
    except Exception:
        return False


def _supports_schema_tables(session: Session) -> bool:
    return _has_table(session, TenantSchemaTableModel.__tablename__)


def _supports_schema_fields(session: Session) -> bool:
    return _has_table(session, TenantSchemaFieldModel.__tablename__)


def table_comment_map(session: Session, tenant_id: int | None, table_names: Iterable[str | None]) -> dict[str, str]:
    names = _table_names(table_names)
    if tenant_id is None or not names or not _supports_schema_tables(session):
        return {}
    rows = session.exec(
        select(TenantSchemaTableModel).where(
            TenantSchemaTableModel.tenant_id == int(tenant_id),
            TenantSchemaTableModel.table_name.in_(names),
        )
    ).all()
    return {
        row.table_name: clean_schema_comment(row.table_comment) or ""
        for row in rows
    }


def field_comment_map(
        session: Session,
        tenant_id: int | None,
        field_keys: Iterable[SchemaFieldKey],
) -> dict[tuple[str, str], str]:
    keys = _field_keys(field_keys)
    if tenant_id is None or not keys or not _supports_schema_fields(session):
        return {}
    table_names = sorted({key.table_name for key in keys})
    field_names = sorted({key.field_name for key in keys})
    rows = session.exec(
        select(TenantSchemaFieldModel).where(
            TenantSchemaFieldModel.tenant_id == int(tenant_id),
            TenantSchemaFieldModel.table_name.in_(table_names),
            TenantSchemaFieldModel.field_name.in_(field_names),
        )
    ).all()
    allowed = {(key.table_name, key.field_name) for key in keys}
    return {
        (row.table_name, row.field_name): clean_schema_comment(row.field_comment) or ""
        for row in rows
        if (row.table_name, row.field_name) in allowed
    }


def get_table_comment(
        session: Session,
        tenant_id: int | None,
        table_name: str | None,
        fallback: str | None = None,
) -> str:
    table_name = (table_name or "").strip()
    if tenant_id is None or not table_name or not _supports_schema_tables(session):
        return fallback or ""
    row = session.exec(
        select(TenantSchemaTableModel).where(
            TenantSchemaTableModel.tenant_id == int(tenant_id),
            TenantSchemaTableModel.table_name == table_name,
        )
    ).first()
    if row is None:
        return fallback or ""
    return clean_schema_comment(row.table_comment) or ""


def get_field_comment(
        session: Session,
        tenant_id: int | None,
        table_name: str | None,
        field_name: str | None,
        fallback: str | None = None,
) -> str:
    table_name = (table_name or "").strip()
    field_name = (field_name or "").strip()
    if tenant_id is None or not table_name or not field_name or not _supports_schema_fields(session):
        return fallback or ""
    row = session.exec(
        select(TenantSchemaFieldModel).where(
            TenantSchemaFieldModel.tenant_id == int(tenant_id),
            TenantSchemaFieldModel.table_name == table_name,
            TenantSchemaFieldModel.field_name == field_name,
        )
    ).first()
    if row is None:
        return fallback or ""
    return clean_schema_comment(row.field_comment) or ""


def save_table_comment(
        session: Session,
        tenant_id: int | None,
        table_name: str,
        comment: str | None,
        *,
        current_user_id: int | None = None,
) -> None:
    table_name = (table_name or "").strip()
    if tenant_id is None or not table_name or not _supports_schema_tables(session):
        return
    now = get_timestamp()
    row = session.exec(
        select(TenantSchemaTableModel).where(
            TenantSchemaTableModel.tenant_id == int(tenant_id),
            TenantSchemaTableModel.table_name == table_name,
        )
    ).first()
    if row is None:
        row = TenantSchemaTableModel(
            id=snowflake.generate_id(),
            tenant_id=int(tenant_id),
            table_name=table_name,
            create_by=current_user_id,
            create_time=now,
        )
    row.table_comment = clean_schema_comment(comment)
    row.update_by = current_user_id
    row.update_time = now
    session.add(row)


def save_field_comment(
        session: Session,
        tenant_id: int | None,
        table_name: str,
        field_name: str,
        comment: str | None,
        *,
        current_user_id: int | None = None,
) -> None:
    table_name = (table_name or "").strip()
    field_name = (field_name or "").strip()
    if tenant_id is None or not table_name or not field_name or not _supports_schema_fields(session):
        return
    now = get_timestamp()
    row = session.exec(
        select(TenantSchemaFieldModel).where(
            TenantSchemaFieldModel.tenant_id == int(tenant_id),
            TenantSchemaFieldModel.table_name == table_name,
            TenantSchemaFieldModel.field_name == field_name,
        )
    ).first()
    if row is None:
        row = TenantSchemaFieldModel(
            id=snowflake.generate_id(),
            tenant_id=int(tenant_id),
            table_name=table_name,
            field_name=field_name,
            create_by=current_user_id,
            create_time=now,
        )
    row.field_comment = clean_schema_comment(comment)
    row.update_by = current_user_id
    row.update_time = now
    session.add(row)
