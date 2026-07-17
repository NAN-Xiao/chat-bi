"""ROI 配置、共享看板和图表服务。"""

import hashlib
import json
import time
from dataclasses import asdict
from typing import Any, Protocol

from fastapi import HTTPException
from redis import Redis
from redis.exceptions import RedisError
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
from apps.roi_dashboard.query_executor import RoiQueryResult, execute_roi_read_query
from apps.roi_dashboard.schemas import (
    RoiChartCreate,
    RoiChartPreviewRequest,
    RoiChartReorderRequest,
    RoiChartUpdate,
    RoiConfigResponse,
    RoiConfigUpdate,
    RoiDashboardCreate,
    RoiDashboardReorderRequest,
    RoiDashboardUpdate,
)
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.core.redis_client import build_redis_url, user_redis_key
from common.utils.utils import AppLogUtil

VERSION_CONFLICT_MESSAGE = "数据已被其他人修改，请刷新后重试"
CONFIG_CONFLICT_MESSAGE = "ROI 配置已被其他人创建或修改，请刷新后重试"
ROI_DATASOURCE_PERMISSION_MESSAGE = "当前账号无此数据源权限"


class RoiChartCacheAdapter(Protocol):
    """ROI 图表缓存的最小可注入接口。"""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any]) -> None: ...

    def delete_pattern(self, pattern: str) -> None: ...


class RedisRoiChartCache:
    """独立 Redis ROI 缓存；连接失败时不使用普通看板缓存兜底。"""

    def __init__(self) -> None:
        self._client: Redis | None = None

    def _redis(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(
                build_redis_url(),
                decode_responses=True,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
                health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
            )
        return self._client

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            value = self._redis().get(key)
            return None if value is None else json.loads(value)
        except (RedisError, ValueError, TypeError) as exc:
            AppLogUtil.warning(f"ROI chart cache read failed: {type(exc).__name__}")
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            self._redis().setex(
                key,
                settings.DASHBOARD_SQL_PREVIEW_CACHE_TTL_SECONDS,
                json.dumps(value, ensure_ascii=False, default=str),
            )
        except (RedisError, ValueError, TypeError) as exc:
            AppLogUtil.warning(f"ROI chart cache write failed: {type(exc).__name__}")

    def delete_pattern(self, pattern: str) -> None:
        try:
            client = self._redis()
            keys = list(client.scan_iter(match=pattern, count=200))
            if keys:
                client.delete(*keys)
        except RedisError as exc:
            AppLogUtil.warning(f"ROI chart cache invalidation failed: {type(exc).__name__}")


_ROI_CHART_CACHE = RedisRoiChartCache()


def _now() -> int:
    return int(time.time())


def _tenant_id(current_user: CurrentUser) -> int:
    return require_roi_workspace_admin(current_user).management_tenant_id


def _operator_id(current_user: CurrentUser) -> int:
    return int(current_user.id)


def _parse_path_id(value: str | int, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{label} ID 不合法") from exc
    if parsed <= 0:
        raise HTTPException(status_code=400, detail=f"{label} ID 不合法")
    return parsed


def _cache(cache_adapter: RoiChartCacheAdapter | None) -> RoiChartCacheAdapter:
    return cache_adapter or _ROI_CHART_CACHE


def _sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def roi_chart_cache_key(
    tenant_id: int,
    user_id: int,
    datasource_id: int,
    dashboard_id: int,
    chart_id: int,
    version: int,
    sql_hash: str,
) -> str:
    """构造完整隔离的 ROI 图表缓存键。"""
    return user_redis_key(
        tenant_id,
        user_id,
        "roi-chart",
        datasource_id,
        dashboard_id,
        chart_id,
        version,
        sql_hash,
    )


def _roi_chart_cache_pattern(
    tenant_id: int,
    *,
    datasource_id: int | str = "*",
    dashboard_id: int | str = "*",
    chart_id: int | str = "*",
) -> str:
    return user_redis_key(
        tenant_id,
        "*",
        "roi-chart",
        datasource_id,
        dashboard_id,
        chart_id,
        "*",
        "*",
    )


def _invalidate_roi_chart_cache(
    cache_adapter: RoiChartCacheAdapter | None,
    tenant_id: int,
    *,
    datasource_id: int | str = "*",
    dashboard_id: int | str = "*",
    chart_id: int | str = "*",
) -> None:
    _cache(cache_adapter).delete_pattern(
        _roi_chart_cache_pattern(
            tenant_id,
            datasource_id=datasource_id,
            dashboard_id=dashboard_id,
            chart_id=chart_id,
        )
    )


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


def lock_active_roi_dashboard(
    session: SessionDep,
    tenant_id: int,
    dashboard_id: int,
) -> CoreRoiDashboard | None:
    """锁定活动看板；create/delete 统一先锁看板、再锁 ROI 配置。"""
    return session.exec(
        _active_dashboard_statement(tenant_id)
        .where(CoreRoiDashboard.id == dashboard_id)
        .with_for_update()
    ).first()


def _config_response(
    session: SessionDep,
    current_user: CurrentUser,
    record: CoreRoiWorkspaceConfig,
) -> RoiConfigResponse:
    datasource_name = session.exec(
        select(CoreDatasource.name).where(CoreDatasource.id == record.datasource_id)
    ).first()
    has_access = has_roi_datasource_access(session, current_user, record.datasource_id)
    return RoiConfigResponse.model_validate(
        {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "datasource_id": record.datasource_id,
            "datasource_name": datasource_name,
            "version": record.version,
            "can_execute": has_access,
            "can_edit": has_access,
        }
    )


def get_roi_config(
    session: SessionDep,
    current_user: CurrentUser,
) -> RoiConfigResponse | None:
    """读取当前工作空间共享的 ROI 数据源配置。"""
    tenant_id = _tenant_id(current_user)
    record = session.exec(_active_config_statement(tenant_id)).first()
    return None if record is None else _config_response(session, current_user, record)


def set_roi_config(
    session: SessionDep,
    current_user: CurrentUser,
    request: RoiConfigUpdate,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
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
        _invalidate_roi_chart_cache(cache_adapter, tenant_id)
        return _config_response(session, current_user, record)

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
    _invalidate_roi_chart_cache(cache_adapter, tenant_id)
    updated = session.exec(_active_config_statement(tenant_id)).first()
    if updated is None:
        raise HTTPException(status_code=404, detail="ROI 配置不存在")
    return _config_response(session, current_user, updated)


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
    dashboard_id: str | int,
    request: RoiDashboardUpdate,
) -> CoreRoiDashboard:
    """按乐观锁版本更新当前工作空间的 ROI 看板。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
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
    dashboard_id: str | int,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> bool:
    """在同一事务中软删除看板及其活动图表。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    dashboard = lock_active_roi_dashboard(session, tenant_id, dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="ROI 看板不存在")
    config = lock_active_roi_config(session, tenant_id)
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
    _invalidate_roi_chart_cache(
        cache_adapter,
        tenant_id,
        datasource_id=(config.datasource_id if config is not None else "*"),
        dashboard_id=dashboard_id,
    )
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


def _load_chart_or_404(
    session: SessionDep,
    tenant_id: int,
    dashboard_id: int,
    chart_id: int,
) -> CoreRoiDashboardChart:
    record = session.exec(
        select(CoreRoiDashboardChart).where(
            CoreRoiDashboardChart.id == chart_id,
            CoreRoiDashboardChart.tenant_id == tenant_id,
            CoreRoiDashboardChart.roi_dashboard_id == dashboard_id,
            CoreRoiDashboardChart.deleted.is_(False),
            CoreRoiDashboardChart.status == 1,
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="ROI 图表不存在")
    return record


def _load_config_or_409(
    session: SessionDep,
    tenant_id: int,
) -> CoreRoiWorkspaceConfig:
    config = session.exec(_active_config_statement(tenant_id)).first()
    if config is None:
        raise HTTPException(status_code=409, detail="当前工作空间尚未配置 ROI 数据源")
    return config


def _require_roi_chart_write_access(
    session: SessionDep,
    current_user: CurrentUser,
    tenant_id: int,
) -> CoreRoiWorkspaceConfig:
    config = _load_config_or_409(session, tenant_id)
    if not has_roi_datasource_access(session, current_user, config.datasource_id):
        raise HTTPException(status_code=403, detail=ROI_DATASOURCE_PERMISSION_MESSAGE)
    return config


def _require_successful_query(result: RoiQueryResult) -> None:
    if result.status != "success":
        raise HTTPException(
            status_code=400,
            detail=result.message or "ROI SQL 执行失败，图表未保存",
        )


def preview_roi_chart(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: str | int,
    request: RoiChartPreviewRequest,
) -> RoiQueryResult:
    """执行图表草稿 SQL，但不创建或修改图表。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    _load_dashboard_or_404(session, tenant_id, dashboard_id)
    return execute_roi_read_query(session, current_user, request.sql)


def list_roi_charts(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: str | int,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> list[dict[str, Any]]:
    """读取图表结构；只有当前账号仍有数据源权限时才读缓存或执行。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    _load_dashboard_or_404(session, tenant_id, dashboard_id)
    charts = list(
        session.exec(
            select(CoreRoiDashboardChart)
            .where(
                CoreRoiDashboardChart.tenant_id == tenant_id,
                CoreRoiDashboardChart.roi_dashboard_id == dashboard_id,
                CoreRoiDashboardChart.deleted.is_(False),
                CoreRoiDashboardChart.status == 1,
            )
            .order_by(
                CoreRoiDashboardChart.sort.asc(),
                CoreRoiDashboardChart.create_time.asc(),
                CoreRoiDashboardChart.id.asc(),
            )
        ).all()
    )
    config = session.exec(_active_config_statement(tenant_id)).first()
    can_execute = bool(
        config is not None
        and has_roi_datasource_access(session, current_user, config.datasource_id)
    )
    permission_error = (
        None
        if can_execute
        else (
            ROI_DATASOURCE_PERMISSION_MESSAGE
            if config is not None
            else "当前工作空间尚未配置 ROI 数据源"
        )
    )
    result: list[dict[str, Any]] = []
    for chart in charts:
        item = chart.model_dump()
        item.update(
            can_execute=can_execute,
            can_edit=can_execute,
            error=permission_error,
            query_result=None,
        )
        if not can_execute:
            result.append(item)
            continue

        key = roi_chart_cache_key(
            tenant_id,
            _operator_id(current_user),
            int(config.datasource_id),
            dashboard_id,
            int(chart.id),
            chart.version,
            _sql_hash(chart.sql),
        )
        cached = _cache(cache_adapter).get(key)
        if cached is not None:
            item["query_result"] = cached
            result.append(item)
            continue

        query_started_at = time.perf_counter()
        try:
            query_result = execute_roi_read_query(session, current_user, chart.sql)
            query_payload = asdict(query_result)
            item["query_result"] = query_payload
            if query_result.status == "success":
                _cache(cache_adapter).set(key, query_payload)
            else:
                item["error"] = query_result.message or "ROI SQL 执行失败"
                _log_roi_chart_query_failure(
                    tenant_id=tenant_id,
                    user_id=_operator_id(current_user),
                    datasource_id=int(config.datasource_id),
                    chart_id=int(chart.id),
                    started_at=query_started_at,
                    error_type="FailedResult",
                )
        except Exception as exc:
            message = (
                str(exc.detail)
                if isinstance(exc, HTTPException)
                else "ROI 查询执行失败"
            )
            item["error"] = message
            item["query_result"] = asdict(
                RoiQueryResult(status="failed", message=message)
            )
            _log_roi_chart_query_failure(
                tenant_id=tenant_id,
                user_id=_operator_id(current_user),
                datasource_id=int(config.datasource_id),
                chart_id=int(chart.id),
                started_at=query_started_at,
                error_type=type(exc).__name__,
            )
        result.append(item)
    return result


def _log_roi_chart_query_failure(
    *,
    tenant_id: int,
    user_id: int,
    datasource_id: int,
    chart_id: int,
    started_at: float,
    error_type: str,
) -> None:
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    AppLogUtil.warning(
        "ROI chart query failed: "
        f"tenant_id={tenant_id}, user_id={user_id}, datasource_id={datasource_id}, "
        f"chart_id={chart_id}, elapsed_ms={elapsed_ms}, status=failed, "
        f"error_type={error_type}"
    )


def create_roi_chart(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: str | int,
    request: RoiChartCreate,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> CoreRoiDashboardChart:
    """锁定统一配置后重新执行 SQL，成功才创建图表。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    dashboard = lock_active_roi_dashboard(session, tenant_id, dashboard_id)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="ROI 看板不存在")
    config = lock_active_roi_config(session, tenant_id)
    if config is None:
        raise HTTPException(status_code=409, detail="当前工作空间尚未配置 ROI 数据源")
    if not has_roi_datasource_access(session, current_user, config.datasource_id):
        raise HTTPException(status_code=403, detail=ROI_DATASOURCE_PERMISSION_MESSAGE)
    query_result = execute_roi_read_query(session, current_user, request.sql)
    _require_successful_query(query_result)

    now = _now()
    operator_id = _operator_id(current_user)
    record = CoreRoiDashboardChart(
        tenant_id=tenant_id,
        roi_dashboard_id=dashboard_id,
        title=request.title,
        sql=request.sql,
        chart_type=request.chart_type,
        chart_config=request.chart_config,
        layout_span=request.layout_span,
        sort=request.sort,
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
    _invalidate_roi_chart_cache(
        cache_adapter,
        tenant_id,
        datasource_id=config.datasource_id,
        dashboard_id=dashboard_id,
        chart_id=record.id,
    )
    return record


def update_roi_chart(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: str | int,
    chart_id: str | int,
    request: RoiChartUpdate,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> CoreRoiDashboardChart:
    """重新执行提交 SQL 后按版本原子更新活动图表。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    chart_id = _parse_path_id(chart_id, "ROI 图表")
    _load_dashboard_or_404(session, tenant_id, dashboard_id)
    record = _load_chart_or_404(session, tenant_id, dashboard_id, chart_id)
    config = _require_roi_chart_write_access(session, current_user, tenant_id)
    if record.version != request.version:
        raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
    query_result = execute_roi_read_query(session, current_user, request.sql)
    _require_successful_query(query_result)

    result = session.exec(
        update(CoreRoiDashboardChart)
        .where(
            CoreRoiDashboardChart.id == chart_id,
            CoreRoiDashboardChart.tenant_id == tenant_id,
            CoreRoiDashboardChart.roi_dashboard_id == dashboard_id,
            CoreRoiDashboardChart.deleted.is_(False),
            CoreRoiDashboardChart.status == 1,
            CoreRoiDashboardChart.version == request.version,
        )
        .values(
            title=request.title,
            sql=request.sql,
            chart_type=request.chart_type,
            chart_config=request.chart_config,
            layout_span=request.layout_span,
            sort=request.sort,
            version=request.version + 1,
            update_by=_operator_id(current_user),
            update_time=_now(),
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
    session.commit()
    _invalidate_roi_chart_cache(
        cache_adapter,
        tenant_id,
        datasource_id=config.datasource_id,
        dashboard_id=dashboard_id,
        chart_id=chart_id,
    )
    return _load_chart_or_404(session, tenant_id, dashboard_id, chart_id)


def delete_roi_chart(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: str | int,
    chart_id: str | int,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> bool:
    """按租户和看板边界软删除活动图表。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    chart_id = _parse_path_id(chart_id, "ROI 图表")
    _load_dashboard_or_404(session, tenant_id, dashboard_id)
    _load_chart_or_404(session, tenant_id, dashboard_id, chart_id)
    config = _require_roi_chart_write_access(session, current_user, tenant_id)
    session.exec(
        update(CoreRoiDashboardChart)
        .where(
            CoreRoiDashboardChart.id == chart_id,
            CoreRoiDashboardChart.tenant_id == tenant_id,
            CoreRoiDashboardChart.roi_dashboard_id == dashboard_id,
            CoreRoiDashboardChart.deleted.is_(False),
            CoreRoiDashboardChart.status == 1,
        )
        .values(
            deleted=True,
            update_by=_operator_id(current_user),
            update_time=_now(),
        )
    )
    session.commit()
    _invalidate_roi_chart_cache(
        cache_adapter,
        tenant_id,
        datasource_id=config.datasource_id,
        dashboard_id=dashboard_id,
        chart_id=chart_id,
    )
    return True


def reorder_roi_charts(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_id: str | int,
    request: RoiChartReorderRequest,
    *,
    cache_adapter: RoiChartCacheAdapter | None = None,
) -> list[dict[str, Any]]:
    """全量预验证后在单事务中更新图表顺序、宽度和版本。"""
    tenant_id = _tenant_id(current_user)
    dashboard_id = _parse_path_id(dashboard_id, "ROI 看板")
    _load_dashboard_or_404(session, tenant_id, dashboard_id)
    parsed_items: list[tuple[int, Any]] = []
    for item in request.items:
        try:
            chart_id = int(item.id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="ROI 图表 ID 不合法") from exc
        parsed_items.append((chart_id, item))

    records_by_id: dict[int, CoreRoiDashboardChart] = {}
    for chart_id, _item in parsed_items:
        if chart_id not in records_by_id:
            records_by_id[chart_id] = _load_chart_or_404(
                session,
                tenant_id,
                dashboard_id,
                chart_id,
            )

    config = _require_roi_chart_write_access(session, current_user, tenant_id)
    if len(records_by_id) != len(parsed_items):
        raise HTTPException(status_code=400, detail="ROI 图表排序项不能重复")

    records = [
        (records_by_id[chart_id], item)
        for chart_id, item in parsed_items
    ]
    for record, item in records:
        if item.layout_span not in {"full", "half", "third"}:
            raise HTTPException(status_code=400, detail="ROI 图表宽度不合法")
        if type(item.sort) is not int:
            raise HTTPException(status_code=400, detail="ROI 图表排序值不合法")
        if record.version != item.version:
            raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)

    now = _now()
    operator_id = _operator_id(current_user)
    response_items: list[dict[str, Any]] = []
    for record, item in records:
        result = session.exec(
            update(CoreRoiDashboardChart)
            .where(
                CoreRoiDashboardChart.id == record.id,
                CoreRoiDashboardChart.tenant_id == tenant_id,
                CoreRoiDashboardChart.roi_dashboard_id == dashboard_id,
                CoreRoiDashboardChart.deleted.is_(False),
                CoreRoiDashboardChart.status == 1,
                CoreRoiDashboardChart.version == item.version,
            )
            .values(
                sort=item.sort,
                layout_span=item.layout_span,
                version=item.version + 1,
                update_by=operator_id,
                update_time=now,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(status_code=409, detail=VERSION_CONFLICT_MESSAGE)
        response_item = record.model_dump()
        response_item.update(
            sort=item.sort,
            layout_span=item.layout_span,
            version=item.version + 1,
            update_by=operator_id,
            update_time=now,
            can_execute=True,
            can_edit=True,
            error=None,
            query_result=None,
        )
        response_items.append(response_item)
    session.commit()
    _invalidate_roi_chart_cache(
        cache_adapter,
        tenant_id,
        datasource_id=config.datasource_id,
        dashboard_id=dashboard_id,
    )
    return sorted(
        response_items,
        key=lambda item: (item["sort"], item["create_time"], item["id"]),
    )
