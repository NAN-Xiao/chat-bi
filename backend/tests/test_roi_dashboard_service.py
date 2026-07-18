"""验证 ROI 配置和工作空间共享看板服务。"""

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.dml import Update
from sqlmodel import Session, create_engine, select

from apps.roi_dashboard import service
from apps.roi_dashboard.models import (
    CoreRoiDashboard,
    CoreRoiDashboardChart,
    CoreRoiWorkspaceConfig,
)
from apps.roi_dashboard.query_executor import RoiQueryResult
from apps.roi_dashboard.schemas import (
    RoiChartCreate,
    RoiChartOrderItem,
    RoiChartPreviewRequest,
    RoiChartReorderRequest,
    RoiChartUpdate,
    RoiDashboardCreate,
    RoiDashboardOrderItem,
    RoiDashboardReorderRequest,
    RoiDashboardUpdate,
)
from apps.roi_dashboard.service import (
    create_roi_chart,
    create_roi_dashboard,
    delete_roi_chart,
    delete_roi_dashboard,
    get_roi_config,
    list_roi_charts,
    list_roi_dashboards,
    preview_roi_chart,
    reorder_roi_charts,
    reorder_roi_dashboards,
    roi_chart_cache_key,
    set_roi_datasource_for_tenant,
    update_roi_chart,
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
            "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, name TEXT NOT NULL, status TEXT)"
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
            "CREATE UNIQUE INDEX uq_core_roi_workspace_config_active_tenant "
            "ON core_roi_workspace_config (tenant_id) WHERE deleted = 0"
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


@pytest.fixture(autouse=True)
def isolate_default_roi_cache(monkeypatch: pytest.MonkeyPatch):
    cache = FakeRoiChartCache()
    monkeypatch.setattr("apps.roi_dashboard.service._ROI_CHART_CACHE", cache)
    return cache


def add_datasource(session: Session, datasource_id: int, name: str | None = None) -> None:
    session.exec(
        text(
            "INSERT INTO core_datasource (id, tenant_id, name, status) "
            "VALUES (:id, 1, :name, 'success')"
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
) -> CoreRoiDashboardChart:
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
    return session.exec(
        select(CoreRoiDashboardChart).where(CoreRoiDashboardChart.id == chart_id)
    ).one()


def assert_http_error(status_code: int, call) -> None:
    with pytest.raises(HTTPException) as exc:
        call()
    assert exc.value.status_code == status_code


def test_roi_dashboards_are_shared_within_workspace(session: Session) -> None:
    owner = make_user(id=1, tenant_id=11, tenant_role="owner")
    admin = make_user(id=2, tenant_id=11, tenant_role="admin")
    add_datasource(session, 101)
    grant_datasource(session, user_id=1, datasource_id=101)
    seed_roi_config(session, tenant_id=11, datasource_id=101)

    created = create_roi_dashboard(session, owner, RoiDashboardCreate(name="渠道 ROI"))

    assert [item.id for item in list_roi_dashboards(session, admin)] == [created.id]


@pytest.mark.parametrize(
    ("state", "expected_status", "expected_detail"),
    [
        ("missing", 409, "当前工作空间尚未配置 ROI 数据源"),
        ("unauthorized", 403, "当前账号无此数据源权限"),
        ("inactive", 403, "当前账号无此数据源权限"),
    ],
)
def test_create_dashboard_requires_executable_roi_datasource(
    session: Session,
    state: str,
    expected_status: int,
    expected_detail: str,
) -> None:
    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    if state != "missing":
        add_datasource(session, 101)
        seed_roi_config(session, tenant_id=11, datasource_id=101)
    if state == "inactive":
        grant_datasource(session, user_id=7, datasource_id=101)
        session.exec(text("UPDATE core_datasource SET status = 'failed' WHERE id = 101"))
        session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_roi_dashboard(session, user, RoiDashboardCreate(name="禁止创建"))

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_detail
    assert session.exec(select(CoreRoiDashboard)).all() == []


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


def test_platform_admin_can_create_and_read_roi_datasource_binding(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_datasource(session, 101, "ROI 数据源")
    cache = FakeRoiChartCache()
    events: list[str] = []
    original_commit = session.commit
    original_delete_pattern = cache.delete_pattern

    def record_commit(*args, **kwargs):
        events.append("commit")
        return original_commit(*args, **kwargs)

    def record_delete_pattern(pattern: str) -> None:
        events.append("cache_delete")
        original_delete_pattern(pattern)

    monkeypatch.setattr(session, "commit", record_commit)
    monkeypatch.setattr(cache, "delete_pattern", record_delete_pattern)

    created = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=1,
        commit=True,
        cache_adapter=cache,
    )

    assert created is not None
    assert (created.tenant_id, created.datasource_id, created.version) == (11, 101, 1)
    assert len(cache.deleted_patterns) == 1
    assert events == ["commit", "cache_delete"]
    assert service.list_roi_workspace_config_rows(session, [11]) == [
        (11, 101, "ROI 数据源")
    ]


def test_platform_admin_roi_datasource_binding_is_idempotent(
    session: Session,
) -> None:
    add_datasource(session, 101)
    original = seed_roi_config(session, tenant_id=11, datasource_id=101, version=3)
    cache = FakeRoiChartCache()

    updated = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=9,
        commit=True,
        cache_adapter=cache,
    )

    assert updated is not None
    assert updated.id == original.id
    assert updated.version == 3
    assert cache.deleted_patterns == []


@pytest.mark.parametrize("datasource_state", ["deleted", "inactive"])
def test_platform_admin_idempotent_save_keeps_invalid_bound_datasource(
    session: Session,
    datasource_state: str,
) -> None:
    if datasource_state == "inactive":
        add_datasource(session, 101)
        session.exec(text("UPDATE core_datasource SET status = 'failed' WHERE id = 101"))
    original = seed_roi_config(session, tenant_id=11, datasource_id=101, version=3)

    updated = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=9,
        commit=True,
    )

    assert updated is not None
    assert updated.id == original.id
    assert updated.datasource_id == 101
    assert updated.version == 3


def test_workspace_config_rows_keep_deleted_datasource_id(session: Session) -> None:
    seed_roi_config(session, tenant_id=11, datasource_id=101)

    assert service.list_roi_workspace_config_rows(session, [11]) == [(11, 101, None)]


def test_platform_admin_rejects_switch_to_inactive_datasource(
    session: Session,
) -> None:
    add_datasource(session, 101)
    add_datasource(session, 202)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    session.exec(text("UPDATE core_datasource SET status = 'failed' WHERE id = 202"))
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=202,
            operator_id=9,
            commit=True,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "ROI 数据源不可用"


def test_platform_admin_restores_soft_deleted_roi_datasource_binding(
    session: Session,
) -> None:
    add_datasource(session, 101)
    original = seed_roi_config(session, tenant_id=11, datasource_id=101, version=3)
    original.deleted = True
    session.add(original)
    session.commit()

    restored = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=9,
        commit=True,
    )

    assert restored is not None
    assert (restored.id, restored.version, restored.deleted) == (original.id, 4, False)


@pytest.mark.parametrize("status", [None, "", "failed"])
def test_platform_admin_rejects_non_success_roi_datasource(
    session: Session,
    status: str | None,
) -> None:
    add_datasource(session, 101)
    session.exec(
        text("UPDATE core_datasource SET status = :status WHERE id = 101"),
        params={"status": status},
    )

    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=101,
            operator_id=1,
            commit=True,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "ROI 数据源不可用"


def test_platform_admin_accepts_case_insensitive_success_roi_datasource(
    session: Session,
) -> None:
    add_datasource(session, 101)
    session.exec(text("UPDATE core_datasource SET status = 'SUCCESS' WHERE id = 101"))

    created = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=1,
        commit=True,
    )

    assert created is not None
    assert created.datasource_id == 101


@pytest.mark.parametrize("datasource_id", [0, "", False, "not-a-number"])
def test_platform_admin_rejects_invalid_roi_datasource_id(
    session: Session,
    datasource_id: int | str | bool,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=datasource_id,
            operator_id=1,
            commit=True,
        )

    assert exc_info.value.status_code == 400


def test_platform_admin_roi_datasource_binding_can_skip_commit(
    session: Session,
) -> None:
    add_datasource(session, 101)
    cache = FakeRoiChartCache()

    created = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=101,
        operator_id=1,
        commit=False,
        cache_adapter=cache,
    )

    assert created is not None
    assert service.list_roi_workspace_config_rows(session, [11]) == [(11, 101, "数据源 101")]
    assert cache.deleted_patterns == []
    session.rollback()
    session.expire_all()
    assert service.list_roi_workspace_config_rows(session, [11]) == []


def test_platform_admin_create_conflict_from_unique_index_keeps_session_usable(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_datasource(session, 101)
    existing = seed_roi_config(session, tenant_id=11, datasource_id=101)
    monkeypatch.setattr(service, "lock_active_roi_config", lambda *_args: None)

    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=101,
            operator_id=1,
            commit=False,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "ROI 配置已被其他请求修改，请刷新后重试"
    assert session.exec(text("SELECT 1")).one()[0] == 1
    assert service.list_roi_workspace_config_rows(session, [11]) == [
        (11, existing.datasource_id, "数据源 101")
    ]


def test_platform_admin_restore_conflict_from_unique_index_keeps_session_usable(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    add_datasource(session, 101)
    historical = seed_roi_config(session, tenant_id=11, datasource_id=101)
    historical.deleted = True
    session.add(historical)
    session.commit()
    session.exec(
        text(
            "INSERT INTO core_roi_workspace_config ("
            "id, tenant_id, datasource_id, version, create_by, update_by, "
            "create_time, update_time, deleted) VALUES "
            "(2011, 11, 101, 1, 1, 1, 100, 100, 0)"
        )
    )
    session.commit()
    monkeypatch.setattr(service, "lock_active_roi_config", lambda *_args: None)

    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=101,
            operator_id=1,
            commit=False,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "ROI 配置已被其他请求修改，请刷新后重试"
    assert session.exec(text("SELECT 1")).one()[0] == 1
    session.expire_all()
    records = session.exec(
        select(CoreRoiWorkspaceConfig)
        .where(CoreRoiWorkspaceConfig.tenant_id == 11)
        .order_by(CoreRoiWorkspaceConfig.id)
    ).all()
    assert [(record.id, record.deleted) for record in records] == [
        (historical.id, True),
        (2011, False),
    ]


def test_platform_admin_can_clear_roi_datasource_without_active_charts(
    session: Session,
) -> None:
    add_datasource(session, 101)
    seed_roi_config(session, tenant_id=11, datasource_id=101)

    cleared = service.set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=None,
        operator_id=1,
        commit=True,
    )

    assert cleared is None
    assert service.list_roi_workspace_config_rows(session, [11]) == []


@pytest.mark.parametrize("target_datasource_id", [None, 202])
def test_platform_admin_cannot_change_or_clear_roi_datasource_with_active_charts(
    session: Session,
    target_datasource_id: int | None,
) -> None:
    add_datasource(session, 101)
    add_datasource(session, 202)
    seed_roi_config(session, tenant_id=11, datasource_id=101)
    seed_roi_dashboard(session, tenant_id=11, dashboard_id=301, name="ROI 看板")
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=401)

    with pytest.raises(HTTPException) as exc_info:
        service.set_roi_datasource_for_tenant(
            session,
            tenant_id=11,
            datasource_id=target_datasource_id,
            operator_id=1,
            commit=True,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "已有 ROI 图表时不能更换或清除数据源"


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


class FakeRoiChartCache:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}
        self.get_keys: list[str] = []
        self.deleted_patterns: list[str] = []

    def get(self, key: str):
        self.get_keys.append(key)
        return self.values.get(key)

    def set(self, key: str, value: dict) -> None:
        self.values[key] = value

    def delete_pattern(self, pattern: str) -> None:
        self.deleted_patterns.append(pattern)
        self.values = {
            key: value
            for key, value in self.values.items()
            if not _redis_pattern_matches(pattern, key)
        }


def _redis_pattern_matches(pattern: str, key: str) -> bool:
    import fnmatch

    return fnmatch.fnmatchcase(key, pattern)


def successful_query(value: int = 1) -> RoiQueryResult:
    return RoiQueryResult(
        status="success",
        fields=["value"],
        data=[{"value": value}],
    )


def prepare_chart_context(session: Session, *, grant: bool = True) -> SimpleNamespace:
    user = make_user(id=7, tenant_id=11, tenant_role="admin")
    add_datasource(session, 202)
    if grant:
        grant_datasource(session, user_id=7, datasource_id=202)
    seed_roi_config(session, tenant_id=11, datasource_id=202)
    seed_roi_dashboard(session, dashboard_id=301, tenant_id=11, name="ROI")
    session.commit()
    return user


def test_preview_executes_without_persisting_chart(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        lambda *_args: successful_query(8),
    )

    result = preview_roi_chart(
        session,
        user,
        301,
        RoiChartPreviewRequest(
            title="预览",
            sql="SELECT 8 AS value",
            chart_type="table",
        ),
    )

    assert result.data == [{"value": 8}]
    assert session.exec(select(CoreRoiDashboardChart)).all() == []


def test_create_locks_config_before_authorization_execution_and_write(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    import apps.roi_dashboard.service as service

    events: list[str] = []
    original_dashboard_lock = service.lock_active_roi_dashboard
    original_config_lock = service.lock_active_roi_config
    original_access = service.has_roi_datasource_access

    def record_dashboard_lock(*args):
        events.append("dashboard_lock")
        return original_dashboard_lock(*args)

    def record_config_lock(*args):
        events.append("config_lock")
        return original_config_lock(*args)

    def record_access(*args):
        events.append("access")
        return original_access(*args)

    def record_execute(*_args):
        events.append("execute")
        return successful_query()

    monkeypatch.setattr(service, "lock_active_roi_dashboard", record_dashboard_lock)
    monkeypatch.setattr(service, "lock_active_roi_config", record_config_lock)
    monkeypatch.setattr(service, "has_roi_datasource_access", record_access)
    monkeypatch.setattr(service, "execute_roi_read_query", record_execute)

    created = create_roi_chart(
        session,
        user,
        301,
        RoiChartCreate(title="收入", sql="SELECT 1", chart_type="table"),
    )

    assert events[:4] == ["dashboard_lock", "config_lock", "access", "execute"]
    assert created.version == 1
    assert created.layout_span == "full"


def test_create_reexecutes_sql_and_failed_execution_is_not_saved(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    calls: list[str] = []

    def failed_execute(_session, _user, sql):
        calls.append(sql)
        return RoiQueryResult(status="failed", message="timeout")

    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        failed_execute,
    )

    assert_http_error(
        400,
        lambda: create_roi_chart(
            session,
            user,
            301,
            RoiChartCreate(title="失败", sql="SELECT slow", chart_type="table"),
        ),
    )
    assert calls == ["SELECT slow"]
    assert session.exec(select(CoreRoiDashboardChart)).all() == []


def test_chart_list_checks_permission_before_cache_and_keeps_structure_visible(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    chart = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    cache = FakeRoiChartCache()
    executions = 0

    def execute(*_args):
        nonlocal executions
        executions += 1
        return successful_query(9)

    monkeypatch.setattr("apps.roi_dashboard.service.execute_roi_read_query", execute)

    first = list_roi_charts(session, user, 301, cache_adapter=cache)
    second = list_roi_charts(session, user, 301, cache_adapter=cache)
    expected_key = roi_chart_cache_key(
        11,
        7,
        202,
        301,
        901,
        chart.version,
        hashlib.sha256(chart.sql.encode("utf-8")).hexdigest(),
    )
    assert executions == 1
    assert cache.get_keys == [expected_key, expected_key]
    assert first[0]["can_execute"] is True
    assert second[0]["query_result"]["data"] == [{"value": 9}]

    session.exec(
        text("DELETE FROM core_datasource_user WHERE user_id = 7 AND ds_id = 202")
    )
    session.commit()
    cache.get_keys.clear()
    unauthorized = list_roi_charts(session, user, 301, cache_adapter=cache)

    assert cache.get_keys == []
    assert unauthorized[0]["id"] == 901
    assert unauthorized[0]["can_execute"] is False
    assert unauthorized[0]["can_edit"] is False
    assert unauthorized[0]["error"] == "当前账号无此数据源权限"


def test_chart_writes_are_rejected_without_datasource_access(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session, grant=False)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        lambda *_args: pytest.fail("无权限时不应执行 SQL"),
    )

    calls = [
        lambda: create_roi_chart(
            session,
            user,
            301,
            RoiChartCreate(title="新增", sql="SELECT 1", chart_type="table"),
        ),
        lambda: update_roi_chart(
            session,
            user,
            301,
            901,
            RoiChartUpdate(
                title="修改",
                sql="SELECT 1",
                chart_type="table",
                version=1,
            ),
        ),
        lambda: delete_roi_chart(session, user, 301, 901),
        lambda: reorder_roi_charts(
            session,
            user,
            301,
            RoiChartReorderRequest(
                items=[
                    RoiChartOrderItem(
                        id="901", sort=1, layout_span="half", version=1
                    )
                ]
            ),
        ),
    ]
    for call in calls:
        assert_http_error(403, call)


def test_update_chart_uses_version_and_hides_cross_tenant_chart(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    seed_roi_chart(session, tenant_id=22, dashboard_id=301, chart_id=902)
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        lambda *_args: successful_query(),
    )
    request = RoiChartUpdate(
        title="新版",
        sql="SELECT 2",
        chart_type="bar",
        chart_config={"xAxis": "name"},
        layout_span="half",
        sort=3,
        version=2,
    )

    assert_http_error(409, lambda: update_roi_chart(session, user, 301, 901, request))
    assert_http_error(404, lambda: update_roi_chart(session, user, 301, 902, request))

    updated = update_roi_chart(
        session,
        user,
        301,
        901,
        request.model_copy(update={"version": 1}),
    )
    assert (updated.title, updated.version, updated.layout_span) == ("新版", 2, "half")


def test_update_failed_execution_does_not_overwrite_chart(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    original = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        lambda *_args: RoiQueryResult(status="failed", message="timeout"),
    )

    assert_http_error(
        400,
        lambda: update_roi_chart(
            session,
            user,
            301,
            901,
            RoiChartUpdate(
                title="不应保存",
                sql="SELECT slow",
                chart_type="bar",
                version=1,
            ),
        ),
    )
    session.refresh(original)
    assert (original.title, original.sql, original.version) == (
        "图表",
        "SELECT 1",
        1,
    )


def test_cross_tenant_chart_returns_404_even_without_datasource_access(
    session: Session,
) -> None:
    user = prepare_chart_context(session, grant=False)
    seed_roi_chart(session, tenant_id=22, dashboard_id=301, chart_id=902)
    update_request = RoiChartUpdate(
        title="越权",
        sql="SELECT 1",
        chart_type="table",
        version=1,
    )
    reorder_request = RoiChartReorderRequest(
        items=[
            RoiChartOrderItem(id="902", sort=1, layout_span="half", version=1)
        ]
    )

    assert_http_error(
        404,
        lambda: update_roi_chart(session, user, 301, 902, update_request),
    )
    assert_http_error(404, lambda: delete_roi_chart(session, user, 301, 902))
    assert_http_error(
        404,
        lambda: reorder_roi_charts(session, user, 301, reorder_request),
    )


def test_chart_layout_validation_rejects_unknown_span() -> None:
    with pytest.raises(ValueError):
        RoiChartCreate(
            title="错误宽度",
            sql="SELECT 1",
            chart_type="table",
            layout_span="quarter",
        )


def test_reorder_charts_rolls_back_when_later_update_conflicts(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=902)
    original_exec = session.exec
    chart_update_count = 0

    def conflict_on_second_update(statement, *args, **kwargs):
        nonlocal chart_update_count
        if isinstance(statement, Update) and statement.table.name == "core_roi_dashboard_chart":
            chart_update_count += 1
            if chart_update_count == 2:
                return SimpleNamespace(rowcount=0)
        return original_exec(statement, *args, **kwargs)

    monkeypatch.setattr(session, "exec", conflict_on_second_update)
    request = RoiChartReorderRequest(
        items=[
            RoiChartOrderItem(id="901", sort=2, layout_span="half", version=1),
            RoiChartOrderItem(id="902", sort=1, layout_span="third", version=1),
        ]
    )

    assert_http_error(409, lambda: reorder_roi_charts(session, user, 301, request))
    monkeypatch.setattr(session, "exec", original_exec)
    session.expire_all()
    records = session.exec(
        select(CoreRoiDashboardChart).where(CoreRoiDashboardChart.tenant_id == 11)
        .order_by(CoreRoiDashboardChart.id)
    ).all()
    assert [(item.sort, item.layout_span, item.version) for item in records] == [
        (0, "full", 1),
        (0, "full", 1),
    ]


def test_reorder_charts_updates_sort_layout_and_version(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    first = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    second = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=902)
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        lambda *_args: successful_query(),
    )

    reorder_roi_charts(
        session,
        user,
        301,
        RoiChartReorderRequest(
            items=[
                RoiChartOrderItem(id="901", sort=2, layout_span="half", version=1),
                RoiChartOrderItem(id="902", sort=1, layout_span="third", version=1),
            ]
        ),
    )

    session.refresh(first)
    session.refresh(second)
    assert (first.sort, first.layout_span, first.version) == (2, "half", 2)
    assert (second.sort, second.layout_span, second.version) == (1, "third", 2)


def test_chart_mutations_and_config_change_invalidate_roi_cache(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    add_datasource(session, 303)
    session.commit()
    cache = FakeRoiChartCache()
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        lambda *_args: successful_query(),
    )
    created = create_roi_chart(
        session,
        user,
        301,
        RoiChartCreate(title="新增", sql="SELECT 1", chart_type="table"),
        cache_adapter=cache,
    )
    updated = update_roi_chart(
        session,
        user,
        301,
        created.id,
        RoiChartUpdate(
            title="修改",
            sql="SELECT 2",
            chart_type="bar",
            version=1,
        ),
        cache_adapter=cache,
    )
    reorder_roi_charts(
        session,
        user,
        301,
        RoiChartReorderRequest(
            items=[
                RoiChartOrderItem(
                    id=str(updated.id), sort=2, layout_span="half", version=2
                )
            ]
        ),
        cache_adapter=cache,
    )
    assert delete_roi_chart(
        session,
        user,
        301,
        created.id,
        cache_adapter=cache,
    ) is True
    set_roi_datasource_for_tenant(
        session,
        tenant_id=11,
        datasource_id=303,
        operator_id=user.id,
        commit=True,
        cache_adapter=cache,
    )

    assert len(cache.deleted_patterns) == 5
    assert all("roi-chart" in pattern for pattern in cache.deleted_patterns)


def test_chart_list_isolates_driver_exception_and_continues_other_charts(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = prepare_chart_context(session)
    first = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    second = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=902)
    first.sql = "SELECT failing"
    second.sql = "SELECT working"
    session.add(first)
    session.add(second)
    session.commit()

    def execute(_session, _user, sql):
        if sql == "SELECT failing":
            raise RuntimeError("driver failed password=do-not-log")
        return successful_query(2)

    monkeypatch.setattr("apps.roi_dashboard.service.execute_roi_read_query", execute)

    result = list_roi_charts(
        session,
        user,
        301,
        cache_adapter=FakeRoiChartCache(),
    )

    assert len(result) == 2
    assert result[0]["query_result"]["status"] == "failed"
    assert result[1]["query_result"]["data"] == [{"value": 2}]
    assert "tenant_id=11" in caplog.text
    assert "user_id=7" in caplog.text
    assert "datasource_id=202" in caplog.text
    assert "elapsed_ms=" in caplog.text
    assert "status=failed" in caplog.text
    assert "do-not-log" not in caplog.text


def test_reorder_commit_is_not_reported_failed_when_chart_query_raises(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    chart = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    execute = Mock(side_effect=RuntimeError("driver unavailable"))
    monkeypatch.setattr(
        "apps.roi_dashboard.service.execute_roi_read_query",
        execute,
    )

    result = reorder_roi_charts(
        session,
        user,
        301,
        RoiChartReorderRequest(
            items=[
                RoiChartOrderItem(id="901", sort=3, layout_span="half", version=1)
            ]
        ),
        cache_adapter=FakeRoiChartCache(),
    )

    session.refresh(chart)
    assert (chart.sort, chart.layout_span, chart.version) == (3, "half", 2)
    assert result[0]["version"] == 2
    assert result[0]["query_result"] is None
    execute.assert_not_called()


def test_create_rechecks_active_dashboard_under_lock(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    import apps.roi_dashboard.service as service

    monkeypatch.setattr(service, "lock_active_roi_dashboard", lambda *_args: None)
    monkeypatch.setattr(
        service,
        "execute_roi_read_query",
        lambda *_args: pytest.fail("看板锁定后已失效时不应执行 SQL"),
    )

    assert_http_error(
        404,
        lambda: create_roi_chart(
            session,
            user,
            301,
            RoiChartCreate(title="竞态", sql="SELECT 1", chart_type="table"),
        ),
    )
    assert session.exec(select(CoreRoiDashboardChart)).all() == []


def test_delete_dashboard_uses_same_lock_order_and_invalidates_cache(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    cache = FakeRoiChartCache()
    import apps.roi_dashboard.service as service

    events: list[str] = []
    original_dashboard_lock = service.lock_active_roi_dashboard
    original_config_lock = service.lock_active_roi_config

    def record_dashboard_lock(*args):
        events.append("dashboard_lock")
        return original_dashboard_lock(*args)

    def record_config_lock(*args):
        events.append("config_lock")
        return original_config_lock(*args)

    monkeypatch.setattr(service, "lock_active_roi_dashboard", record_dashboard_lock)
    monkeypatch.setattr(service, "lock_active_roi_config", record_config_lock)

    assert delete_roi_dashboard(
        session,
        user,
        301,
        cache_adapter=cache,
    ) is True

    assert events[:2] == ["dashboard_lock", "config_lock"]
    assert len(cache.deleted_patterns) == 1
    assert "roi-chart" in cache.deleted_patterns[0]
    assert ":301:" in cache.deleted_patterns[0]


def test_reorder_locates_all_charts_before_version_validation(
    session: Session,
) -> None:
    user = prepare_chart_context(session)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    seed_roi_chart(session, tenant_id=22, dashboard_id=301, chart_id=902)

    request = RoiChartReorderRequest(
        items=[
            RoiChartOrderItem(id="901", sort=1, layout_span="half", version=999),
            RoiChartOrderItem(id="902", sort=2, layout_span="third", version=1),
        ]
    )

    assert_http_error(404, lambda: reorder_roi_charts(session, user, 301, request))


@pytest.mark.parametrize(
    "item",
    [
        RoiChartOrderItem.model_construct(
            id="901", sort=1, layout_span="quarter", version=1
        ),
        RoiChartOrderItem.model_construct(
            id="901", sort="first", layout_span="half", version=1
        ),
    ],
)
def test_reorder_service_rejects_invalid_layout_or_sort(
    session: Session,
    item,
) -> None:
    user = prepare_chart_context(session)
    chart = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    request = RoiChartReorderRequest.model_construct(items=[item])

    assert_http_error(400, lambda: reorder_roi_charts(session, user, 301, request))
    session.refresh(chart)
    assert (chart.sort, chart.layout_span, chart.version) == (0, "full", 1)


def test_reorder_cross_tenant_wins_over_duplicate_error(session: Session) -> None:
    user = prepare_chart_context(session)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    seed_roi_chart(session, tenant_id=22, dashboard_id=301, chart_id=902)
    request = RoiChartReorderRequest(
        items=[
            RoiChartOrderItem(id="901", sort=1, layout_span="half", version=1),
            RoiChartOrderItem(id="901", sort=2, layout_span="third", version=1),
            RoiChartOrderItem(id="902", sort=3, layout_span="full", version=1),
        ]
    )

    assert_http_error(404, lambda: reorder_roi_charts(session, user, 301, request))


def test_reorder_permission_wins_over_duplicate_error(session: Session) -> None:
    user = prepare_chart_context(session, grant=False)
    seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    request = RoiChartReorderRequest(
        items=[
            RoiChartOrderItem(id="901", sort=1, layout_span="half", version=1),
            RoiChartOrderItem(id="901", sort=2, layout_span="third", version=1),
        ]
    )

    assert_http_error(403, lambda: reorder_roi_charts(session, user, 301, request))


def test_reorder_returns_structure_without_calling_full_chart_list(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = prepare_chart_context(session)
    chart = seed_roi_chart(session, tenant_id=11, dashboard_id=301, chart_id=901)
    monkeypatch.setattr(
        "apps.roi_dashboard.service.list_roi_charts",
        lambda *_args, **_kwargs: pytest.fail("提交后不应调用完整图表列表"),
    )

    result = reorder_roi_charts(
        session,
        user,
        301,
        RoiChartReorderRequest(
            items=[
                RoiChartOrderItem(id="901", sort=4, layout_span="third", version=1)
            ]
        ),
        cache_adapter=FakeRoiChartCache(),
    )

    session.refresh(chart)
    assert (chart.sort, chart.layout_span, chart.version) == (4, "third", 2)
    assert result[0]["sort"] == 4
    assert result[0]["layout_span"] == "third"
    assert result[0]["version"] == 2
    assert result[0]["query_result"] is None
