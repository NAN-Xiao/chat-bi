"""验证 ROI 专用看板的工作空间角色与账号级数据源授权。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, create_engine


def make_user(
    *,
    id: int = 7,
    tenant_id: int | None = 11,
    tenant_role: str = "admin",
    system_role: str = "viewer",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        tenant_id=tenant_id,
        tenant_role=tenant_role,
        system_role=system_role,
        isAdmin=system_role in {"system_admin", "collab_admin"},
        workspace_status="active",
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE core_datasource ("
                "id BIGINT PRIMARY KEY, "
                "tenant_id BIGINT NOT NULL DEFAULT 1, "
                "status TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE core_datasource_user ("
                "id INTEGER PRIMARY KEY, ds_id BIGINT NOT NULL, user_id BIGINT NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE core_datasource_tenant_binding ("
                "id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL, "
                "datasource_id BIGINT NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE core_roi_workspace_config ("
                "id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL, "
                "datasource_id BIGINT NOT NULL, deleted BOOLEAN NOT NULL DEFAULT 0)"
            )
        )
    with Session(engine) as db_session:
        yield db_session


def add_datasource(
    session: Session,
    datasource_id: int,
    *,
    status: str = "Success",
) -> None:
    session.exec(
        text("INSERT INTO core_datasource (id, status) VALUES (:id, :status)"),
        params={"id": datasource_id, "status": status},
    )


def bind_datasource(session: Session, *, tenant_id: int, datasource_id: int) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource_tenant_binding "
            "(tenant_id, datasource_id) VALUES (:tenant_id, :datasource_id)"
        ),
        params={"tenant_id": tenant_id, "datasource_id": datasource_id},
    )


def grant_datasource_user(session: Session, *, user_id: int, datasource_id: int) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource_user (ds_id, user_id) "
            "VALUES (:datasource_id, :user_id)"
        ),
        params={"datasource_id": datasource_id, "user_id": user_id},
    )


def configure_roi_datasource(
    session: Session,
    *,
    tenant_id: int,
    datasource_id: int,
    deleted: bool = False,
) -> None:
    session.exec(
        text(
            "INSERT INTO core_roi_workspace_config (tenant_id, datasource_id, deleted) "
            "VALUES (:tenant_id, :datasource_id, :deleted)"
        ),
        params={
            "tenant_id": tenant_id,
            "datasource_id": datasource_id,
            "deleted": deleted,
        },
    )


@pytest.mark.parametrize("tenant_role", ["owner", "admin"])
def test_workspace_owner_and_admin_can_access_roi(tenant_role: str) -> None:
    from apps.roi_dashboard.permissions import require_roi_workspace_admin

    user = make_user(tenant_role=tenant_role)

    context = require_roi_workspace_admin(user)

    assert context.tenant_id == 11
    assert context.tenant_role == tenant_role


def test_member_cannot_access_roi() -> None:
    from apps.roi_dashboard.permissions import require_roi_workspace_admin

    user = make_user(tenant_role="member")

    with pytest.raises(HTTPException) as exc:
        require_roi_workspace_admin(user)

    assert exc.value.status_code == 403


def test_global_platform_admin_cannot_use_default_workspace_owner_role() -> None:
    from apps.roi_dashboard.permissions import require_roi_workspace_admin

    user = make_user(
        tenant_id=1,
        tenant_role="owner",
        system_role="system_admin",
    )
    user.workspace_role = "owner"

    with pytest.raises(HTTPException) as exc:
        require_roi_workspace_admin(user)

    assert exc.value.status_code == 403


def test_platform_workspace_delegate_cannot_bypass_roi_workspace_role() -> None:
    from apps.roi_dashboard.permissions import require_roi_workspace_admin

    user = make_user(tenant_role="owner", system_role="system_admin")
    user.workspace_role = "owner"
    user.workspace_status = "platform_workspace_delegate"

    with pytest.raises(HTTPException) as exc:
        require_roi_workspace_admin(user)

    assert exc.value.status_code == 403


def test_roi_datasources_union_workspace_and_direct_account_grants(
    session: Session,
) -> None:
    from apps.roi_dashboard.permissions import (
        has_roi_datasource_access,
        list_account_datasource_ids_without_tenant_filter,
        list_roi_accessible_datasource_ids,
    )

    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 101, status="Success")
    add_datasource(session, 202, status="success")
    add_datasource(session, 303, status="Success")
    bind_datasource(session, tenant_id=11, datasource_id=101)
    bind_datasource(session, tenant_id=22, datasource_id=202)
    grant_datasource_user(session, user_id=7, datasource_id=202)
    grant_datasource_user(session, user_id=8, datasource_id=303)
    grant_datasource_user(session, user_id=7, datasource_id=404)
    session.commit()

    assert list_account_datasource_ids_without_tenant_filter(session, 7) == {202, 404}
    assert list_roi_accessible_datasource_ids(session, user) == {101, 202}
    assert has_roi_datasource_access(session, user, 101) is True
    assert has_roi_datasource_access(session, user, 202) is True
    assert has_roi_datasource_access(session, user, 303) is False
    assert has_roi_datasource_access(session, user, 404) is False


def test_workspace_admin_can_access_configured_roi_datasource_without_direct_grant(
    session: Session,
) -> None:
    from apps.roi_dashboard.permissions import (
        has_roi_datasource_access,
        list_roi_accessible_datasource_ids,
    )

    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 202)
    add_datasource(session, 303)
    configure_roi_datasource(session, tenant_id=11, datasource_id=202)
    configure_roi_datasource(session, tenant_id=22, datasource_id=303)
    session.commit()

    assert list_roi_accessible_datasource_ids(session, user) == {202}
    # 虽然配置纳入可访问集合，但写入/执行权限仍需显式授权（服务层保持原有授权要求）
    assert has_roi_datasource_access(session, user, 202) is False
    assert has_roi_datasource_access(session, user, 303) is False


def test_inactive_datasources_are_excluded_from_all_roi_permission_candidates(
    session: Session,
) -> None:
    from apps.roi_dashboard.permissions import (
        has_roi_datasource_access,
        list_roi_accessible_datasource_ids,
    )

    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 101, status="failed")
    add_datasource(session, 202, status="disabled")
    add_datasource(session, 303, status="successful")
    bind_datasource(session, tenant_id=11, datasource_id=101)
    grant_datasource_user(session, user_id=7, datasource_id=202)
    grant_datasource_user(session, user_id=7, datasource_id=303)
    configure_roi_datasource(session, tenant_id=11, datasource_id=303)
    session.commit()

    assert list_roi_accessible_datasource_ids(session, user) == set()
    assert has_roi_datasource_access(session, user, 101) is False
    assert has_roi_datasource_access(session, user, 202) is False
    assert has_roi_datasource_access(session, user, 303) is False


def test_deleted_roi_config_does_not_grant_datasource_access(
    session: Session,
) -> None:
    from apps.roi_dashboard.permissions import (
        has_roi_datasource_access,
        list_roi_accessible_datasource_ids,
    )

    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 202)
    configure_roi_datasource(
        session,
        tenant_id=11,
        datasource_id=202,
        deleted=True,
    )
    session.commit()

    assert list_roi_accessible_datasource_ids(session, user) == set()
    assert has_roi_datasource_access(session, user, 202) is False
