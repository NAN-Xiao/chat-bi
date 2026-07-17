"""独立 ROI 看板 API。"""

from fastapi import APIRouter, Depends
from sqlmodel import select

from apps.datasource.models.datasource import CoreDatasource
from apps.roi_dashboard.permissions import list_roi_accessible_datasource_ids
from apps.roi_dashboard.schemas import (
    RoiChartCreate,
    RoiChartListResponse,
    RoiChartPreviewRequest,
    RoiChartPreviewResponse,
    RoiChartReorderRequest,
    RoiChartResponse,
    RoiChartUpdate,
    RoiConfigResponse,
    RoiConfigUpdate,
    RoiDashboardCreate,
    RoiDashboardReorderRequest,
    RoiDashboardResponse,
    RoiDashboardUpdate,
    RoiDatasourceOption,
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
    set_roi_config,
    update_roi_chart,
    update_roi_dashboard,
)
from apps.system.schemas.business_access import require_chatbi_business_user
from common.core.deps import CurrentUser, SessionDep

router = APIRouter(
    tags=["ROI Dashboard"],
    prefix="/dashboard/roi",
    dependencies=[Depends(require_chatbi_business_user)],
)


@router.get("/datasources", response_model=list[RoiDatasourceOption])
def list_roi_datasources_api(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[RoiDatasourceOption]:
    datasource_ids = list_roi_accessible_datasource_ids(session, current_user)
    if not datasource_ids:
        return []
    rows = session.exec(
        select(
            CoreDatasource.id,
            CoreDatasource.name,
            CoreDatasource.type,
            CoreDatasource.type_name,
        )
        .where(CoreDatasource.id.in_(datasource_ids))
        .order_by(CoreDatasource.name.asc(), CoreDatasource.id.asc())
    ).all()
    return [RoiDatasourceOption.model_validate(row) for row in rows]


@router.get("/config", response_model=RoiConfigResponse | None)
def get_roi_config_api(session: SessionDep, current_user: CurrentUser):
    return get_roi_config(session, current_user)


@router.put("/config", response_model=RoiConfigResponse)
def set_roi_config_api(
    request: RoiConfigUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    return set_roi_config(session, current_user, request)


@router.get("/list", response_model=list[RoiDashboardResponse])
def list_roi_dashboards_api(session: SessionDep, current_user: CurrentUser):
    return list_roi_dashboards(session, current_user)


@router.post("", response_model=RoiDashboardResponse)
def create_roi_dashboard_api(
    request: RoiDashboardCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    return create_roi_dashboard(session, current_user, request)


@router.patch("/{dashboard_id}", response_model=RoiDashboardResponse)
def update_roi_dashboard_api(
    dashboard_id: str,
    request: RoiDashboardUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    return update_roi_dashboard(session, current_user, dashboard_id, request)


@router.delete("/{dashboard_id}", response_model=bool)
def delete_roi_dashboard_api(
    dashboard_id: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    return delete_roi_dashboard(session, current_user, dashboard_id)


@router.post("/reorder", response_model=list[RoiDashboardResponse])
def reorder_roi_dashboards_api(
    request: RoiDashboardReorderRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    return reorder_roi_dashboards(session, current_user, request)


@router.post(
    "/{dashboard_id}/charts/preview",
    response_model=RoiChartPreviewResponse,
)
def preview_chart_api(
    dashboard_id: str,
    request: RoiChartPreviewRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    return preview_roi_chart(session, current_user, dashboard_id, request)


@router.get(
    "/{dashboard_id}/charts",
    response_model=list[RoiChartListResponse],
)
def list_roi_charts_api(
    dashboard_id: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    return list_roi_charts(session, current_user, dashboard_id)


@router.post("/{dashboard_id}/charts", response_model=RoiChartResponse)
def create_roi_chart_api(
    dashboard_id: str,
    request: RoiChartCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    return create_roi_chart(session, current_user, dashboard_id, request)


@router.put(
    "/{dashboard_id}/charts/{chart_id}",
    response_model=RoiChartResponse,
)
def update_roi_chart_api(
    dashboard_id: str,
    chart_id: str,
    request: RoiChartUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    return update_roi_chart(session, current_user, dashboard_id, chart_id, request)


@router.delete("/{dashboard_id}/charts/{chart_id}", response_model=bool)
def delete_roi_chart_api(
    dashboard_id: str,
    chart_id: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    return delete_roi_chart(session, current_user, dashboard_id, chart_id)


@router.post(
    "/{dashboard_id}/charts/reorder",
    response_model=list[RoiChartListResponse],
)
def reorder_roi_charts_api(
    dashboard_id: str,
    request: RoiChartReorderRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    return reorder_roi_charts(session, current_user, dashboard_id, request)
