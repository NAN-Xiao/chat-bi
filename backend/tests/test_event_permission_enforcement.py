"""Event permissions inherited from physical and tracking authorities."""

from __future__ import annotations

import pytest

from metadata_permission_fixtures import (
    insert_rule,
    metadata_permission_session,
    workspace_user,
)
from sqlalchemy import text

from apps.datasource.crud.metadata_permission import MetadataPermissionService
from apps.datasource.crud.semantic_object_key import (
    SemanticObjectKey,
    canonical_object_key,
)
from apps.datasource.models.datasource import CoreDatasource


def _event_key() -> str:
    return canonical_object_key(
        SemanticObjectKey(
            object_type="EVENT",
            tenant_id=2,
            datasource_id=9,
            catalog="",
            schema="public",
            table="events",
            field="event_name",
            event_name="purchase",
        )
    )


def _property_key() -> str:
    return canonical_object_key(
        SemanticObjectKey(
            object_type="EVENT_PROPERTY",
            tenant_id=2,
            datasource_id=9,
            catalog="",
            schema="public",
            table="events",
            field="payload",
            json_path="$.amount",
            event_name="purchase",
            event_property_key="amount",
        )
    )


def _table_key() -> str:
    return canonical_object_key(
        SemanticObjectKey(
            object_type="TABLE",
            tenant_id=2,
            datasource_id=9,
            catalog="",
            schema="public",
            table="events",
        )
    )


def _field_key(field: str) -> str:
    return canonical_object_key(
        SemanticObjectKey(
            object_type="FIELD",
            tenant_id=2,
            datasource_id=9,
            catalog="",
            schema="public",
            table="events",
            field=field,
        )
    )


def _json_path_key(field: str, json_path: str) -> str:
    return canonical_object_key(
        SemanticObjectKey(
            object_type="JSON_PATH",
            tenant_id=2,
            datasource_id=9,
            catalog="",
            schema="public",
            table="events",
            field=field,
            json_path=json_path,
        )
    )


def _snapshot(*, allowed: set[str], denied: set[str] | None = None):
    from apps.datasource.crud.permission_scope import PermissionScopeSnapshot

    return PermissionScopeSnapshot(
        tenant_id=2,
        user_id=7,
        datasource_id=9,
        permission_version="test-version",
        schema_hash="a" * 64,
        allowed_object_keys=frozenset(allowed),
        denied_object_keys=frozenset(denied or set()),
        row_constraints_hash="b" * 64,
    )


def test_physical_permissions_do_not_require_tracking_configuration(tmp_path) -> None:
    with metadata_permission_session(tmp_path / "without-tracking.db") as session:
        session.execute(
            text(
                "DELETE FROM sys_tenant_tracking_config "
                "WHERE tenant_id = 2 AND datasource_id = 9"
            )
        )
        session.commit()
        insert_rule(
            session,
            permission_id=10,
            permission_type="table",
            table_id=90,
            targets=[],
        )

        denied = MetadataPermissionService.resolve_denied_objects(
            session=session,
            current_user=workspace_user(),
            tenant_id=2,
            datasource_id=9,
        )

    assert denied == frozenset({_table_key()})


def test_event_and_properties_inherit_denied_event_name_field(tmp_path) -> None:
    with metadata_permission_session(tmp_path / "event-field.db") as session:
        insert_rule(
            session,
            permission_id=11,
            permission_type="column",
            table_id=90,
            targets=[{"field_id": 901, "field_name": "event_name", "enable": False}],
        )

        denied = MetadataPermissionService.resolve_denied_objects(
            session=session,
            current_user=workspace_user(),
            tenant_id=2,
            datasource_id=9,
        )

    assert _event_key() in denied
    assert _property_key() in denied


def test_event_property_inherits_denied_json_path_without_denying_event(tmp_path) -> None:
    with metadata_permission_session(tmp_path / "event-json.db") as session:
        insert_rule(
            session,
            permission_id=12,
            permission_type="column",
            table_id=90,
            targets=[
                {
                    "field_id": "tracking:events:payload.amount",
                    "field_name": "payload.amount",
                    "source_field": "payload",
                    "json_path": "$.amount",
                    "is_json_subfield": True,
                    "enable": False,
                }
            ],
        )

        denied = MetadataPermissionService.resolve_denied_objects(
            session=session,
            current_user=workspace_user(),
            tenant_id=2,
            datasource_id=9,
        )

    assert _event_key() not in denied
    assert _property_key() in denied


def test_tracking_field_reload_uses_physical_display_name_not_normalized_table_key(tmp_path) -> None:
    with metadata_permission_session(tmp_path / "mixed-case-table.db") as session:
        session.execute(text("UPDATE core_datasource SET type = 'mysql' WHERE id = 9"))
        session.execute(
            text(
                "UPDATE core_table SET table_name = 'Events' "
                "WHERE id = 90"
            )
        )
        session.execute(
            text(
                "UPDATE sys_tenant_tracking_config SET default_event_table = 'Events' "
                "WHERE tenant_id = 2 AND datasource_id = 9"
            )
        )
        session.execute(
            text(
                "UPDATE sys_tenant_tracking_field SET table_name = 'Events' "
                "WHERE tenant_id = 2 AND datasource_id = 9"
            )
        )
        session.commit()
        insert_rule(
            session,
            permission_id=13,
            permission_type="column",
            table_id=90,
            targets=[
                {
                    "field_id": "tracking:Events:payload.amount",
                    "field_name": "payload.amount",
                    "source_field": "payload",
                    "json_path": "$.amount",
                    "is_json_subfield": True,
                    "enable": False,
                }
            ],
        )

        denied = MetadataPermissionService.resolve_denied_objects(
            session=session,
            current_user=workspace_user(),
            tenant_id=2,
            datasource_id=9,
        )

    assert _property_key() in denied


def test_authorized_public_events_does_not_authorize_archive_orders(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "full-key-scope.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None
        with pytest.raises(SqlPermissionScopeError, match="无权限表"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT * FROM archive.orders",
                snapshot=_snapshot(allowed={_table_key()}),
            )


def test_snapshot_scope_rejects_star_when_table_has_denied_field(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-star-denied-field.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match=r"SELECT \*"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT * FROM public.events",
                snapshot=_snapshot(
                    allowed={_table_key(), _field_key("event_name")},
                    denied={_field_key("payload")},
                ),
            )


def test_snapshot_scope_rejects_denied_static_json_path(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-static-json.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="JSON"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT payload ->> 'amount' FROM public.events",
                snapshot=_snapshot(
                    allowed={
                        _table_key(),
                        _field_key("event_name"),
                        _field_key("payload"),
                    },
                    denied={_json_path_key("payload", "$.amount")},
                ),
            )


def test_snapshot_scope_rejects_star_when_table_has_denied_json_path(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-star-denied-json.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="SELECT \\*"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT * FROM public.events",
                snapshot=_snapshot(
                    allowed={_table_key(), _field_key("event_name"), _field_key("payload")},
                    denied={_json_path_key("payload", "$.amount")},
                ),
            )


def test_snapshot_scope_does_not_treat_source_column_as_output_alias(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-output-alias.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="无权限字段"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT payload AS payload FROM public.events",
                snapshot=_snapshot(
                    allowed={_table_key(), _field_key("event_name")},
                    denied={_field_key("payload")},
                ),
            )


def test_snapshot_scope_rejects_json_access_when_source_field_is_denied(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-json-denied-field.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="无权限字段"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT payload ->> 'amount' FROM public.events",
                snapshot=_snapshot(
                    allowed={_table_key(), _field_key("event_name")},
                    denied={_field_key("payload")},
                ),
            )


def test_snapshot_scope_rejects_dynamic_json_path_when_source_is_restricted(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-dynamic-json.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="动态 JSON"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql="SELECT payload ->> event_name FROM public.events",
                snapshot=_snapshot(
                    allowed={
                        _table_key(),
                        _field_key("event_name"),
                        _field_key("payload"),
                    },
                    denied={_json_path_key("payload", "$.amount")},
                ),
            )


def test_snapshot_scope_rejects_denied_json_path_through_derived_table(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import validate_sql_object_scope

    with metadata_permission_session(tmp_path / "snapshot-nested-json.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="JSON"):
            validate_sql_object_scope(
                session=session,
                datasource=datasource,
                sql=(
                    "SELECT t.payload ->> 'amount' "
                    "FROM (SELECT payload FROM public.events) AS t"
                ),
                snapshot=_snapshot(
                    allowed={
                        _table_key(),
                        _field_key("event_name"),
                        _field_key("payload"),
                    },
                    denied={_json_path_key("payload", "$.amount")},
                ),
            )


def test_compile_event_constraints_filters_denied_event(tmp_path) -> None:
    from apps.datasource.crud.sql_permission import compile_event_constraints

    with metadata_permission_session(tmp_path / "denied-event-filter.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        rewritten = compile_event_constraints(
            session=session,
            datasource=datasource,
            sql="SELECT event_name FROM public.events",
            snapshot=_snapshot(
                allowed={
                    _table_key(),
                    _field_key("event_name"),
                    _field_key("payload"),
                    _event_key(),
                },
                denied={_event_key()},
            ),
        )

    assert "purchase" in rewritten
    assert "WHERE" in rewritten.upper()


def test_compile_event_constraints_rejects_outer_join(tmp_path) -> None:
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError
    from apps.datasource.crud.sql_permission import compile_event_constraints

    with metadata_permission_session(tmp_path / "denied-event-outer-join.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        with pytest.raises(SqlPermissionScopeError, match="无法安全"):
            compile_event_constraints(
                session=session,
                datasource=datasource,
                sql=(
                    "SELECT e.event_name FROM public.events AS e "
                    "LEFT JOIN public.events AS related ON related.event_name = e.event_name"
                ),
                snapshot=_snapshot(
                    allowed={
                        _table_key(),
                        _field_key("event_name"),
                        _field_key("payload"),
                        _event_key(),
                    },
                    denied={_event_key()},
                ),
            )


def test_compile_event_constraints_ignores_unrelated_aggregate(tmp_path) -> None:
    from apps.datasource.crud.sql_permission import compile_event_constraints

    with metadata_permission_session(tmp_path / "denied-event-unrelated-aggregate.db") as session:
        datasource = session.get(CoreDatasource, 9)
        assert datasource is not None

        assert compile_event_constraints(
            session=session,
            datasource=datasource,
            sql="SELECT COUNT(*) FROM archive.orders",
            snapshot=_snapshot(allowed={_table_key(), _event_key()}, denied={_event_key()}),
        ) == "SELECT COUNT(*) FROM archive.orders"
