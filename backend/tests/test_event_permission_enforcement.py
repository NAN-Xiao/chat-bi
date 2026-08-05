"""Event permissions inherited from physical and tracking authorities."""

from __future__ import annotations

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
