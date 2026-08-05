"""Metadata permission validation and stable-key behavior."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from metadata_permission_fixtures import (
    insert_rule,
    metadata_permission_session,
    workspace_user,
)
from sqlalchemy import text

from apps.datasource.api import permission as permission_api
from apps.datasource.crud.metadata_permission import (
    MetadataPermissionService,
    MetadataPermissionValidationError,
)
from apps.datasource.crud.semantic_object_key import (
    SemanticObjectKey,
    canonical_object_key,
)


def _expected_key(object_type: str, **values) -> str:
    return canonical_object_key(
        SemanticObjectKey(
            object_type=object_type,
            tenant_id=2,
            datasource_id=9,
            **values,
        )
    )


@pytest.mark.parametrize("permission_type", ["schema", "event", "event_property"])
def test_permission_api_accepts_metadata_types(permission_type: str) -> None:
    assert permission_api._normalize_permission_type(permission_type) == permission_type


def test_permission_api_returns_chinese_message_for_unsupported_type() -> None:
    with pytest.raises(HTTPException) as exc:
        permission_api._normalize_permission_type("unknown")

    assert exc.value.status_code == 400
    assert exc.value.detail == {
        "code": "PERMISSION_TYPE_UNSUPPORTED",
        "message": "不支持的权限类型。",
    }


def test_platform_metadata_rule_uses_datasource_bound_workspace_for_canonical_key(tmp_path) -> None:
    platform_admin = SimpleNamespace(
        id=1,
        tenant_id=1,
        tenant_role=None,
        system_role="system_admin",
        isAdmin=True,
        workspace_status="platform_admin",
    )
    payload = {
        "tenant_id": 1,
        "scope": "PLATFORM",
        "permissions": [
            {
                "type": "event",
                "ds_id": 9,
                "target": {"event_name": "purchase"},
            }
        ],
    }
    with metadata_permission_session(tmp_path / "platform-rule.db") as session:
        permission_api._validate_permission_rule_scope(session, platform_admin, payload)

    normalized = payload["permissions"][0]
    assert normalized["table_id"] is None
    assert "target" not in normalized
    assert normalized["permissions"][0]["canonical_key"] == _expected_key(
        "EVENT",
        catalog="",
        schema="public",
        table="events",
        field="event_name",
        event_name="purchase",
    )


def test_metadata_rule_save_persists_normalized_type_and_server_target(tmp_path) -> None:
    payload = {
        "name": "event deny",
        "permissions": [
            {
                "name": "purchase deny",
                "type": "EVENT",
                "ds_id": 9,
                "target": {
                    "event_name": "purchase",
                    "display_name": "client label",
                    "canonical_key": "client-key",
                },
            }
        ],
        "users": ["7"],
    }
    with metadata_permission_session(tmp_path / "save-rule.db") as session:
        saved = asyncio.run(
            permission_api.save_rule.__wrapped__(
                session,
                workspace_user(role="admin"),
                payload,
            )
        )

    permission = saved["permissions"][0]
    assert permission["type"] == "event"
    assert permission["table_id"] is None
    assert permission["permissions"] == [
        {
            "object_type": "EVENT",
            "event_name": "purchase",
            "canonical_key": _expected_key(
                "EVENT",
                catalog="",
                schema="public",
                table="events",
                field="event_name",
                event_name="purchase",
            ),
            "enable": False,
        }
    ]


@pytest.mark.parametrize(
    ("permission_type", "target", "expected_fields"),
    [
        (
            "schema",
            {"catalog_key": "", "schema_key": "public"},
            {"object_type": "SCHEMA", "catalog_key": "", "schema_key": "public"},
        ),
        (
            "event",
            {"event_name": "purchase"},
            {"object_type": "EVENT", "event_name": "purchase"},
        ),
        (
            "event_property",
            {"event_name": "purchase", "event_property_key": "amount"},
            {
                "object_type": "EVENT_PROPERTY",
                "event_name": "purchase",
                "event_property_key": "amount",
            },
        ),
    ],
)
def test_metadata_targets_are_reloaded_and_client_authority_is_discarded(
    tmp_path,
    permission_type: str,
    target: dict,
    expected_fields: dict,
) -> None:
    submitted = {
        **target,
        "tenant_id": 88,
        "datasource_id": 77,
        "display_name": "client supplied label",
        "canonical_key": "client-supplied-key",
    }
    with metadata_permission_session(tmp_path / "metadata.db") as session:
        normalized = MetadataPermissionService.normalize_permission_targets(
            session=session,
            current_user=workspace_user(role="admin"),
            tenant_id=2,
            datasource_id=9,
            permission_type=permission_type,
            targets=[submitted],
        )

    assert len(normalized) == 1
    assert normalized[0].items() >= expected_fields.items()
    assert normalized[0]["canonical_key"] != "client-supplied-key"
    assert normalized[0]["enable"] is False
    assert "tenant_id" not in normalized[0]
    assert "datasource_id" not in normalized[0]
    assert "display_name" not in normalized[0]


@pytest.mark.parametrize(
    ("permission_type", "target"),
    [
        ("schema", {"catalog_key": "", "schema_key": "foreign_schema"}),
        ("event", {"event_name": "foreign_event"}),
        (
            "event_property",
            {"event_name": "foreign_event", "event_property_key": "foreign_property"},
        ),
    ],
)
def test_metadata_permission_rejects_foreign_workspace_object_without_leaking_name(
    tmp_path,
    permission_type: str,
    target: dict,
) -> None:
    with metadata_permission_session(tmp_path / "foreign.db") as session:
        with pytest.raises(MetadataPermissionValidationError) as exc:
            MetadataPermissionService.normalize_permission_targets(
                session=session,
                current_user=workspace_user(role="admin"),
                tenant_id=2,
                datasource_id=9,
                permission_type=permission_type,
                targets=[target],
            )

    assert exc.value.code == "METADATA_PERMISSION_TARGET_NOT_FOUND"
    assert exc.value.message == "权限对象不存在或不属于当前工作空间。"
    assert "foreign" not in exc.value.message.lower()


def test_duplicate_event_name_in_workspace_tracking_is_rejected(tmp_path) -> None:
    duplicate_mappings = [
        {"event_name": "purchase", "event_table": "events_a"},
        {"event_name": "purchase", "event_table": "events_b"},
    ]
    with metadata_permission_session(tmp_path / "duplicate.db") as session:
        session.execute(
            text(
                "UPDATE sys_tenant_tracking_config SET event_name_mappings = :mappings "
                "WHERE tenant_id = 2 AND datasource_id = 9"
            ),
            {"mappings": json.dumps(duplicate_mappings)},
        )
        session.commit()

        with pytest.raises(MetadataPermissionValidationError) as exc:
            MetadataPermissionService.normalize_permission_targets(
                session=session,
                current_user=workspace_user(role="admin"),
                tenant_id=2,
                datasource_id=9,
                permission_type="event",
                targets=[{"event_name": "purchase"}],
            )

    assert exc.value.code == "METADATA_EVENT_DUPLICATE"
    assert exc.value.message == "当前工作空间存在重复事件名称，请先修正事件字典。"


def test_resolve_denied_objects_rebuilds_all_metadata_canonical_keys(tmp_path) -> None:
    with metadata_permission_session(tmp_path / "resolve.db") as session:
        insert_rule(
            session,
            permission_id=1,
            permission_type="schema",
            targets=[{"schema_key": "archive", "catalog_key": "", "canonical_key": "spoof"}],
        )
        insert_rule(
            session,
            permission_id=2,
            permission_type="event",
            targets=[{"event_name": "purchase", "canonical_key": "spoof"}],
        )
        insert_rule(
            session,
            permission_id=3,
            permission_type="event_property",
            targets=[
                {
                    "event_name": "purchase",
                    "event_property_key": "amount",
                    "canonical_key": "spoof",
                }
            ],
        )

        denied = MetadataPermissionService.resolve_denied_objects(
            session=session,
            current_user=workspace_user(),
            tenant_id=2,
            datasource_id=9,
        )

    assert denied == frozenset(
        {
            _expected_key("SCHEMA", catalog="", schema="archive"),
            _expected_key(
                "EVENT",
                catalog="",
                schema="public",
                table="events",
                field="event_name",
                event_name="purchase",
            ),
            _expected_key(
                "EVENT_PROPERTY",
                catalog="",
                schema="public",
                table="events",
                field="payload",
                json_path="$.amount",
                event_name="purchase",
                event_property_key="amount",
            ),
        }
    )
