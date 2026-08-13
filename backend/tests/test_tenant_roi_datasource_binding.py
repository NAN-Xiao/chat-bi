import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from apps.roi_dashboard import service as roi_service
from apps.system.api import tenant as tenant_api
from apps.system.schemas.tenant_schema import TenantCreator, TenantDTO, TenantEditor


def make_tenant() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        public_id="WS11",
        name="测试",
        plan="default",
        status=1,
        subscription_status="active",
        billing_mode="manual",
        trial_end_time=None,
        current_period_end_time=None,
        contract_no=None,
        billing_contact=None,
        billing_email=None,
        subscription_note=None,
        roi_project_id="ROI-11",
        create_time=0,
        update_time=0,
    )


def make_platform_admin() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        account="admin",
        name="平台管理员",
        system_role="system_admin",
        tenant_id=None,
    )


class FakeTenantSession:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.tenant = make_tenant()
        self.fail_commit = fail_commit
        self.commit_count = 0
        self.rollback_count = 0
        self.events: list[str] = []

    def get(self, _model, _record_id):
        return self.tenant

    def commit(self) -> None:
        self.commit_count += 1
        self.events.append("commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.rollback_count += 1
        self.events.append("rollback")


def test_tenant_schemas_accept_roi_project_id_text() -> None:
    assert TenantCreator(name="测试").roi_datasource_id is None
    assert TenantEditor(name="测试").roi_datasource_id is None
    assert TenantCreator(name="测试", roi_datasource_id=101).roi_datasource_id == 101
    assert TenantEditor(name="测试", roi_datasource_id="101").roi_datasource_id == 101
    assert TenantCreator(name="测试", roi_project_id=" 001A ").roi_project_id == "001A"
    assert TenantEditor(name="测试", roi_project_id="ROI-001").roi_project_id == "ROI-001"


@pytest.mark.parametrize("schema_type", [TenantCreator, TenantEditor])
@pytest.mark.parametrize("roi_project_id", ["", "   ", 123, "x" * 129])
def test_tenant_schemas_reject_invalid_roi_project_id(schema_type, roi_project_id) -> None:
    with pytest.raises(ValidationError):
        schema_type(name="测试", roi_project_id=roi_project_id)


def test_add_tenant_requires_roi_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeTenantSession()
    monkeypatch.setattr(tenant_api, "_require_platform_admin", lambda *_args: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(tenant_api.add_tenant(session, make_platform_admin(), TenantCreator(name="测试")))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "项目 ID 为必填项"
    assert session.commit_count == 0


def test_edit_tenant_requires_roi_project_id() -> None:
    session = FakeTenantSession()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            tenant_api.edit_tenant(
                session,
                make_platform_admin(),
                11,
                TenantEditor(name="测试"),
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "项目 ID 为必填项"
    assert session.commit_count == 0
    assert session.rollback_count == 0


@pytest.mark.parametrize("schema_type", [TenantCreator, TenantEditor])
@pytest.mark.parametrize(
    "roi_datasource_id",
    [True, False, 0, -1, "", "-1", "abc", " 101", "１２３", 1.5],
)
def test_tenant_schemas_reject_invalid_roi_datasource_before_coercion(
    schema_type,
    roi_datasource_id,
) -> None:
    with pytest.raises(ValidationError):
        schema_type(name="测试", roi_datasource_id=roi_datasource_id)


def test_tenant_dto_contains_roi_datasource() -> None:
    dto = tenant_api._tenant_dto(
        make_tenant(),
        roi_datasource={
            "roi_datasource_id": 101,
            "roi_datasource_name": "ROI 数据源",
        },
        include_operations=True,
    )

    assert dto.roi_datasource_id == 101
    assert dto.roi_datasource_name == "ROI 数据源"
    assert dto.roi_project_id == "ROI-11"


def test_tenant_roi_datasource_map_uses_workspace_config_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[int]] = []
    monkeypatch.setattr(
        tenant_api,
        "list_roi_workspace_config_rows",
        lambda _session, tenant_ids: calls.append(tenant_ids)
        or [(11, 101, "ROI 数据源")],
    )

    result = tenant_api._tenant_roi_datasource_map(object(), [11, 12])

    assert calls == [[11, 12]]
    assert result == {
        11: {
            "roi_datasource_id": 101,
            "roi_datasource_name": "ROI 数据源",
        }
    }


def test_tenant_list_and_admin_dto_include_roi_datasource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant = make_tenant()
    monkeypatch.setattr(tenant_api, "ensure_tenant_public_id", lambda *_args: None)
    monkeypatch.setattr(tenant_api, "_tenant_owner_map", lambda *_args: {})
    monkeypatch.setattr(tenant_api, "_tenant_bound_datasource_map", lambda *_args: {})
    monkeypatch.setattr(tenant_api, "_tenant_bound_external_mcp_map", lambda *_args: {})
    monkeypatch.setattr(tenant_api, "_tenant_member_stats_map", lambda *_args: {})
    monkeypatch.setattr(
        tenant_api,
        "_tenant_roi_datasource_map",
        lambda *_args: {
            11: {
                "roi_datasource_id": 101,
                "roi_datasource_name": "ROI 数据源",
            }
        },
    )

    listed = tenant_api._tenant_dto_list(object(), [(tenant, "owner", None)])
    admin = tenant_api._tenant_admin_dto(object(), tenant)

    assert listed[0].roi_datasource_id == 101
    assert listed[0].roi_datasource_name == "ROI 数据源"
    assert admin.roi_datasource_id == 101
    assert admin.roi_datasource_name == "ROI 数据源"
    assert listed[0].roi_project_id == "ROI-11"
    assert admin.roi_project_id == "ROI-11"


def test_current_tenant_includes_roi_datasource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession()
    current = SimpleNamespace(id=11, name="测试", role="owner")
    monkeypatch.setattr(tenant_api, "ensure_tenant_public_id", lambda *_args: None)
    monkeypatch.setattr(tenant_api, "_tenant_bound_datasource_map", lambda *_args: {})
    monkeypatch.setattr(tenant_api, "_tenant_bound_external_mcp_map", lambda *_args: {})
    monkeypatch.setattr(
        tenant_api,
        "_tenant_roi_datasource_map",
        lambda *_args: {
            11: {
                "roi_datasource_id": 101,
                "roi_datasource_name": "ROI 数据源",
            }
        },
    )

    dto = asyncio.run(tenant_api.current_tenant(session, current))

    assert dto.roi_datasource_id == 101
    assert dto.roi_datasource_name == "ROI 数据源"
    assert dto.roi_project_id == "ROI-11"


def _patch_tenant_return_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tenant_api, "_tenant_bound_datasource_map", lambda *_args: {})
    monkeypatch.setattr(tenant_api, "_tenant_bound_external_mcp_map", lambda *_args: {})
    monkeypatch.setattr(
        tenant_api,
        "_tenant_roi_datasource_map",
        lambda *_args: {
            11: {
                "roi_datasource_id": 301,
                "roi_datasource_name": "ROI 数据源",
            }
        },
    )


def test_add_tenant_saves_bindings_and_audit_in_one_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession()
    user = make_platform_admin()
    binding_calls: list[tuple[str, object, bool]] = []
    monkeypatch.setattr(tenant_api, "_resolve_owner_user", lambda *_args: None)

    def fake_create_tenant(*_args, **kwargs):
        session.tenant.roi_project_id = kwargs["roi_project_id"]
        return session.tenant

    monkeypatch.setattr(tenant_api, "create_tenant", fake_create_tenant)
    monkeypatch.setattr(
        tenant_api,
        "bind_tenant_to_datasource",
        lambda *_args, **kwargs: binding_calls.append(
            ("datasource", _args[3], kwargs["commit"])
        ),
    )
    monkeypatch.setattr(
        tenant_api,
        "bind_tenant_to_external_mcp",
        lambda *_args, **kwargs: binding_calls.append(("mcp", _args[3], kwargs["commit"])),
    )
    monkeypatch.setattr(
        tenant_api,
        "set_roi_datasource_for_tenant",
        lambda *_args, **kwargs: binding_calls.append(
            ("roi", kwargs["datasource_id"], kwargs["commit"])
        ),
    )
    monkeypatch.setattr(
        tenant_api,
        "_write_tenant_audit",
        lambda *_args, **_kwargs: session.events.append("audit"),
    )
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: session.events.append(f"invalidate:{tenant_id}"),
    )
    _patch_tenant_return_maps(monkeypatch)

    dto = asyncio.run(
        tenant_api.add_tenant(
            session,
            user,
            TenantCreator(
                name="测试",
                datasource_id=101,
                external_mcp_server_id=201,
                roi_datasource_id=301,
                roi_project_id="ROI-301",
            ),
        )
    )

    assert binding_calls == [
        ("datasource", 101, False),
        ("mcp", 201, False),
        ("roi", 301, False),
    ]
    assert session.events == ["audit", "commit", "invalidate:11"]
    assert session.commit_count == 1
    assert dto.roi_datasource_id == 301
    assert dto.roi_datasource_name == "ROI 数据源"
    assert dto.roi_project_id == "ROI-301"


def test_add_tenant_without_roi_datasource_does_not_create_config_or_invalidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession()
    user = make_platform_admin()
    roi_calls: list[object] = []
    monkeypatch.setattr(tenant_api, "_resolve_owner_user", lambda *_args: None)
    monkeypatch.setattr(tenant_api, "create_tenant", lambda *_args, **_kwargs: session.tenant)
    monkeypatch.setattr(tenant_api, "set_roi_datasource_for_tenant", lambda *args, **kwargs: roi_calls.append((args, kwargs)))
    monkeypatch.setattr(tenant_api, "_write_tenant_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: roi_calls.append(("invalidate", tenant_id)),
    )
    _patch_tenant_return_maps(monkeypatch)

    asyncio.run(
        tenant_api.add_tenant(
            session,
            user,
            TenantCreator(name="测试", roi_project_id="ROI-TEST"),
        )
    )

    assert roi_calls == []
    assert session.commit_count == 1


def test_add_tenant_with_explicit_null_roi_only_invalidates_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession()
    user = make_platform_admin()
    roi_calls: list[object] = []
    monkeypatch.setattr(tenant_api, "_resolve_owner_user", lambda *_args: None)
    monkeypatch.setattr(tenant_api, "create_tenant", lambda *_args, **_kwargs: session.tenant)
    monkeypatch.setattr(
        tenant_api,
        "set_roi_datasource_for_tenant",
        lambda *args, **kwargs: roi_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(tenant_api, "_write_tenant_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: session.events.append(f"invalidate:{tenant_id}"),
    )
    _patch_tenant_return_maps(monkeypatch)

    asyncio.run(
        tenant_api.add_tenant(
            session,
            user,
            TenantCreator(name="测试", roi_datasource_id=None, roi_project_id="ROI-TEST"),
        )
    )

    assert roi_calls == []
    assert session.events == ["commit", "invalidate:11"]


def test_edit_tenant_saves_all_bindings_in_one_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession()
    user = make_platform_admin()
    calls: list[tuple[str, object, bool]] = []
    audit_remarks: list[str] = []
    monkeypatch.setattr(tenant_api, "update_tenant", lambda *args, **kwargs: session.tenant)
    monkeypatch.setattr(
        tenant_api,
        "bind_tenant_to_datasource",
        lambda *_args, **kwargs: calls.append(("datasource", _args[3], kwargs["commit"])),
    )
    monkeypatch.setattr(
        tenant_api,
        "bind_tenant_to_external_mcp",
        lambda *_args, **kwargs: calls.append(("mcp", _args[3], kwargs["commit"])),
    )
    monkeypatch.setattr(
        tenant_api,
        "set_roi_datasource_for_tenant",
        lambda *_args, **kwargs: calls.append(("roi", kwargs["datasource_id"], kwargs["commit"])),
    )
    monkeypatch.setattr(
        tenant_api,
        "_write_tenant_audit",
        lambda *_args, **kwargs: (
            audit_remarks.append(kwargs["remark"]),
            session.events.append("audit"),
        ),
    )
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: session.events.append(f"invalidate:{tenant_id}"),
    )
    monkeypatch.setattr(
        tenant_api,
        "_tenant_admin_dto",
        lambda *_args, **_kwargs: TenantDTO(
            id=11,
            public_id="WS11",
            name="测试",
            roi_datasource_id=301,
            roi_datasource_name="ROI 数据源",
        ),
    )

    dto = asyncio.run(
        tenant_api.edit_tenant(
            session,
            user,
            11,
            TenantEditor(
                name="测试",
                datasource_id=101,
                external_mcp_server_id=201,
                roi_datasource_id=301,
                roi_project_id="ROI-301",
            ),
        )
    )

    assert calls == [
        ("datasource", 101, False),
        ("mcp", 201, False),
        ("roi", 301, False),
    ]
    assert session.events == ["audit", "commit", "invalidate:11"]
    assert session.commit_count == 1
    assert "roi_datasource_id=301" in audit_remarks[0]
    assert "roi_project_id=ROI-301" in audit_remarks[0]
    assert dto.roi_datasource_id == 301


def test_edit_tenant_distinguishes_omitted_roi_field_from_explicit_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_platform_admin()
    roi_values: list[int | None] = []
    invalidated_tenants: list[int] = []
    monkeypatch.setattr(tenant_api, "update_tenant", lambda *args, **kwargs: make_tenant())
    monkeypatch.setattr(
        tenant_api,
        "set_roi_datasource_for_tenant",
        lambda *_args, **kwargs: roi_values.append(kwargs["datasource_id"]),
    )
    monkeypatch.setattr(tenant_api, "_write_tenant_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: invalidated_tenants.append(tenant_id),
    )
    monkeypatch.setattr(
        tenant_api,
        "_tenant_admin_dto",
        lambda *_args, **_kwargs: TenantDTO(id=11, public_id="WS11", name="测试"),
    )

    omitted_session = FakeTenantSession()
    asyncio.run(
        tenant_api.edit_tenant(
            omitted_session,
            user,
            11,
            TenantEditor(name="测试", roi_project_id="ROI-11"),
        )
    )
    explicit_null_session = FakeTenantSession()
    asyncio.run(
        tenant_api.edit_tenant(
            explicit_null_session,
            user,
            11,
            TenantEditor(name="测试", roi_datasource_id=None, roi_project_id="ROI-11"),
        )
    )

    assert roi_values == [None]
    assert invalidated_tenants == [11]
    assert omitted_session.commit_count == 1
    assert explicit_null_session.commit_count == 1


def test_edit_tenant_rolls_back_and_keeps_cache_on_binding_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession()
    user = make_platform_admin()
    invalidated_tenants: list[int] = []
    monkeypatch.setattr(tenant_api, "update_tenant", lambda *args, **kwargs: session.tenant)
    monkeypatch.setattr(
        tenant_api,
        "set_roi_datasource_for_tenant",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPException(status_code=409, detail="conflict")),
    )
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: invalidated_tenants.append(tenant_id),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            tenant_api.edit_tenant(
                session,
                user,
                11,
                TenantEditor(name="测试", roi_datasource_id=301, roi_project_id="ROI-301"),
            )
        )

    assert exc_info.value.status_code == 409
    assert session.rollback_count == 1
    assert session.commit_count == 0
    assert invalidated_tenants == []


def test_edit_tenant_rolls_back_and_keeps_cache_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeTenantSession(fail_commit=True)
    user = make_platform_admin()
    invalidated_tenants: list[int] = []
    monkeypatch.setattr(tenant_api, "update_tenant", lambda *args, **kwargs: session.tenant)
    monkeypatch.setattr(tenant_api, "set_roi_datasource_for_tenant", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tenant_api, "_write_tenant_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: invalidated_tenants.append(tenant_id),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        asyncio.run(
            tenant_api.edit_tenant(
                session,
                user,
                11,
                TenantEditor(name="测试", roi_datasource_id=301, roi_project_id="ROI-301"),
            )
        )

    assert session.rollback_count == 1
    assert invalidated_tenants == []


@pytest.mark.parametrize("datasource_id", [101, None])
def test_roi_domain_rejects_default_workspace_configuration(
    datasource_id: int | None,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        roi_service.set_roi_datasource_for_tenant(
            object(),
            tenant_id=1,
            datasource_id=datasource_id,
            operator_id=7,
            commit=True,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "默认工作空间不能配置 ROI 数据源"


def test_edit_tenant_rejects_default_workspace_roi_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_tenant = make_tenant()
    default_tenant.id = 1
    default_tenant.public_id = "WS1"
    session = FakeTenantSession()
    session.tenant = default_tenant
    invalidated_tenants: list[int] = []
    monkeypatch.setattr(
        tenant_api,
        "update_tenant",
        lambda *args, **kwargs: default_tenant,
    )
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: invalidated_tenants.append(tenant_id),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            tenant_api.edit_tenant(
                session,
                make_platform_admin(),
                1,
                TenantEditor(name="默认工作空间", roi_datasource_id=101),
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "默认工作空间不能配置 ROI 数据源"
    assert session.rollback_count == 1
    assert session.commit_count == 0
    assert invalidated_tenants == []


def test_edit_tenant_preserves_default_workspace_roi_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_tenant = make_tenant()
    default_tenant.id = 1
    default_tenant.public_id = "WS1"
    default_tenant.roi_project_id = "LEGACY-DEFAULT"
    session = FakeTenantSession()
    session.tenant = default_tenant
    update_values: list[str | None] = []

    def fake_update_tenant(*_args, **kwargs):
        update_values.append(kwargs["roi_project_id"])
        return default_tenant

    monkeypatch.setattr(tenant_api, "update_tenant", fake_update_tenant)
    monkeypatch.setattr(tenant_api, "_write_tenant_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tenant_api,
        "_tenant_admin_dto",
        lambda *_args: TenantDTO(id=1, public_id="WS1", name="默认工作空间"),
    )

    asyncio.run(
        tenant_api.edit_tenant(
            session,
            make_platform_admin(),
            1,
            TenantEditor(name="默认工作空间"),
        )
    )

    assert update_values == ["LEGACY-DEFAULT"]
    assert session.commit_count == 1


def test_edit_tenant_rejects_default_workspace_roi_project_id() -> None:
    session = FakeTenantSession()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            tenant_api.edit_tenant(
                session,
                make_platform_admin(),
                1,
                TenantEditor(name="默认工作空间", roi_project_id="ROI-DEFAULT"),
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "默认工作空间不能配置项目 ID"
    assert session.commit_count == 0
    assert session.rollback_count == 0


@pytest.fixture
def roi_transaction_engine(tmp_path) -> Engine:
    from tests.permission_scope_fixtures import EPOCH_STATEMENTS

    database_path = tmp_path / "tenant_roi_transaction.db"
    engine = create_engine(f"sqlite:///{database_path}")
    statements = [
        *EPOCH_STATEMENTS,
        """
        CREATE TABLE sys_tenant (
            id BIGINT PRIMARY KEY, public_id TEXT, name TEXT, status BIGINT,
            plan TEXT, subscription_status TEXT, billing_mode TEXT,
            trial_end_time BIGINT, current_period_end_time BIGINT,
            contract_no TEXT, billing_contact TEXT, billing_email TEXT,
            roi_project_id TEXT,
            subscription_note TEXT, create_time BIGINT, update_time BIGINT
        )
        """,
        """
        CREATE TABLE core_datasource (
            id BIGINT PRIMARY KEY, tenant_id BIGINT, name TEXT, description TEXT,
            type TEXT, type_name TEXT, configuration TEXT, create_time DATETIME,
            create_by BIGINT, status TEXT, num TEXT, table_relation TEXT,
            embedding TEXT, recommended_config BIGINT,
            catalog_complete BOOLEAN NOT NULL DEFAULT 0,
            catalog_incomplete_reason TEXT, physical_schema_hash VARCHAR(64)
        )
        """,
        """
        CREATE TABLE core_datasource_user (
            id BIGINT PRIMARY KEY, ds_id BIGINT, user_id BIGINT, role TEXT,
            create_by BIGINT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_datasource_tenant_binding (
            id INTEGER PRIMARY KEY, tenant_id BIGINT, datasource_id BIGINT,
            create_by BIGINT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE ds_permission (
            id BIGINT PRIMARY KEY, name TEXT, enable BOOLEAN, auth_target_type TEXT,
            auth_target_id BIGINT, type TEXT, ds_id BIGINT, table_id BIGINT,
            expression_tree TEXT, permissions TEXT, white_list_user TEXT,
            create_time DATETIME
        )
        """,
        """
        CREATE TABLE ds_rules (
            id INTEGER PRIMARY KEY, enable BOOLEAN, name TEXT, description TEXT,
            tenant_id BIGINT, scope TEXT, permission_list TEXT, user_list TEXT,
            white_list_user TEXT, create_time DATETIME
        )
        """,
        """
        CREATE TABLE core_external_mcp_server (
            id BIGINT PRIMARY KEY, name TEXT, endpoint TEXT, description TEXT,
            auth_type TEXT, auth_header_name TEXT, auth_token TEXT, server_name TEXT,
            server_version TEXT, status BIGINT, credential_configured BOOLEAN,
            create_by BIGINT, update_by BIGINT, create_time BIGINT, update_time BIGINT
        )
        """,
        """
        CREATE TABLE core_external_mcp_tenant_binding (
            id INTEGER PRIMARY KEY, tenant_id BIGINT, external_mcp_server_id BIGINT,
            create_by BIGINT, create_time BIGINT
        )
        """,
        """
        CREATE TABLE core_roi_workspace_config (
            id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL,
            datasource_id BIGINT NOT NULL, version INTEGER NOT NULL,
            create_by BIGINT, update_by BIGINT, create_time BIGINT NOT NULL,
            update_time BIGINT NOT NULL, deleted BOOLEAN NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX uq_core_roi_workspace_config_active_tenant
        ON core_roi_workspace_config (tenant_id) WHERE deleted = 0
        """,
        """
        CREATE TABLE core_roi_dashboard_chart (
            id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL,
            roi_dashboard_id BIGINT NOT NULL, title TEXT NOT NULL,
            sql TEXT NOT NULL, chart_type TEXT NOT NULL, chart_config TEXT NOT NULL,
            layout_span TEXT NOT NULL, sort INTEGER NOT NULL, status INTEGER NOT NULL,
            version INTEGER NOT NULL, create_by BIGINT, update_by BIGINT,
            create_time BIGINT NOT NULL, update_time BIGINT NOT NULL,
            deleted BOOLEAN NOT NULL
        )
        """,
        """
        CREATE TABLE sys_logs (
            id INTEGER PRIMARY KEY, tenant_id BIGINT, operation_type TEXT,
            operation_detail TEXT, user_id BIGINT, operation_status TEXT,
            ip_address TEXT, user_agent TEXT, execution_time BIGINT,
            error_message TEXT, create_time DATETIME, module TEXT,
            resource_id TEXT, request_method TEXT, request_path TEXT,
            remark TEXT, user_name TEXT, resource_name TEXT
        )
        """,
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO sys_tenant ("
                "id, public_id, name, status, plan, subscription_status, "
                "billing_mode, roi_project_id, create_time, update_time) VALUES "
                "(11, 'WS11', '原工作空间', 1, 'default', 'active', 'manual', 'ROI-OLD', 1, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_datasource (id, tenant_id, name, status) "
                "VALUES "
                "(101, 1, 'ROI 数据源', 'success'), "
                "(202, 1, '旧 ROI 数据源', 'success'), "
                "(303, 1, '新 ROI 数据源', 'success')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_external_mcp_server (id, name, endpoint, status) "
                "VALUES (201, '测试 MCP', 'https://example.test/mcp', 1)"
            )
        )
    yield engine
    engine.dispose()


def seed_roi_config_and_table_rule(
    session: Session,
    *,
    tenant_id: int,
    roi_datasource_id: int,
) -> None:
    session.exec(
        text(
            "INSERT INTO core_roi_workspace_config "
            "(tenant_id, datasource_id, version, create_by, update_by, create_time, update_time, deleted) "
            "VALUES (:tenant_id, :datasource_id, 1, 7, 7, 1, 1, 0)"
        ),
        params={"tenant_id": tenant_id, "datasource_id": roi_datasource_id},
    )
    session.exec(
        text(
            "INSERT INTO ds_permission "
            "(id, name, enable, type, ds_id, table_id, permissions, white_list_user) "
            "VALUES (9001, 'ROI 禁止表', 1, 'table', :datasource_id, 2001, '[]', '[]')"
        ),
        params={"datasource_id": roi_datasource_id},
    )
    session.exec(
        text(
            "INSERT INTO ds_rules "
            "(id, enable, name, tenant_id, scope, permission_list, user_list, white_list_user) "
            "VALUES (9001, 1, 'ROI 规则组', :tenant_id, 'TENANT', :permissions, :users, '[]')"
        ),
        params={
            "tenant_id": tenant_id,
            "permissions": json.dumps([9001]),
            "users": json.dumps(["7"]),
        },
    )
    session.commit()


def bind_ordinary_datasource(
    session: Session,
    *,
    tenant_id: int,
    datasource_id: int,
) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource_tenant_binding "
            "(tenant_id, datasource_id) VALUES (:tenant_id, :datasource_id)"
        ),
        params={"tenant_id": tenant_id, "datasource_id": datasource_id},
    )
    session.commit()


def tenant_permission_ids(session: Session, tenant_id: int) -> list[int]:
    rows = session.exec(
        text(
            "SELECT p.id FROM ds_permission p "
            "JOIN ds_rules r ON r.permission_list LIKE '%' || p.id || '%' "
            "WHERE r.tenant_id = :tenant_id ORDER BY p.id"
        ),
        params={"tenant_id": tenant_id},
    ).all()
    return [int(row[0]) for row in rows]


def test_roi_rebinding_clears_old_tenant_rules_when_old_source_is_not_ordinary(
    roi_transaction_engine: Engine,
) -> None:
    with Session(roi_transaction_engine) as session:
        seed_roi_config_and_table_rule(session, tenant_id=11, roi_datasource_id=202)
        roi_service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=303,
            operator_id=7,
            commit=False,
        )

        assert tenant_permission_ids(session, 11) == []


def test_roi_rebinding_keeps_rules_when_old_source_remains_ordinary(
    roi_transaction_engine: Engine,
) -> None:
    with Session(roi_transaction_engine) as session:
        bind_ordinary_datasource(session, tenant_id=11, datasource_id=202)
        seed_roi_config_and_table_rule(session, tenant_id=11, roi_datasource_id=202)
        roi_service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=303,
            operator_id=7,
            commit=False,
        )

        assert tenant_permission_ids(session, 11) == [9001]


def _patch_integration_response(
    monkeypatch: pytest.MonkeyPatch,
    invalidated_tenants: list[int],
) -> None:
    monkeypatch.setattr(
        tenant_api,
        "_tenant_admin_dto",
        lambda *_args, **_kwargs: TenantDTO(
            id=11,
            public_id="WS11",
            name="已更新工作空间",
        ),
    )
    monkeypatch.setattr(
        tenant_api,
        "invalidate_roi_chart_cache_for_tenant",
        lambda tenant_id: invalidated_tenants.append(tenant_id),
    )


def _integration_editor() -> TenantEditor:
    return TenantEditor(
        name="已更新工作空间",
        plan="enterprise",
        datasource_id=101,
        external_mcp_server_id=201,
        roi_datasource_id=101,
        roi_project_id="ROI-101",
    )


def test_edit_tenant_persists_all_bindings_and_audit_in_one_sqlite_transaction(
    roi_transaction_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalidated_tenants: list[int] = []
    _patch_integration_response(monkeypatch, invalidated_tenants)

    with Session(roi_transaction_engine) as session:
        asyncio.run(
            tenant_api.edit_tenant(
                session,
                make_platform_admin(),
                11,
                _integration_editor(),
            )
        )

    with Session(roi_transaction_engine) as verification_session:
        tenant_row = verification_session.exec(
            text("SELECT name, plan, roi_project_id FROM sys_tenant WHERE id = 11")
        ).one()
        datasource_id = verification_session.exec(
            text(
                "SELECT datasource_id FROM core_datasource_tenant_binding "
                "WHERE tenant_id = 11"
            )
        ).one()[0]
        external_mcp_id = verification_session.exec(
            text(
                "SELECT external_mcp_server_id FROM core_external_mcp_tenant_binding "
                "WHERE tenant_id = 11"
            )
        ).one()[0]
        roi_row = verification_session.exec(
            text(
                "SELECT datasource_id, deleted FROM core_roi_workspace_config "
                "WHERE tenant_id = 11"
            )
        ).one()
        audit_row = verification_session.exec(
            text(
                "SELECT operation_type, operation_status, remark FROM sys_logs "
                "WHERE tenant_id = 11"
            )
        ).one()

    assert tuple(tenant_row) == ("已更新工作空间", "enterprise", "ROI-101")
    assert int(datasource_id) == 101
    assert int(external_mcp_id) == 201
    assert tuple(roi_row) == (101, 0)
    assert audit_row[0:2] == ("update", "success")
    assert "roi_datasource_id=101" in audit_row[2]
    assert invalidated_tenants == [11]


def test_edit_tenant_commit_failure_rolls_back_entire_sqlite_transaction(
    roi_transaction_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalidated_tenants: list[int] = []
    _patch_integration_response(monkeypatch, invalidated_tenants)

    with Session(roi_transaction_engine) as session:
        monkeypatch.setattr(
            session,
            "commit",
            lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
        )
        with pytest.raises(RuntimeError, match="commit failed"):
            asyncio.run(
                tenant_api.edit_tenant(
                    session,
                    make_platform_admin(),
                    11,
                    _integration_editor(),
                )
            )

    with Session(roi_transaction_engine) as verification_session:
        tenant_row = verification_session.exec(
            text("SELECT name, plan, roi_project_id FROM sys_tenant WHERE id = 11")
        ).one()
        datasource_tenant_id = verification_session.exec(
            text("SELECT tenant_id FROM core_datasource WHERE id = 101")
        ).one()[0]
        datasource_binding_count = verification_session.exec(
            text("SELECT COUNT(*) FROM core_datasource_tenant_binding")
        ).one()[0]
        external_mcp_binding_count = verification_session.exec(
            text("SELECT COUNT(*) FROM core_external_mcp_tenant_binding")
        ).one()[0]
        roi_config_count = verification_session.exec(
            text("SELECT COUNT(*) FROM core_roi_workspace_config")
        ).one()[0]
        audit_count = verification_session.exec(
            text("SELECT COUNT(*) FROM sys_logs")
        ).one()[0]

    assert tuple(tenant_row) == ("原工作空间", "default", "ROI-OLD")
    assert int(datasource_tenant_id) == 1
    assert int(datasource_binding_count) == 0
    assert int(external_mcp_binding_count) == 0
    assert int(roi_config_count) == 0
    assert int(audit_count) == 0
    assert invalidated_tenants == []


def test_public_roi_cache_invalidation_delegates_to_existing_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = object()
    calls: list[tuple[object, int]] = []
    monkeypatch.setattr(
        roi_service,
        "_invalidate_roi_chart_cache",
        lambda cache_adapter, tenant_id: calls.append((cache_adapter, tenant_id)),
    )

    roi_service.invalidate_roi_chart_cache_for_tenant(11, cache_adapter=cache)

    assert calls == [(cache, 11)]
