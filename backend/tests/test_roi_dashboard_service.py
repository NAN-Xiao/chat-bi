"""验证 ROI 配置和工作空间共享看板服务。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.dml import Update
from sqlmodel import Session, create_engine, select

from apps.roi_dashboard.models import (
    CoreRoiDashboard,
    CoreRoiDashboardChart,
    CoreRoiWorkspaceConfig,
)
from apps.roi_dashboard.schemas import (
    RoiConfigUpdate,
    RoiDashboardCreate,
    RoiDashboardOrderItem,
    RoiDashboardReorderRequest,
    RoiDashboardUpdate,
)
from apps.roi_dashboard.service import (
    create_roi_dashboard,
    delete_roi_dashboard,
    get_roi_config,
    list_roi_dashboards,
    reorder_roi_dashboards,
    set_roi_config,
    update_roi_dashboard,
)


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
    statements = [
        (
            "CREATE TABLE core_datasource ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE core_datasource_user ("
            "id INTEGER PRIMARY KEY, ds_id BIGINT NOT NULL, user_id BIGINT NOT NULL)"
        ),
        (
            "CREATE TABLE core_datasource_tenant_binding ("
            "id INTEGER PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT NOT NULL)"
        ),
        (
            "CREATE TABLE core_roi_workspace_config ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT NOT NULL, "
            "version INTEGER NOT NULL, create_by BIGINT, update_by BIGINT, "
            "create_time BIGINT NOT NULL, update_time BIGINT NOT NULL, deleted BOOLEAN NOT NULL)"
        ),
        (
            "CREATE TABLE core_roi_dashboard ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL, "
            "sort INTEGER NOT NULL, status INTEGER NOT NULL, version INTEGER NOT NULL, "
            "create_by BIGINT, update_by BIGINT, create_time BIGINT NOT NULL, "
            "update_time BIGINT NOT NULL, deleted BOOLEAN NOT NULL)"
        ),
        (
            "CREATE TABLE core_roi_dashboard_chart ("
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, roi_dashboard_id BIGINT NOT NULL, "
            "title TEXT NOT NULL, sql TEXT NOT NULL, chart_type TEXT NOT NULL, "
            "chart_config TEXT NOT NULL, layout_span TEXT NOT NULL, sort INTEGER NOT NULL, "
            "status INTEGER NOT NULL, version INTEGER NOT NULL, create_by BIGINT, update_by BIGINT, "
            "create_time BIGINT NOT NULL, update_time BIGINT NOT NULL, deleted BOOLEAN NOT NULL)"
        ),
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    with Session(engine) as db_session:
        yield db_session


def add_datasource(session: Session, datasource_id: int, name: str | None = None) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource (id, tenant_id, name) "
            "VALUES (:id, 1, :name)"
        ),
        params={"id": datasource_id, "name": name or f"数据源 {datasource_id}"},
    )


def grant_datasource(session: Session, *, user_id: int, datasource_id: int) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource_user (ds_id, user_id) "
            "VALUES (:datasource_id, :user_id)"
        ),
        params={"datasource_id": datasource_id, "user_id": user_id},
    )


def seed_roi_config(
    session: Session,
    *,
    tenant_id: int,
    datasource_id: int,
    version: int = 1,
) -> CoreRoiWorkspaceConfig:
    record = CoreRoiWorkspaceConfig(
        id=1000 + tenant_id,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        version=version,
        create_by=1,
        update_by=1,
        create_time=100,
        update_time=100,
        deleted=False,
    )
    session.add(record)
    session.commit()
    return record


def seed_roi_dashboard(
    session: Session,
    *,
    dashboard_id: int,
    tenant_id: int,
    name: str,
    sort: int = 0,
    version: int = 1,
    create_time: int = 100,
) -> CoreRoiDashboard:
    record = CoreRoiDashboard(
        id=dashboard_id,
        tenant_id=tenant_id,
        name=name,
        sort=sort,
        status=1,
        version=version,
        create_by=1,
        update_by=1,
        create_time=create_time,
        update_time=create_time,
        deleted=False,
    )
    session.add(record)
    session.commit()
    return record


def seed_roi_chart(
    session: Session,
    *,
    tenant_id: int,
    dashboard_id: int,
    chart_id: int = 901,
    status: int = 1,
    deleted: bool = False,
) -> None:
    session.exec(
        text(
            "INSERT INTO core_roi_dashboard_chart ("
            "id, tenant_id, roi_dashboard_id, title, sql, chart_type, chart_config, "
            "layout_span, sort, status, version, create_by, update_by, create_time, "
            "update_time, deleted) VALUES ("
            ":id, :tenant_id, :dashboard_id, '图表', 'SELECT 1', 'table', '{}', "
            "'full', 0, :status, 1, 1, 1, 100, 100, :deleted)"
        ),
        params={
            "id": chart_id,
            "tenant_id": tenant_id,
            "dashboard_id": dashboard_id,
            "status": status,
            "deleted": deleted,
        },
    )
    session.commit()


def assert_http_error(status_code: int, call) -> None:
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == status_code


def test_roi_dashboards_are_shared_within_workspace(session: Session) -> None:
    owner = make_user(id=1, tenant_id=11, tenant_role="owner")
    admin = make_user(id=2, tenant_id=11, tenant_role="admin")

    created = create_roi_dashboard(session, owner, RoiDashboardCreate(name="渠道 ROI"))

    assert [item.id for item in list_roi_dashboards(session, admin)] == [created.id]


@pytest.mark.parametrize(
    "user",
    [
        make_user(tenant_role="member"),
        make_user(tenant_role="owner", system_role="system_admin"),
    ],
)
def test_member_and_platform_identity_are_rejected(session: Session, user) -> None:
    assert_http_error(403, lambda: list_roi_dashboards(session, user))


def test_cross_tenant_dashboard_is_not_disclosed(session: Session) -> None:
    seed_roi_dashboard(
        session,
        dashboard_id=301,
        tenant_id=22,
        name="其他空间看板",
    )
    user = make_user(tenant_id=11, tenant_role="owner")

    assert_http_error(
        404,
        lambda: update_roi_dashboard(
            session,
            user,
            301,
            RoiDashboardUpdate(name="越权修改", version=1),
        ),
    )
    assert_http_error(404, lambda: delete_roi_dashboard(session, user, 301))


def test_first_config_requires_no_version_and_is_shared(session: Session) -> None:
    owner = make_user(id=1, tenant_id=11, tenant_role="owner")
    admin = make_user(id=2, tenant_id=11, tenant_role="admin")
    add_datasource(session, 101, "付费数据")
    grant_datasource(session, user_id=1, datasource_id=101)
    session.commit()

    created = set_roi_config(
        session,
        owner,
        RoiConfigUpdate(datasource_id=101, version=None),
    )

    assert created.datasource_id == 101
    assert created.datasource_name == "付费数据"
    assert created.version == 1
    assert get_roi_config(session, admin).id == created.id


def test_first_config_rejects_version_and_unauthorized_datasource(session: Session) -> None:
    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    add_datasource(session, 101)
    session.commit()

    assert_http_error(
        403,
        lambda: set_roi_config(
            session,
            user,
            RoiConfigUpdate(datasource_id=101, version=None),
        ),
    )
    grant_datasource(session, user_id=1, datasource_id=101)
    session.commit()
    assert_http_error(
        409,
        lambda: set_roi_config(
            session,
            user,
            RoiConfigUpdate(datasource_id=101, version=1),
        ),
    )


def test_existing_config_requires_matching_version(session: Session) -> None:
    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    add_datasource(session, 101)
    add_datasource(session, 202)
    grant_datasource(session, user_id=1, datasource_id=101)
    grant_datasource(session, user_id=1, datasource_id=202)
    seed_roi_config(session, tenant_id=11, datasource_id=101, version=3)
    session.commit()

    assert_http_error(
        409,
        lambda: set_roi_config(
            session,
            user,
            RoiConfigUpdate(datasource_id=202, version=None),
        ),
    )
    assert_http_error(
        409,
        lambda: set_roi_config(
            session,
            user,
            RoiConfigUpdate(datasource_id=202, version=2),
        ),
    )

    updated = set_roi_config(
        session,
        user,
        RoiConfigUpdate(datasource_id=202, version=3),
    )
    assert updated.datasource_id == 202
    assert updated.version == 4


def test_existing_config_update_locks_active_config_row(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.roi_dashboard.service import lock_active_roi_config

    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    add_datasource(session, 101)
    grant_datasource(session, user_id=1, datasource_id=101)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    session.commit()
    original_exec = session.exec
    locked_selects = []

    def recording_exec(statement, *args, **kwargs):
        if getattr(statement, "_for_update_arg", None) is not None:
            locked_selects.append(statement)
        return original_exec(statement, *args, **kwargs)

    monkeypatch.setattr(session, "exec", recording_exec)

    updated = set_roi_config(
        session,
        user,
        RoiConfigUpdate(datasource_id=101, version=1),
    )

    assert lock_active_roi_config is not None
    assert len(locked_selects) == 1
    assert updated.version == 2


def test_first_config_integrity_conflict_rolls_back_and_returns_409(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    add_datasource(session, 101)
    grant_datasource(session, user_id=1, datasource_id=101)
    session.commit()
    rollback = Mock(wraps=session.rollback)
    monkeypatch.setattr(session, "rollback", rollback)
    monkeypatch.setattr(
        session,
        "commit",
        Mock(side_effect=IntegrityError("unique conflict", {}, Exception("duplicate"))),
    )

    assert_http_error(
        409,
        lambda: set_roi_config(
            session,
            user,
            RoiConfigUpdate(datasource_id=101, version=None),
        ),
    )

    rollback.assert_called_once_with()
    assert session.exec(text("SELECT 1")).one()[0] == 1


def test_cannot_change_datasource_when_any_active_chart_exists(session: Session) -> None:
    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    add_datasource(session, 202)
    grant_datasource(session, user_id=1, datasource_id=202)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301)
    session.commit()

    assert_http_error(
        409,
        lambda: set_roi_config(
            session,
            user,
            RoiConfigUpdate(datasource_id=202, version=1),
        ),
    )
    persisted = session.exec(
        select(CoreRoiWorkspaceConfig).where(CoreRoiWorkspaceConfig.tenant_id == 11)
    ).one()
    assert (persisted.datasource_id, persisted.version) == (101, 1)


def test_empty_dashboard_and_inactive_chart_do_not_block_datasource_change(
    session: Session,
) -> None:
    user = make_user(id=1, tenant_id=11, tenant_role="owner")
    add_datasource(session, 202)
    grant_datasource(session, user_id=1, datasource_id=202)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    seed_roi_dashboard(session, dashboard_id=301, tenant_id=11, name="空看板")
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, status=0)
    session.commit()

    updated = set_roi_config(
        session,
        user,
        RoiConfigUpdate(datasource_id=202, version=1),
    )

    assert updated.datasource_id == 202


def test_dashboard_list_is_stably_sorted(session: Session) -> None:
    user = make_user(tenant_id=11, tenant_role="admin")
    seed_roi_dashboard(
        session, dashboard_id=303, tenant_id=11, name="后创建", sort=1, create_time=200
    )
    seed_roi_dashboard(
        session, dashboard_id=302, tenant_id=11, name="ID 较小", sort=1, create_time=100
    )
    seed_roi_dashboard(
        session, dashboard_id=301, tenant_id=11, name="最前", sort=0, create_time=300
    )
    seed_roi_dashboard(
        session, dashboard_id=304, tenant_id=22, name="其他租户", sort=-1
    )

    assert [item.id for item in list_roi_dashboards(session, user)] == [301, 302, 303]


def test_update_uses_optimistic_lock(session: Session) -> None:
    user = make_user(id=2, tenant_id=11, tenant_role="admin")
    seed_roi_dashboard(
        session,
        dashboard_id=301,
        tenant_id=11,
        name="旧名称",
        version=2,
    )

    assert_http_error(
        409,
        lambda: update_roi_dashboard(
            session,
            user,
            301,
            RoiDashboardUpdate(name="冲突名称", version=1),
        ),
    )

    updated = update_roi_dashboard(
        session,
        user,
        301,
        RoiDashboardUpdate(name="新名称", version=2),
    )
    assert updated.name == "新名称"
    assert updated.version == 3
    assert updated.update_by == 2


def test_delete_soft_deletes_dashboard_and_its_active_charts(session: Session) -> None:
    user = make_user(id=2, tenant_id=11, tenant_role="admin")
    seed_roi_dashboard(session, dashboard_id=301, tenant_id=11, name="待删除")
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    seed_roi_chart(
        session,
        tenant_id=22,
        dashboard_id=301,
        chart_id=902,
    )

    assert delete_roi_dashboard(session, user, 301) is True
    assert list_roi_dashboards(session, user) == []
    own_chart = session.exec(
        select(CoreRoiDashboardChart).where(CoreRoiDashboardChart.id == 901)
    ).first()
    other_chart = session.exec(
        select(CoreRoiDashboardChart).where(CoreRoiDashboardChart.id == 902)
    ).first()
    assert own_chart.deleted is True
    assert other_chart.deleted is False


def test_reorder_updates_all_versions_atomically(session: Session) -> None:
    user = make_user(id=2, tenant_id=11, tenant_role="admin")
    first = seed_roi_dashboard(
        session, dashboard_id=301, tenant_id=11, name="第一", sort=0, version=1
    )
    second = seed_roi_dashboard(
        session, dashboard_id=302, tenant_id=11, name="第二", sort=1, version=4
    )

    result = reorder_roi_dashboards(
        session,
        user,
        RoiDashboardReorderRequest(
            items=[
                RoiDashboardOrderItem(id="301", sort=2, version=1),
                RoiDashboardOrderItem(id="302", sort=1, version=4),
            ]
        ),
    )

    assert [(item.id, item.sort, item.version) for item in result] == [
        (302, 1, 5),
        (301, 2, 2),
    ]
    session.refresh(first)
    session.refresh(second)
    assert (first.sort, first.version) == (2, 2)
    assert (second.sort, second.version) == (1, 5)


def test_reorder_conflict_does_not_partially_update(session: Session) -> None:
    user = make_user(id=2, tenant_id=11, tenant_role="admin")
    first = seed_roi_dashboard(
        session, dashboard_id=301, tenant_id=11, name="第一", sort=0, version=1
    )
    seed_roi_dashboard(
        session, dashboard_id=302, tenant_id=11, name="第二", sort=1, version=4
    )

    assert_http_error(
        409,
        lambda: reorder_roi_dashboards(
            session,
            user,
            RoiDashboardReorderRequest(
                items=[
                    RoiDashboardOrderItem(id="301", sort=8, version=1),
                    RoiDashboardOrderItem(id="302", sort=9, version=3),
                ]
            ),
        ),
    )
    session.refresh(first)
    assert (first.sort, first.version) == (0, 1)


def test_reorder_execution_conflict_rolls_back_prior_update(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(id=2, tenant_id=11, tenant_role="admin")
    seed_roi_dashboard(
        session, dashboard_id=301, tenant_id=11, name="第一", sort=0, version=1
    )
    seed_roi_dashboard(
        session, dashboard_id=302, tenant_id=11, name="第二", sort=1, version=4
    )
    original_exec = session.exec
    dashboard_update_count = 0

    def conflict_on_second_update(statement, *args, **kwargs):
        nonlocal dashboard_update_count
        if isinstance(statement, Update) and statement.table.name == "core_roi_dashboard":
            dashboard_update_count += 1
            if dashboard_update_count == 2:
                return SimpleNamespace(rowcount=0)
        return original_exec(statement, *args, **kwargs)

    monkeypatch.setattr(session, "exec", conflict_on_second_update)

    assert_http_error(
        409,
        lambda: reorder_roi_dashboards(
            session,
            user,
            RoiDashboardReorderRequest(
                items=[
                    RoiDashboardOrderItem(id="301", sort=8, version=1),
                    RoiDashboardOrderItem(id="302", sort=9, version=4),
                ]
            ),
        ),
    )

    monkeypatch.setattr(session, "exec", original_exec)
    session.expire_all()
    persisted = session.exec(
        select(CoreRoiDashboard).where(CoreRoiDashboard.tenant_id == 11)
        .order_by(CoreRoiDashboard.id)
    ).all()
    assert dashboard_update_count == 2
    assert [(item.id, item.sort, item.version) for item in persisted] == [
        (301, 0, 1),
        (302, 1, 4),
    ]


def test_reorder_cross_tenant_id_returns_404(session: Session) -> None:
    user = make_user(id=2, tenant_id=11, tenant_role="admin")
    seed_roi_dashboard(
        session, dashboard_id=301, tenant_id=22, name="其他空间", sort=0, version=1
    )

    assert_http_error(
        404,
        lambda: reorder_roi_dashboards(
            session,
            user,
            RoiDashboardReorderRequest(
                items=[RoiDashboardOrderItem(id="301", sort=1, version=1)]
            ),
        ),
    )
