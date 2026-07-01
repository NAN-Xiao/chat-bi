"""
脚本说明：这个脚本放第三方 MCP 外部数据源配置接口。
"""
from fastapi import APIRouter, Query

from apps.external_mcp.crud import (
    list_external_mcp_servers,
    list_external_mcp_tools,
    preview_external_mcp_tool,
    upsert_external_mcp_server,
)
from apps.external_mcp.schemas import (
    ExternalMcpServerCreator,
    ExternalMcpServerDTO,
    ExternalMcpServerEditor,
    ExternalMcpToolDTO,
    ExternalMcpToolPreviewRequest,
    ExternalMcpToolPreviewResponse,
)
from apps.system.schemas.permission import AppPermission, require_permissions
from common.audit.models.log_model import OperationModules, OperationType
from common.audit.schemas.logger_decorator import LogConfig, system_log
from common.core.deps import CurrentUser, SessionDep

router = APIRouter(tags=["external_mcp"], prefix="/external-mcp")


def _external_mcp_dto(record) -> ExternalMcpServerDTO:
    """
    是什么：_external_mcp_dto 把第三方 MCP 数据源数据库记录转成前端 DTO。
    """
    return ExternalMcpServerDTO(
        id=int(record.id),
        name=record.name,
        endpoint=record.endpoint,
        description=record.description,
        auth_type=record.auth_type,
        auth_header_name=record.auth_header_name,
        server_name=record.server_name,
        server_version=record.server_version,
        status=int(record.status or 0),
        credential_configured=bool(record.credential_configured),
        create_time=int(record.create_time or 0),
        update_time=int(record.update_time or 0),
    )


@router.get("/list", response_model=list[ExternalMcpServerDTO], include_in_schema=False)
@require_permissions(permission=AppPermission(role=["platform_admin"]))
async def list_external_mcp(
    session: SessionDep,
    _current_user: CurrentUser,
    keyword: str | None = Query(default=None, max_length=100),
    include_disabled: bool = Query(default=False),
):
    """
    是什么：list_external_mcp 列出第三方 MCP 外部数据源配置。
    """
    return [
        _external_mcp_dto(record)
        for record in list_external_mcp_servers(
            session,
            keyword=keyword,
            include_disabled=include_disabled,
        )
    ]


@router.post("", response_model=ExternalMcpServerDTO, include_in_schema=False)
@require_permissions(permission=AppPermission(role=["platform_admin"]))
@system_log(LogConfig(operation_type=OperationType.CREATE, module=OperationModules.DATASOURCE, result_id_expr="id"))
async def create_external_mcp(
    session: SessionDep,
    current_user: CurrentUser,
    creator: ExternalMcpServerCreator,
):
    """
    是什么：create_external_mcp 创建第三方 MCP 外部数据源配置。
    """
    record = upsert_external_mcp_server(
        session,
        current_user,
        name=creator.name,
        endpoint=creator.endpoint,
        description=creator.description,
        auth_type=creator.auth_type,
        auth_header_name=creator.auth_header_name,
        auth_token=creator.auth_token,
        server_name=creator.server_name,
        server_version=creator.server_version,
        status=creator.status,
    )
    return _external_mcp_dto(record)


@router.get("/{external_mcp_server_id}/tools", response_model=list[ExternalMcpToolDTO], include_in_schema=False)
async def list_external_mcp_tool_api(
    session: SessionDep,
    current_user: CurrentUser,
    external_mcp_server_id: int | str,
    tenant_id: int | str | None = Query(default=None),
    dashboard_id: str | None = Query(default=None),
):
    """
    是什么：list_external_mcp_tool_api 列出当前工作空间绑定的第三方 MCP 工具。
    """
    _record, tools = list_external_mcp_tools(
        session,
        current_user,
        external_mcp_server_id,
        tenant_id=tenant_id,
        dashboard_id=dashboard_id,
    )
    return [
        ExternalMcpToolDTO(
            name=item.get("name") or "",
            title=item.get("title"),
            description=item.get("description"),
            input_schema=item.get("inputSchema") or {},
            output_schema=item.get("outputSchema") or {},
        )
        for item in tools
        if isinstance(item, dict) and item.get("name")
    ]


@router.post("/preview", response_model=ExternalMcpToolPreviewResponse, include_in_schema=False)
async def preview_external_mcp_tool_api(
    session: SessionDep,
    current_user: CurrentUser,
    request: ExternalMcpToolPreviewRequest,
):
    """
    是什么：preview_external_mcp_tool_api 调用第三方 MCP 工具并返回图表可用快照数据。
    """
    return preview_external_mcp_tool(
        session,
        current_user,
        external_mcp_server_id=request.external_mcp_server_id,
        tool=request.tool,
        arguments=request.arguments,
        result_path=request.result_path,
        key_field=request.key_field,
        value_field=request.value_field,
        tenant_id=request.tenant_id,
        dashboard_id=request.dashboard_id,
    )


@router.put("", response_model=ExternalMcpServerDTO, include_in_schema=False)
@require_permissions(permission=AppPermission(role=["platform_admin"]))
@system_log(LogConfig(operation_type=OperationType.UPDATE, module=OperationModules.DATASOURCE, resource_id_expr="editor.id"))
async def update_external_mcp(
    session: SessionDep,
    current_user: CurrentUser,
    editor: ExternalMcpServerEditor,
):
    """
    是什么：update_external_mcp 更新第三方 MCP 外部数据源配置。
    """
    record = upsert_external_mcp_server(
        session,
        current_user,
        external_mcp_server_id=editor.id,
        name=editor.name,
        endpoint=editor.endpoint,
        description=editor.description,
        auth_type=editor.auth_type,
        auth_header_name=editor.auth_header_name,
        auth_token=editor.auth_token,
        server_name=editor.server_name,
        server_version=editor.server_version,
        status=editor.status,
    )
    return _external_mcp_dto(record)
