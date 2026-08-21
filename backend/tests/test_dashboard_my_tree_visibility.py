"""验证“我的看板”不会在空树回退时混入推荐看板。"""

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardTree,
    DashboardBaseResponse,
    QueryDashboard,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(
        engine,
        tables=[CoreDashboard.__table__, CoreDashboardTree.__table__],
    )
    return Session(engine)


def _dashboard(dashboard_id: str, name: str, *, is_default: int | None, node_type: str) -> CoreDashboard:
    return CoreDashboard(
        id=dashboard_id,
        tenant_id=100,
        name=name,
        pid="root",
        datasource=10,
        node_type=node_type,
        type="dashboard",
        status=1,
        is_default=is_default,
        delete_flag=0,
    )


def _patch_list_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_service, "get_bound_external_mcp_id_for_tenant", lambda *_args: None)
    monkeypatch.setattr(dashboard_service, "get_accessible_datasource_ids", lambda *_args: [10])
    monkeypatch.setattr(dashboard_service, "_dashboard_list_visibility_filter", lambda *_args: None)
    monkeypatch.setattr(dashboard_service, "_active_dashboard_share_map_for_user", lambda *_args: {})
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_base_response",
        lambda _session, _user, record, *_args, **_kwargs: DashboardBaseResponse(
            id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            pid=record.pid,
            datasource=record.datasource,
            node_type=record.node_type,
            leaf=record.node_type == "leaf",
            is_default=bool(record.is_default),
            sort=record.sort or 0,
        ),
    )


def _list_my_tree(session: Session) -> list[DashboardBaseResponse]:
    user = SimpleNamespace(id=200, tenant_id=100, system_role="viewer", isAdmin=False)
    return dashboard_service.list_resource(session, QueryDashboard(), user)


def test_empty_my_tree_excludes_recommended_leaf_but_keeps_legacy_personal_records(monkeypatch) -> None:
    _patch_list_dependencies(monkeypatch)
    with _session() as session:
        session.add_all(
            [
                _dashboard("recommended", "推荐看板", is_default=1, node_type="leaf"),
                _dashboard("personal", "个人看板", is_default=0, node_type="leaf"),
                _dashboard("folder", "个人目录", is_default=0, node_type="folder"),
                _dashboard("legacy", "历史个人看板", is_default=None, node_type="leaf"),
            ]
        )
        session.commit()

        tree = _list_my_tree(session)

    assert {node.id for node in tree} == {"folder", "legacy", "personal"}
    assert "recommended" not in {node.id for node in tree}


def test_explicit_my_tree_positions_remain_scope_authority(monkeypatch) -> None:
    _patch_list_dependencies(monkeypatch)
    with _session() as session:
        personal = _dashboard("personal", "个人看板", is_default=0, node_type="leaf")
        recommended = _dashboard("recommended", "推荐看板", is_default=1, node_type="leaf")
        session.add_all(
            [
                personal,
                recommended,
                CoreDashboardTree(
                    id="tree-personal",
                    tenant_id=100,
                    scope="my",
                    dashboard_id=personal.id,
                    parent_id="root",
                    sort=1,
                ),
                CoreDashboardTree(
                    id="tree-recommended",
                    tenant_id=100,
                    scope="default",
                    dashboard_id=recommended.id,
                    parent_id="root",
                    sort=1,
                ),
            ]
        )
        session.commit()

        tree = _list_my_tree(session)

    assert [node.id for node in tree] == ["personal"]
