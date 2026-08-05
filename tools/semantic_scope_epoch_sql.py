"""Transaction-neutral epoch upsert for psycopg management scripts."""

from __future__ import annotations


SEMANTIC_SCOPE_TYPES = frozenset(
    {
        "PERMISSION",
        "SYSTEM_ROLE",
        "MEMBERSHIP",
        "DATASOURCE_ACCESS",
        "DATASOURCE_ROLE",
        "TRACKING",
        "DATASOURCE_BINDING",
        "SCHEMA",
    }
)

SQLALCHEMY_EPOCH_UPSERT = """
    INSERT INTO semantic_scope_epoch (
        scope_type, tenant_id, datasource_id, subject_id, epoch, update_time
    ) VALUES (
        :scope_type, :tenant_id, :datasource_id, :subject_id, 1, NOW()
    )
    ON CONFLICT (
        scope_type,
        tenant_id,
        (COALESCE(datasource_id, 0)),
        (COALESCE(subject_id, 0))
    ) DO UPDATE SET
        epoch = semantic_scope_epoch.epoch + 1,
        update_time = NOW()
"""


def _scope_parameters(
    *,
    scope_type: str,
    tenant_id: int,
    datasource_id: int | None,
    subject_id: int | None,
) -> dict[str, int | str | None]:
    normalized_scope = str(scope_type or "").strip().upper()
    if normalized_scope not in SEMANTIC_SCOPE_TYPES:
        raise ValueError(f"Unsupported semantic scope type: {scope_type}")
    return {
        "scope_type": normalized_scope,
        "tenant_id": int(tenant_id),
        "datasource_id": int(datasource_id) if datasource_id is not None else None,
        "subject_id": int(subject_id) if subject_id is not None else None,
    }


def bump_semantic_scope_epoch_cursor(
    cursor,
    *,
    scope_type: str,
    tenant_id: int,
    datasource_id: int | None = None,
    subject_id: int | None = None,
) -> None:
    """Use the caller's cursor so authority data and its epoch commit together."""
    parameters = _scope_parameters(
        scope_type=scope_type,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        subject_id=subject_id,
    )
    cursor.execute(
        """
        INSERT INTO semantic_scope_epoch (
            scope_type, tenant_id, datasource_id, subject_id, epoch, update_time
        ) VALUES (%s, %s, %s, %s, 1, NOW())
        ON CONFLICT (
            scope_type,
            tenant_id,
            (COALESCE(datasource_id, 0)),
            (COALESCE(subject_id, 0))
        ) DO UPDATE SET
            epoch = semantic_scope_epoch.epoch + 1,
            update_time = NOW()
        """,
        (
            parameters["scope_type"],
            parameters["tenant_id"],
            parameters["datasource_id"],
            parameters["subject_id"],
        ),
    )


def bump_semantic_scope_epoch_connection(
    connection,
    *,
    scope_type: str,
    tenant_id: int,
    datasource_id: int | None = None,
    subject_id: int | None = None,
) -> None:
    """Run the same upsert through an existing SQLAlchemy transaction."""
    from sqlalchemy import text

    connection.execute(
        text(SQLALCHEMY_EPOCH_UPSERT),
        _scope_parameters(
            scope_type=scope_type,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            subject_id=subject_id,
        ),
    )
