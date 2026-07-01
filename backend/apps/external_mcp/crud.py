"""
脚本说明：这个脚本封装第三方 MCP 外部数据源配置和工作空间绑定逻辑。
"""
from typing import Any
from datetime import datetime, timezone
import itertools
import json

from fastapi import HTTPException
import httpx
from sqlalchemy import inspect, or_
from sqlmodel import select

from apps.dashboard.models.dashboard_model import CoreDashboard
from apps.external_mcp.models import CoreExternalMcpServer, CoreExternalMcpTenantBinding
from apps.system.crud.tenant import DEFAULT_TENANT_ID, user_belongs_to_tenant
from apps.system.crud.user import is_platform_admin
from apps.system.models.tenant import TenantModel
from common.core.deps import CurrentUser, SessionDep
from common.utils.crypto import decrypt_sensitive_text, encrypt_sensitive_text
from common.utils.time import get_timestamp


def supports_external_mcp_binding(session: SessionDep) -> bool:
    """
    是什么：supports_external_mcp_binding 检查第三方 MCP 绑定表是否可用。
    """
    try:
        inspector = inspect(session.connection())
        return inspector.has_table(CoreExternalMcpTenantBinding.__tablename__)
    except Exception:
        return False


def supports_external_mcp_server(session: SessionDep) -> bool:
    """
    是什么：supports_external_mcp_server 检查第三方 MCP 服务表是否可用。
    """
    try:
        inspector = inspect(session.connection())
        return inspector.has_table(CoreExternalMcpServer.__tablename__)
    except Exception:
        return False


def _external_mcp_rpc_headers(record: CoreExternalMcpServer) -> dict[str, str]:
    """
    是什么：_external_mcp_rpc_headers 根据第三方 MCP 配置生成请求头。
    """
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    token = decrypt_sensitive_text(getattr(record, "auth_token", None))
    if token:
        header_name = (record.auth_header_name or "Authorization").strip() or "Authorization"
        auth_type = (record.auth_type or "bearer").strip().lower()
        headers[header_name] = f"Bearer {token}" if auth_type == "bearer" else token
    return headers


def _parse_mcp_json_rpc_response(response: httpx.Response) -> dict[str, Any]:
    """
    是什么：_parse_mcp_json_rpc_response 解析第三方 MCP JSON-RPC/事件流响应。
    """
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" not in content_type:
        return response.json()
    for line in response.text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line.removeprefix("data:").strip()
        if not payload:
            continue
        try:
            return json.loads(payload)
        except Exception:
            continue
    raise HTTPException(status_code=502, detail="Invalid MCP event stream response")


def _external_mcp_rpc_call(record: CoreExternalMcpServer, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    是什么：_external_mcp_rpc_call 调用第三方 MCP JSON-RPC 方法。
    """
    endpoint = (record.endpoint or "").strip()
    if not endpoint:
        raise HTTPException(status_code=400, detail="External MCP endpoint is empty")
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.post(endpoint, headers=_external_mcp_rpc_headers(record), json=payload)
            response.raise_for_status()
            data = _parse_mcp_json_rpc_response(response)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"External MCP request failed: {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="External MCP request failed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="External MCP returned invalid JSON") from exc
    if "error" in data:
        message = data.get("error", {}).get("message") or "External MCP returned an error"
        raise HTTPException(status_code=400, detail=message)
    return data.get("result") or {}


def _external_mcp_initialize(record: CoreExternalMcpServer) -> dict[str, Any]:
    """
    是什么：_external_mcp_initialize 获取第三方 MCP 服务信息。
    """
    return _external_mcp_rpc_call(
        record,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "shuzhi-bi-dashboard", "version": "1.0.0"},
        },
    )


def _mcp_tool_structured_content(result: dict[str, Any]) -> Any:
    """
    是什么：_mcp_tool_structured_content 提取 MCP tools/call 的结构化结果。
    """
    if "structuredContent" in result:
        return result.get("structuredContent")
    content = result.get("content")
    if isinstance(content, list):
        text = "".join(item.get("text", "") for item in content if isinstance(item, dict))
        if text:
            try:
                return json.loads(text)
            except Exception:
                return {"text": text}
    return result


def _value_at_path(value: Any, path: str | None) -> Any:
    """
    是什么：_value_at_path 按点号路径从 MCP 返回结果里取一段数据。
    """
    if not path:
        return value
    current = value
    for part in [item for item in path.split(".") if item]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (TypeError, ValueError, IndexError):
                return None
        else:
            return None
    return current


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：_flatten_row 把列表、对象等值转换成图表表格可展示的标量。
    """
    flattened: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flattened[str(key)] = value
        else:
            flattened[str(key)] = json.dumps(value, ensure_ascii=False)
    return flattened


def _ordered_mapping_items(value: dict[str, Any]) -> list[tuple[str, Any]]:
    """
    是什么：_ordered_mapping_items 把 MCP 映射结果转成稳定的图表行顺序。
    """
    items = list(value.items())
    scalar_items = [
        (key, item_value)
        for key, item_value in items
        if isinstance(item_value, (str, int, float, bool)) or item_value is None
    ]
    if scalar_items and all(isinstance(item_value, (int, float)) and not isinstance(item_value, bool) for _, item_value in scalar_items):
        return sorted(scalar_items, key=lambda item: (-float(item[1]), str(item[0])))
    return scalar_items


def _expand_mapping_rows(
    value: dict[str, Any],
    *,
    group_name: str | None,
    key_name: str,
    value_name: str,
) -> list[dict[str, Any]]:
    """
    是什么：_expand_mapping_rows 把 MCP 返回的映射对象展开为图表可用行。
    """
    rows: list[dict[str, Any]] = []
    for key, item_value in _ordered_mapping_items(value):
        row = {key_name: key, value_name: item_value}
        if group_name:
            row["group"] = group_name
        rows.append(_flatten_row(row))
    return rows


def _normalize_external_mcp_preview_rows(
    raw: Any,
    *,
    result_path: str | None = None,
    key_field: str | None = None,
    value_field: str | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    是什么：_normalize_external_mcp_preview_rows 把 MCP 任意 JSON 结果整理成图表表格数据。
    """
    selected = _value_at_path(raw, result_path)
    key_name = (key_field or "name").strip() or "name"
    value_name = (value_field or "value").strip() or "value"
    rows: list[dict[str, Any]]
    if isinstance(selected, list):
        rows = [
            _flatten_row(item if isinstance(item, dict) else {key_name: index + 1, value_name: item})
            for index, item in enumerate(selected)
        ]
    elif isinstance(selected, dict):
        rows = [
            _flatten_row({key_name: key, value_name: value})
            for key, value in _ordered_mapping_items(selected)
        ]
        if not rows:
            rows = [_flatten_row(selected)]
        if not result_path:
            nested_rows = list(
                itertools.chain.from_iterable(
                    _expand_mapping_rows(value, group_name=key, key_name=key_name, value_name=value_name)
                    for key, value in selected.items()
                    if isinstance(value, dict)
                )
            )
            if nested_rows:
                rows.extend(nested_rows)
    elif selected is None:
        rows = []
    else:
        rows = [_flatten_row({value_name: selected})]
    fields = list(dict.fromkeys(itertools.chain.from_iterable(row.keys() for row in rows)))
    return fields, rows


def get_bound_external_mcp_id_for_tenant(session: SessionDep, tenant_id: int | None) -> int | None:
    """
    是什么：get_bound_external_mcp_id_for_tenant 获取工作空间当前绑定的第三方 MCP 数据源 ID。
    """
    if tenant_id is None or int(tenant_id) == DEFAULT_TENANT_ID:
        return None
    if not supports_external_mcp_binding(session):
        return None
    external_mcp_id = session.exec(
        select(CoreExternalMcpTenantBinding.external_mcp_server_id)
        .where(CoreExternalMcpTenantBinding.tenant_id == int(tenant_id))
        .order_by(CoreExternalMcpTenantBinding.id)
    ).first()
    return int(external_mcp_id) if external_mcp_id is not None else None


def external_mcp_bound_to_tenant(
    session: SessionDep,
    external_mcp_server_id: int | None,
    tenant_id: int | None,
) -> bool:
    """
    是什么：external_mcp_bound_to_tenant 判断第三方 MCP 数据源是否绑定到当前工作空间。
    """
    if external_mcp_server_id is None or tenant_id is None:
        return False
    if not supports_external_mcp_binding(session):
        return False
    return session.exec(
        select(CoreExternalMcpTenantBinding.id).where(
            CoreExternalMcpTenantBinding.tenant_id == int(tenant_id),
            CoreExternalMcpTenantBinding.external_mcp_server_id == int(external_mcp_server_id),
        )
    ).first() is not None


def _normalize_optional_tenant_id(tenant_id: int | str | None) -> int | None:
    """
    是什么：_normalize_optional_tenant_id 把可选工作空间 ID 转成整数。
    """
    if tenant_id in (None, ""):
        return None
    try:
        return int(tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Workspace id is invalid") from exc


def _resolve_external_mcp_access_tenant_id(
    session: SessionDep,
    current_user: CurrentUser,
    external_mcp_server_id: int,
    requested_tenant_id: int | str | None = None,
    dashboard_id: str | None = None,
) -> int | None:
    """
    是什么：_resolve_external_mcp_access_tenant_id 确定第三方 MCP 调用应按哪个工作空间校验。
    """
    target_tenant_id = _normalize_optional_tenant_id(requested_tenant_id)
    server_id = int(external_mcp_server_id)
    if target_tenant_id is None:
        return _normalize_optional_tenant_id(getattr(current_user, "tenant_id", None))
    if target_tenant_id == DEFAULT_TENANT_ID:
        return target_tenant_id
    current_tenant_id = _normalize_optional_tenant_id(getattr(current_user, "tenant_id", None))
    if current_tenant_id == target_tenant_id:
        return target_tenant_id
    if is_platform_admin(current_user):
        return target_tenant_id
    user_id = getattr(current_user, "id", None)
    if user_id is not None and user_belongs_to_tenant(session, int(user_id), target_tenant_id):
        return target_tenant_id
    if _external_mcp_dashboard_matches_context(session, dashboard_id, server_id, target_tenant_id):
        return target_tenant_id
    raise HTTPException(status_code=403, detail="No permission for target workspace")


def _external_mcp_dashboard_record(
    session: SessionDep,
    dashboard_id: str | None,
) -> CoreDashboard | None:
    """
    是什么：_external_mcp_dashboard_record 读取可作为 MCP 调用上下文的看板。
    """
    if not dashboard_id:
        return None
    dashboard = session.get(CoreDashboard, str(dashboard_id))
    if not dashboard or getattr(dashboard, "delete_flag", 0) == 1:
        return None
    if getattr(dashboard, "external_mcp_server_id", None) is None:
        return None
    return dashboard


def _can_use_external_mcp_dashboard_context(
    session: SessionDep,
    current_user: CurrentUser,
    dashboard: CoreDashboard,
) -> bool:
    """
    是什么：_can_use_external_mcp_dashboard_context 判断当前用户能否按看板上下文调用 MCP。
    """
    dashboard_tenant_id = int(getattr(dashboard, "tenant_id", 0) or 0)
    current_tenant_id = _normalize_optional_tenant_id(getattr(current_user, "tenant_id", None))
    if current_tenant_id == dashboard_tenant_id:
        return True
    if is_platform_admin(current_user):
        return True
    user_id = getattr(current_user, "id", None)
    return user_id is not None and user_belongs_to_tenant(session, int(user_id), dashboard_tenant_id)


def _external_mcp_dashboard_matches_context(
    session: SessionDep,
    dashboard_id: str | None,
    external_mcp_server_id: int,
    tenant_id: int | None,
) -> bool:
    """
    是什么：_external_mcp_dashboard_matches_context 校验目标看板确实属于该工作空间和第三方 MCP。
    """
    if tenant_id is None:
        return False
    dashboard = _external_mcp_dashboard_record(session, dashboard_id)
    if not dashboard:
        return False
    dashboard_external_mcp_id = getattr(dashboard, "external_mcp_server_id", None)
    return (
        dashboard_external_mcp_id is not None
        and int(dashboard_external_mcp_id) == int(external_mcp_server_id)
        and int(getattr(dashboard, "tenant_id", 0) or 0) == int(tenant_id)
    )


def list_external_mcp_binding_rows(session: SessionDep, tenant_ids: list[int] | None = None):
    """
    是什么：list_external_mcp_binding_rows 列出工作空间与第三方 MCP 数据源的绑定关系。
    """
    if not supports_external_mcp_binding(session) or not supports_external_mcp_server(session):
        return []
    statement = (
        select(
            CoreExternalMcpTenantBinding.tenant_id,
            CoreExternalMcpTenantBinding.external_mcp_server_id,
            CoreExternalMcpServer.name,
        )
        .join(CoreExternalMcpServer, CoreExternalMcpServer.id == CoreExternalMcpTenantBinding.external_mcp_server_id)
        .order_by(CoreExternalMcpTenantBinding.tenant_id, CoreExternalMcpServer.name)
    )
    if tenant_ids:
        statement = statement.where(CoreExternalMcpTenantBinding.tenant_id.in_([int(item) for item in tenant_ids]))
    return session.exec(statement).all()


def list_external_mcp_servers(
    session: SessionDep,
    *,
    keyword: str | None = None,
    include_disabled: bool = False,
) -> list[CoreExternalMcpServer]:
    """
    是什么：list_external_mcp_servers 列出第三方 MCP 数据源配置。
    """
    if not supports_external_mcp_server(session):
        return []
    statement = select(CoreExternalMcpServer)
    if not include_disabled:
        statement = statement.where(CoreExternalMcpServer.status == 1)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                CoreExternalMcpServer.name.ilike(pattern),
                CoreExternalMcpServer.server_name.ilike(pattern),
                CoreExternalMcpServer.endpoint.ilike(pattern),
            )
        )
    return list(session.exec(statement.order_by(CoreExternalMcpServer.name, CoreExternalMcpServer.id)).all())


def list_external_mcp_tools(
    session: SessionDep,
    current_user: CurrentUser,
    external_mcp_server_id: int,
    tenant_id: int | str | None = None,
    dashboard_id: str | None = None,
) -> tuple[CoreExternalMcpServer, list[dict[str, Any]]]:
    """
    是什么：list_external_mcp_tools 列出当前工作空间可用第三方 MCP 工具。
    """
    server_id = int(external_mcp_server_id)
    dashboard_context = _external_mcp_dashboard_record(session, dashboard_id)
    if dashboard_context is not None and _can_use_external_mcp_dashboard_context(
        session,
        current_user,
        dashboard_context,
    ):
        server_id = int(dashboard_context.external_mcp_server_id)
        tenant_id = int(dashboard_context.tenant_id)
    target_tenant_id = _resolve_external_mcp_access_tenant_id(
        session,
        current_user,
        server_id,
        requested_tenant_id=tenant_id,
        dashboard_id=dashboard_id,
    )
    if not external_mcp_bound_to_tenant(session, server_id, target_tenant_id):
        raise HTTPException(status_code=403, detail="External MCP datasource is not bound to current workspace")
    record = session.get(CoreExternalMcpServer, server_id)
    if record is None or int(getattr(record, "status", 1)) != 1:
        raise HTTPException(status_code=404, detail="External MCP datasource does not exist")
    _external_mcp_initialize(record)
    result = _external_mcp_rpc_call(record, "tools/list", {})
    return record, result.get("tools") or []


def preview_external_mcp_tool(
    session: SessionDep,
    current_user: CurrentUser,
    *,
    external_mcp_server_id: int,
    tool: str,
    arguments: dict[str, Any] | None = None,
    result_path: str | None = None,
    key_field: str | None = None,
    value_field: str | None = None,
    tenant_id: int | str | None = None,
    dashboard_id: str | None = None,
) -> dict[str, Any]:
    """
    是什么：preview_external_mcp_tool 调用第三方 MCP 工具并整理成看板图表快照。
    """
    record, tools = list_external_mcp_tools(
        session,
        current_user,
        external_mcp_server_id,
        tenant_id=tenant_id,
        dashboard_id=dashboard_id,
    )
    tool_names = {item.get("name") for item in tools if isinstance(item, dict)}
    normalized_tool = (tool or "").strip()
    if not normalized_tool:
        raise HTTPException(status_code=400, detail="External MCP tool is required")
    if tool_names and normalized_tool not in tool_names:
        raise HTTPException(status_code=400, detail="External MCP tool is not available")
    tool_result = _external_mcp_rpc_call(
        record,
        "tools/call",
        {"name": normalized_tool, "arguments": arguments or {}},
    )
    raw = _mcp_tool_structured_content(tool_result)
    fields, rows = _normalize_external_mcp_preview_rows(
        raw,
        result_path=result_path,
        key_field=key_field,
        value_field=value_field,
    )
    initialized = _external_mcp_initialize(record)
    server_info = initialized.get("serverInfo") or {}
    snapshot_at = datetime.now(timezone.utc).isoformat()
    return {
        "status": "success",
        "fields": fields,
        "data": rows,
        "raw": raw,
        "message": "",
        "mcp": {
            "server": server_info.get("name") or record.server_name or record.name,
            "serverVersion": server_info.get("version") or record.server_version,
            "endpoint": record.endpoint,
            "tool": normalized_tool,
            "arguments": arguments or {},
            "resultPath": result_path or "",
            "keyField": key_field or "",
            "valueField": value_field or "",
            "snapshotAt": snapshot_at,
            "auth": "not_stored",
        },
    }


def upsert_external_mcp_server(
    session: SessionDep,
    user: CurrentUser,
    *,
    name: str,
    endpoint: str,
    external_mcp_server_id: int | None = None,
    description: str | None = None,
    auth_type: str = "bearer",
    auth_header_name: str = "Authorization",
    auth_token: str | None = None,
    server_name: str | None = None,
    server_version: str | None = None,
    status: int = 1,
) -> CoreExternalMcpServer:
    """
    是什么：upsert_external_mcp_server 创建或更新第三方 MCP 数据源配置。
    """
    normalized_name = (name or "").strip()
    normalized_endpoint = (endpoint or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="MCP 名称不能为空")
    if not normalized_endpoint:
        raise HTTPException(status_code=400, detail="MCP Endpoint 不能为空")

    now = get_timestamp()
    if external_mcp_server_id:
        record = session.get(CoreExternalMcpServer, int(external_mcp_server_id))
        if not record:
            raise HTTPException(status_code=404, detail="第三方 MCP 数据源不存在")
    else:
        existing = session.exec(
            select(CoreExternalMcpServer).where(CoreExternalMcpServer.name == normalized_name)
        ).first()
        record = existing or CoreExternalMcpServer(create_by=getattr(user, "id", None), create_time=now)

    duplicate = session.exec(
        select(CoreExternalMcpServer.id).where(
            CoreExternalMcpServer.name == normalized_name,
            CoreExternalMcpServer.id != getattr(record, "id", None),
        )
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=400, detail="第三方 MCP 数据源名称已存在")

    record.name = normalized_name
    record.endpoint = normalized_endpoint
    record.description = (description or "").strip() or None
    record.auth_type = (auth_type or "bearer").strip().lower()
    record.auth_header_name = (auth_header_name or "Authorization").strip() or "Authorization"
    if auth_token not in (None, ""):
        record.auth_token = encrypt_sensitive_text(auth_token)
        record.credential_configured = True
    elif not getattr(record, "auth_token", None):
        record.auth_token = None
        record.credential_configured = False
    record.server_name = (server_name or "").strip() or None
    record.server_version = (server_version or "").strip() or None
    record.status = 1 if int(status or 0) == 1 else 0
    record.update_by = getattr(user, "id", None)
    record.update_time = now
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def bind_tenant_to_external_mcp(
    session: SessionDep,
    user: CurrentUser,
    tenant_id: int,
    external_mcp_server_id: int | None,
) -> CoreExternalMcpServer | None:
    """
    是什么：bind_tenant_to_external_mcp 绑定工作空间到一个第三方 MCP 数据源。
    """
    target_tenant_id = int(tenant_id)
    if target_tenant_id == DEFAULT_TENANT_ID:
        raise HTTPException(status_code=400, detail="默认工作空间不能绑定第三方 MCP 数据源")
    tenant = session.get(TenantModel, target_tenant_id)
    if tenant is None or int(getattr(tenant, "status", 1)) < 0:
        raise HTTPException(status_code=404, detail="工作空间不存在")
    if not supports_external_mcp_binding(session):
        raise HTTPException(status_code=400, detail="第三方 MCP 绑定表尚未初始化")

    if external_mcp_server_id in (None, "", 0):
        session.query(CoreExternalMcpTenantBinding).filter(
            CoreExternalMcpTenantBinding.tenant_id == target_tenant_id
        ).delete(synchronize_session=False)
        session.commit()
        return None

    server = session.get(CoreExternalMcpServer, int(external_mcp_server_id))
    if server is None or int(getattr(server, "status", 1)) != 1:
        raise HTTPException(status_code=404, detail="第三方 MCP 数据源不存在或已停用")

    existing = session.exec(
        select(CoreExternalMcpTenantBinding).where(
            CoreExternalMcpTenantBinding.tenant_id == target_tenant_id
        )
    ).first()
    now = get_timestamp()
    if existing:
        existing.external_mcp_server_id = int(server.id)
        existing.create_by = getattr(user, "id", None)
        existing.create_time = now
        session.add(existing)
    else:
        session.add(
            CoreExternalMcpTenantBinding(
                tenant_id=target_tenant_id,
                external_mcp_server_id=int(server.id),
                create_by=getattr(user, "id", None),
                create_time=now,
            )
        )
    session.commit()
    session.refresh(server)
    return server
