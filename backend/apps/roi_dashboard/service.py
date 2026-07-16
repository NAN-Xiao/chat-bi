"""ROI 配置和工作空间共享看板服务。"""

import time

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from apps.datasource.models.datasource import CoreDatasource
from apps.roi_dashboard.models import (
    CoreRoiDashboard,
    CoreRoiDashboardChart,
    CoreRoiWorkspaceConfig,
)
from apps.roi_dashboard.permissions import (
    has_roi_datasource_access,
    require_roi_workspace_admin,
)
from apps.roi_dashboard.schemas import (
    RoiConfigResponse,
    RoiConfigUpdate,
    RoiDashboardCreate,
    RoiDashboardReorderRequest,
    RoiDashboardUpdate,
)
from common.core.deps import CurrentUser, SessionDep

VERSION_CONFLICT_MESSAGE = "数据已被其他人修改，请刷新后重试"
CONFIG_CONFLICT_MESSAGE = "ROI 配置已被其他人创建或修改，请刷新后重试"


def _now() -> int:
    return int(time.time())


def _tenant_id(current_user: CurrentUser) -> int:
    return require_roi_workspace_admin(current_user).management_tenant_id


def _operator_id(current_user: CurrentUser) -> int:
    return int(current_user.id)


def _active_config_statement(tenant_id: int):
    return select(CoreRoiWorkspaceConfig).where(
        CoreRoiWorkspaceConfig.tenant_id == tenant_id,
        CoreRoiWorkspaceConfig.deleted.is_(False),
    )


def lock_active_roi_config(
    session: SessionDep,
    tenant_id: int,
) -> CoreRoiWorkspaceConfig | None:
    """锁定当前租户活动配置，供换源与图表写入共享同一事务协议。"""
    return session.exec(_active_config_statement(tenant_id).with_for_update()).first()


def _active_dashboard_statement(tenant_id: int):
    return select(CoreRoiDashboard).where(
        CoreRoiDashboard.tenant_id == tenant_id,
        CoreRoiDashboard.deleted.is_(False),
        CoreRoiDashboard.status == 1,
    )


def _load_dashboard_or_404(
    session: SessionDep,
    tenant_id: int,
    dashboard_id: int,
) -> CoreRoiDashboard:
    record = session.exec(
        _active_dashboard_statement(tenant_id).where(
            CoreRoiDashboard.id == dashboard_id
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="ROI 看板不存在")
    return record


def _config_response(
    session: SessionDep,
    record: CoreRoiWorkspaceConfig,
) -> RoiConfigResponse:
    datasource_name = session.exec(
        select(CoreDatasource.name).where(CoreDatasource.id == record.datasource_id)
    ).first()
    return RoiConfigResponse.model_validate(
        {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "datasource_id": record.datasource_id,
            "datasource_name": datasource_name,
            "version": record.version,
        }
    )


def get_roi_config(
    session: SessionDep,
    current_user: CurrentUser,
) -> RoiConfigResponse | None:
    """读取当前工作空间共享的 ROI 数据源配置。"""
    tenant_id = _tenant_id(current_user)
    record = session.exec(_active_config_statement(tenant_id)).first()
    return None if record is None else _config_response(session, record)


def set_roi_config(
    session: SessionDep,
    current_user: CurrentUser,
    request: RoiConfigUpdate,
) -> RoiConfigResponse:
    """创建或按版本更新当前工作空间的 ROI 数据源配置。"""
    tenant_id = _tenant_id(current_user)
    if not has_roi_datasource_access(session, current_user, request.datasource_id):
        raise HTTPException(status_code=403, detail="当前账号无此 ROI 数据源权限")

    record = lock_active_roi_config(session, tenant_id)
    now = _now()
    operator_id = _operator_id(current_user)
    if record is None:
        if request.version is not None:
            raise HTTPException(status_code=409, detail=CONFIG_CONFLICT_MESSAGE)
        record = CoreRoiWorkspaceConfig(
            tenant_id=tenant_id,
            datasource_id=request.datasource_id,
            version=1,
            create_by=operator_id,
            update_by=operator_id,
            create_time=now,
            update_time=now,
            deleted=False,
        )
        session.add(record)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail=CONFIG_CONFLICT_MESSAGE) from exc
        session.refresh(record)
        return _config_response(session, record)

    if request.version is None or request.version != record.version:
        raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)

    if record.datasource_id != request.datasource_id:
        active_chart_count = session.exec(
            select(func.count(CoreRoiDashboardChart.id)).where(
                CoreRoiDashboardChart.tenant_id == tenant_id,
                CoreRoiDashboardChart.deleted.is_(False),
                CoreRoiDashboardChart.status == 1,
            )
        ).one()
        if active_chart_count:
            raise HTTPException(
                status_code=409,
                detail="已有 ROI 图表时不能更换数据源",
            )

    result = session.exec(
        update(CoreRoiWorkspaceConfig)
        .where(
            CoreRoiWorkspaceConfig.id == record.id,
            CoreRoiWorkspaceConfig.tenant_id == tenant_id,
            CoreRoiWorkspaceConfig.deleted.is_(False),
            CoreRoiWorkspaceConfig.version == request.version,
        )
        .values(
            datasource_id=request.datasource_id,
            version=request.version + 1,
            update_by=operator_id,
            update_time=now,
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
    session.commit()
    updated = session.exec(_active_config_statement(tenant_id)).first()
    if updated is None:
        raise HTTPException(status_code=404, detail="ROI 配置不存在")
    return _config_response(session, updated)


def list_roi_dashboards(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[CoreRoiDashboard]:
    """按稳定顺序读取当前工作空间的全部活动 ROI 看板。"""
    tenant_id = _tenant_id(current_user)
    return list(
        session.exec(
            _active_dashboard_statement(tenant_id).order_by(
                CoreRoiDashboard.sort.asc(),
                CoreRoiDashboard.create_time.asc(),
                CoreRoiDashboard.id.asc(),
            )
        ).all()
    )


def create_roi_dashboard(
    session: SessionDep,
    current_user: CurrentUser,
    request: RoiDashboardCreate,
) -> CoreRoiDashboard:
    """在当前工作空间创建共享 ROI 看板。"""
    tenant_id = _tenant_id(current_user)
    now = _now()
    operator_id = _operator_id(current_user)
    record = CoreRoiDashboard(
        tenant_id=tenant_id,
        name=request.name,
        sort=0,
        status=1,
        version=1,
        create_by=operator_id,
        update_by=operator_id,
        create_time=now,
        update_time=now,
        deleted=False,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def update_roi_dashboard(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: int,
    request: RoiDashboardUpdate,
) -> CoreRoiDashboard:
    """按乐观锁版本更新当前工作空间的 ROI 看板。"""
    tenant_id = _tenant_id(current_user)
    record = _load_dashboard_or_404(session, tenant_id, dashboard_id)
    if record.version != request.version:
        raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)

    values: dict[str, object] = {
        "version": request.version + 1,
        "update_by": _operator_id(current_user),
        "update_time": _now(),
    }
    if request.name is not None:
        values["name"] = request.name
    if request.status is not None:
        values["status"] = request.status

    result = session.exec(
        update(CoreRoiDashboard)
        .where(
            CoreRoiDashboard.id == dashboard_id,
            CoreRoiDashboard.tenant_id == tenant_id,
            CoreRoiDashboard.deleted.is_(False),
            CoreRoiDashboard.status == 1,
            CoreRoiDashboard.version == request.version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
    session.commit()
    updated = session.exec(
        select(CoreRoiDashboard).where(
            CoreRoiDashboard.id == dashboard_id,
            CoreRoiDashboard.tenant_id == tenant_id,
            CoreRoiDashboard.deleted.is_(False),
        )
    ).first()
    if updated is None:
        raise HTTPException(status_code=404, detail="ROI 看板不存在")
    return updated


def delete_roi_dashboard(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: int,
) -> bool:
    """在同一事务中软删除看板及其活动图表。"""
    tenant_id = _tenant_id(current_user)
    _load_dashboard_or_404(session, tenant_id, dashboard_id)
    now = _now()
    operator_id = _operator_id(current_user)
    session.exec(
        update(CoreRoiDashboardChart)
        .where(
            CoreRoiDashboardChart.tenant_id == tenant_id,
            CoreRoiDashboardChart.roi_dashboard_id == dashboard_id,
            CoreRoiDashboardChart.deleted.is_(False),
            CoreRoiDashboardChart.status == 1,
        )
        .values(deleted=True, update_by=operator_id, update_time=now)
    )
    session.exec(
        update(CoreRoiDashboard)
        .where(
            CoreRoiDashboard.id == dashboard_id,
            CoreRoiDashboard.tenant_id == tenant_id,
            CoreRoiDashboard.deleted.is_(False),
            CoreRoiDashboard.status == 1,
        )
        .values(deleted=True, update_by=operator_id, update_time=now)
    )
    session.commit()
    return True


def reorder_roi_dashboards(
    session: SessionDep,
    current_user: CurrentUser,
    request: RoiDashboardReorderRequest,
) -> list[CoreRoiDashboard]:
    """在一个事务内按版本重排当前工作空间的 ROI 看板。"""
    tenant_id = _tenant_id(current_user)
    records: list[tuple[CoreRoiDashboard, object]] = []
    seen_ids: set[int] = set()
    for item in request.items:
        dashboard_id = int(item.id)
        if dashboard_id in seen_ids:
            raise HTTPException(status_code=400, detail="ROI 看板排序项不能重复")
        seen_ids.add(dashboard_id)
        record = _load_dashboard_or_404(session, tenant_id, dashboard_id)
        if record.version != item.version:
            raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
        records.append((record, item))

    now = _now()
    operator_id = _operator_id(current_user)
    for record, item in records:
        result = session.exec(
            update(CoreRoiDashboard)
            .where(
                CoreRoiDashboard.id == record.id,
                CoreRoiDashboard.tenant_id == tenant_id,
                CoreRoiDashboard.deleted.is_(False),
                CoreRoiDashboard.status == 1,
                CoreRoiDashboard.version == item.version,
            )
            .values(
                sort=item.sort,
                version=item.version + 1,
                update_by=operator_id,
                update_time=now,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
    session.commit()
    return list_roi_dashboards(session, current_user)
