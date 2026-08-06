"""
脚本说明：这个脚本放系统管理的接口，把前端请求接进来并交给后面的业务逻辑处理。
"""
import asyncio
import time
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlmodel import select

from apps.datasource.crud.binding import (
    get_bound_datasource_id_for_tenant,
    list_bound_tenant_ids_for_datasource,
)
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.tracking_config import (
    build_tracking_event_catalog,
    get_tracking_config,
    save_tracking_config,
)
from apps.system.crud.tracking_excel import (
    PhysicalFieldInfo,
    PhysicalTableInfo,
    import_summary,
    parse_tracking_excel,
    tracking_config_excel,
)
from apps.system.schemas.tenant_schema import (
    TenantTrackingConfigDTO,
    TenantTrackingConfigEditor,
    TenantTrackingConfigImportDTO,
    TenantTrackingEventCatalogDTO,
)
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import CurrentTenant, CurrentUser, SessionDep
from apps.system.schemas.access_context import is_global_platform_context
from common.observability.api_timing import log_api_timing
from common.utils.file_utils import AppFileUtils

router = APIRouter(tags=["TenantTrackingConfig"], prefix="/system/tracking-config")


def _require_workspace_admin(current_user: CurrentUser, current_tenant: CurrentTenant) -> None:
    """
    是什么：_require_workspace_admin 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：同一个接口脚本里的路由函数或辅助逻辑会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
    role = normalize_tenant_role(
        getattr(current_user, "workspace_role", None)
        or getattr(current_user, "tenant_role", None)
        or getattr(current_tenant, "role", None)
    )
    if role in TENANT_ADMIN_ROLES:
        return
    raise HTTPException(status_code=403, detail="Only workspace admin can maintain tracking config")


def _workspace_physical_schema(
    session: SessionDep,
    tenant_id: int,
) -> tuple[dict[str, PhysicalTableInfo], str | None, int | None]:
    """
    是什么：读取当前工作空间绑定数据源的物理表字段，用于生成 Excel 模板和校验导入来源字段。
    """
    datasource_id = get_bound_datasource_id_for_tenant(session, int(tenant_id))
    if datasource_id is None:
        return {}, None, None
    datasource = session.get(CoreDatasource, int(datasource_id))
    if datasource is None:
        return {}, None, None
    tables = session.exec(
        select(CoreTable)
        .where(CoreTable.ds_id == int(datasource_id))
        .order_by(CoreTable.table_name, CoreTable.id)
    ).all()
    table_ids = [int(table.id) for table in tables if table.id is not None]
    fields_by_table: dict[int, list[CoreField]] = {table_id: [] for table_id in table_ids}
    if table_ids:
        fields = session.exec(
            select(CoreField)
            .where(CoreField.table_id.in_(table_ids))
            .order_by(CoreField.table_id, CoreField.field_index, CoreField.id)
        ).all()
        for field in fields:
            fields_by_table.setdefault(int(field.table_id), []).append(field)

    schema: dict[str, PhysicalTableInfo] = {}
    for table in tables:
        if not table.table_name:
            continue
        schema[table.table_name] = PhysicalTableInfo(
            table_name=table.table_name,
            table_comment=table.table_comment or "",
            custom_comment=table.custom_comment or "",
            fields=[
                PhysicalFieldInfo(
                    field_name=field.field_name or "",
                    field_type=field.field_type or "",
                    field_comment=field.field_comment or "",
                    custom_comment=field.custom_comment or "",
                    field_index=int(field.field_index or 0),
                )
                for field in fields_by_table.get(int(table.id), [])
                if field.field_name
            ],
        )
    return schema, datasource.type or datasource.type_name, int(datasource_id)


def _excel_response(buffer, filename: str) -> StreamingResponse:
    encoded = quote(filename)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


def _save_tracking_config_or_400(
    session: SessionDep,
    *,
    tenant_id: int,
    editor: TenantTrackingConfigEditor,
    datasource_id: int | None,
    current_user_id: int | None,
) -> TenantTrackingConfigDTO:
    """把配置校验错误转换成可定位的客户端错误并回滚事务。"""
    try:
        return save_tracking_config(
            session,
            int(tenant_id),
            editor,
            datasource_id=datasource_id,
            current_user_id=current_user_id,
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=TenantTrackingConfigDTO, include_in_schema=False)
async def current_tracking_config(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
):
    """
    是什么：current_tracking_config 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    started_at = time.perf_counter()
    status = "error"
    datasource_id = None
    config = None
    try:
        _physical_schema, _datasource_type, datasource_id = _workspace_physical_schema(session, int(current_tenant.id))
        config = get_tracking_config(session, int(current_tenant.id), datasource_id, include_legacy=False)
        status = "success"
        return config
    finally:
        mappings = getattr(config, "event_name_mappings", None) if config is not None else None
        log_api_timing(
            "Tracking config get",
            started_at=started_at,
            tenant_id=getattr(current_tenant, "id", None),
            user_id=getattr(current_user, "id", None),
            datasource_id=datasource_id,
            status=status,
            event_mapping_count=len(mappings) if isinstance(mappings, list) else 0,
        )


@router.get("/event-catalog", response_model=TenantTrackingEventCatalogDTO, include_in_schema=False)
async def current_tracking_event_catalog(
    session: SessionDep,
    current_tenant: CurrentTenant,
    current_user: CurrentUser,
    datasource_id: int | None = None,
):
    """
    是什么：给图表 SQL 构建器返回当前工作空间的业务事件选择目录。
    """
    tenant_id = int(current_tenant.id)
    if datasource_id is not None:
        bound_tenant_ids = list_bound_tenant_ids_for_datasource(session, int(datasource_id))
        if is_global_platform_context(current_user):
            if len(bound_tenant_ids) != 1:
                raise HTTPException(status_code=409, detail="所选数据源未绑定唯一工作空间，无法读取事件目录。")
            tenant_id = int(bound_tenant_ids[0])
        elif int(get_bound_datasource_id_for_tenant(session, tenant_id) or 0) != int(datasource_id):
            raise HTTPException(status_code=409, detail="所选数据源不是当前工作空间绑定的数据源。")
    _physical_schema, _datasource_type, resolved_datasource_id = _workspace_physical_schema(session, tenant_id)
    if datasource_id is not None and int(resolved_datasource_id or 0) != int(datasource_id):
        raise HTTPException(status_code=409, detail="数据源绑定关系已变化，请刷新后重试。")
    config = get_tracking_config(session, tenant_id, resolved_datasource_id, include_legacy=False)
    return build_tracking_event_catalog(config)


@router.put("", response_model=TenantTrackingConfigDTO, include_in_schema=False)
@system_log(
    LogConfig(
        operation_type=OperationType.CREATE_OR_UPDATE,
        module=OperationModules.SETTING,
        resource_id_expr="current_tenant.id",
    )
)
async def update_current_tracking_config(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    editor: TenantTrackingConfigEditor,
):
    """
    是什么：update_current_tracking_config 是一个接口入口，负责接住系统管理相关请求。
    谁调用：前端或外部系统调用对应接口时，FastAPI 会把请求交给它。
    做了什么：把系统管理相关的信息改成最新状态，并保存这些变化。
    """
    _require_workspace_admin(current_user, current_tenant)
    _physical_schema, _datasource_type, datasource_id = _workspace_physical_schema(session, int(current_tenant.id))
    return _save_tracking_config_or_400(
        session,
        tenant_id=int(current_tenant.id),
        editor=editor,
        datasource_id=datasource_id,
        current_user_id=int(current_user.id) if getattr(current_user, "id", None) is not None else None,
    )


@router.get("/template", include_in_schema=False)
@system_log(
    LogConfig(
        operation_type=OperationType.EXPORT,
        module=OperationModules.SETTING,
        resource_id_expr="current_tenant.id",
    )
)
async def download_tracking_config_template(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
):
    """
    是什么：下载可填写的数据字典 Excel 模板。
    """
    _require_workspace_admin(current_user, current_tenant)
    physical_schema, _datasource_type, datasource_id = _workspace_physical_schema(session, int(current_tenant.id))
    config = get_tracking_config(session, int(current_tenant.id), datasource_id, include_legacy=False)
    result = await asyncio.to_thread(
        tracking_config_excel,
        config,
        physical_schema=physical_schema,
        template_only=True,
    )
    return _excel_response(result, "tracking_dictionary_template.xlsx")


@router.get("/export", include_in_schema=False)
@system_log(
    LogConfig(
        operation_type=OperationType.EXPORT,
        module=OperationModules.SETTING,
        resource_id_expr="current_tenant.id",
    )
)
async def export_current_tracking_config(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
):
    """
    是什么：把当前工作空间数据字典导出为 Excel，方便运维离线批量维护。
    """
    _require_workspace_admin(current_user, current_tenant)
    physical_schema, _datasource_type, datasource_id = _workspace_physical_schema(session, int(current_tenant.id))
    config = get_tracking_config(session, int(current_tenant.id), datasource_id, include_legacy=False)
    result = await asyncio.to_thread(
        tracking_config_excel,
        config,
        physical_schema=physical_schema,
        template_only=False,
    )
    return _excel_response(result, "tracking_dictionary_current.xlsx")


@router.post("/importExcel", response_model=TenantTrackingConfigImportDTO, include_in_schema=False)
@system_log(
    LogConfig(
        operation_type=OperationType.IMPORT,
        module=OperationModules.SETTING,
        resource_id_expr="current_tenant.id",
    )
)
async def import_tracking_config_excel(
    session: SessionDep,
    current_user: CurrentUser,
    current_tenant: CurrentTenant,
    file: UploadFile = File(...),
):
    """
    是什么：上传 Excel 并以 Excel 为准替换当前工作空间当前数据源的数据字典语义配置。
    """
    _require_workspace_admin(current_user, current_tenant)
    AppFileUtils.validate_extension(file.filename, {".xlsx", ".xls"})
    content = await AppFileUtils.read_upload_limited(file)
    physical_schema, datasource_type, datasource_id = _workspace_physical_schema(session, int(current_tenant.id))
    existing = get_tracking_config(session, int(current_tenant.id), datasource_id, include_legacy=False)
    try:
        parsed = await asyncio.to_thread(
            parse_tracking_excel,
            content,
            existing,
            physical_schema=physical_schema,
            datasource_type=datasource_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Excel 解析失败：{exc}") from exc

    saved = _save_tracking_config_or_400(
        session,
        tenant_id=int(current_tenant.id),
        editor=parsed.editor,
        datasource_id=datasource_id,
        current_user_id=int(current_user.id) if getattr(current_user, "id", None) is not None else None,
    )
    return TenantTrackingConfigImportDTO(config=saved, summary=import_summary(parsed))
