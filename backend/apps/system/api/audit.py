from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func, or_
from sqlmodel import select

from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.user import is_super_admin
from apps.system.models.tenant import TenantUserModel
from apps.system.models.user import UserModel
from apps.system.schemas.permission import AppPermission, require_permissions
from common.audit.models.log_model import OperationStatus, OperationType, SystemLog, SystemLogsResource
from common.core.deps import CurrentUser, SessionDep

router = APIRouter(tags=["system_audit"], prefix="/system/audit", include_in_schema=False)

OPERATION_TYPE_NAMES = {
    OperationType.CREATE.value: "创建",
    OperationType.DELETE.value: "删除",
    OperationType.UPDATE.value: "更新",
    OperationType.RESET_PWD.value: "重置密码",
    OperationType.UPDATE_PWD.value: "修改密码",
    OperationType.UPDATE_STATUS.value: "修改状态",
    OperationType.UPDATE_TABLE_RELATION.value: "更新表关联",
    OperationType.EDIT.value: "编辑",
    OperationType.LOGIN.value: "登录",
    OperationType.VIEW.value: "查看",
    OperationType.EXPORT.value: "导出",
    OperationType.IMPORT.value: "导入",
    OperationType.ADD.value: "新增",
    OperationType.CREATE_OR_UPDATE.value: "创建或更新",
    OperationType.ANALYSIS.value: "分析",
    OperationType.PREDICTION.value: "预测",
}
STATUS_NAMES = {
    OperationStatus.SUCCESS.value: "成功",
    OperationStatus.FAILED.value: "失败",
}


def _split_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in str(value).split("__") if item != ""]


def _query_filters(request: Request) -> dict[str, list[str] | str | None]:
    query = request.query_params
    return {
        "name": query.get("name"),
        "opt_type_list": _split_values(query.get("opt_type_list")),
        "uid_list": _split_values(query.get("uid_list")),
        "log_status": _split_values(query.get("log_status")),
        "time_range": _split_values(query.get("time_range")),
    }


def _parse_millis(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = int(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp)
    except (TypeError, ValueError, OSError):
        return None


def _current_tenant_id(current_user: CurrentUser) -> int:
    try:
        return int(getattr(current_user, "tenant_id", None) or DEFAULT_TENANT_ID)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID


def _apply_tenant_scope(stmt, current_user: CurrentUser):
    if is_super_admin(current_user):
        return stmt
    return stmt.where(SystemLog.tenant_id == _current_tenant_id(current_user))


def _build_stmt(request: Request, current_user: CurrentUser):
    filters = _query_filters(request)
    stmt = _apply_tenant_scope(select(SystemLog), current_user)

    keyword = filters["name"]
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                SystemLog.operation_detail.ilike(pattern),
                SystemLog.user_name.ilike(pattern),
                SystemLog.resource_name.ilike(pattern),
                SystemLog.ip_address.ilike(pattern),
                SystemLog.request_path.ilike(pattern),
            )
        )

    opt_types = filters["opt_type_list"]
    if opt_types:
        stmt = stmt.where(SystemLog.operation_type.in_(opt_types))

    uid_list = filters["uid_list"]
    if uid_list:
        ids = []
        for item in uid_list:
            try:
                ids.append(int(item))
            except ValueError:
                continue
        if ids:
            stmt = stmt.where(SystemLog.user_id.in_(ids))

    log_status = filters["log_status"]
    if log_status:
        stmt = stmt.where(SystemLog.operation_status.in_(log_status))

    time_range = filters["time_range"]
    if len(time_range) >= 2:
        start = _parse_millis(time_range[0])
        end = _parse_millis(time_range[1])
        if start:
            stmt = stmt.where(SystemLog.create_time >= start)
        if end:
            stmt = stmt.where(SystemLog.create_time <= end)

    return stmt


def _format_row(log: SystemLog, resource_name: str | None = None) -> dict:
    operation_type = getattr(log.operation_type, "value", log.operation_type)
    operation_status = getattr(log.operation_status, "value", log.operation_status)
    return {
        "id": str(log.id),
        "operation_type_name": OPERATION_TYPE_NAMES.get(operation_type, operation_type or "-"),
        "operation_detail_info": log.operation_detail or log.request_path or "-",
        "user_name": log.user_name or "-",
        "resource_name": log.resource_name or resource_name or "-",
        "operation_status": operation_status,
        "operation_status_name": STATUS_NAMES.get(operation_status, operation_status or "-"),
        "ip_address": log.ip_address or "-",
        "create_time": log.create_time,
        "error_message": log.error_message,
        "remark": log.remark,
    }


def _resource_name_map(session: SessionDep, log_ids: list[int]) -> dict[int, str]:
    if not log_ids:
        return {}
    rows = session.exec(
        select(SystemLogsResource.log_id, SystemLogsResource.resource_name)
        .where(SystemLogsResource.log_id.in_(log_ids))
    ).all()
    result: dict[int, str] = {}
    for log_id, resource_name in rows:
        if log_id and resource_name and log_id not in result:
            result[int(log_id)] = resource_name
    return result


@router.get("/page/{page_num}/{page_size}")
@require_permissions(permission=AppPermission(role=["admin"]))
async def page(session: SessionDep, request: Request, current_user: CurrentUser, page_num: int, page_size: int):
    base_stmt = _build_stmt(request, current_user)
    total_count = session.exec(select(func.count()).select_from(base_stmt.subquery())).one()
    logs = session.exec(
        base_stmt
        .order_by(SystemLog.create_time.desc(), SystemLog.id.desc())
        .offset(max(page_num - 1, 0) * page_size)
        .limit(page_size)
    ).all()
    resource_map = _resource_name_map(session, [item.id for item in logs if item.id])
    return {
        "data": [_format_row(item, resource_map.get(item.id)) for item in logs],
        "total_count": total_count,
    }


@router.get("/get_options")
@require_permissions(permission=AppPermission(role=["admin"]))
async def get_options():
    return [{"id": item.value, "name": OPERATION_TYPE_NAMES.get(item.value, item.value)} for item in OperationType]


@router.get("/users")
@require_permissions(permission=AppPermission(role=["admin"]))
async def users(session: SessionDep, current_user: CurrentUser):
    stmt = select(UserModel.id, UserModel.name)
    if not is_super_admin(current_user):
        stmt = (
            stmt
            .join(TenantUserModel, TenantUserModel.user_id == UserModel.id)
            .where(
                TenantUserModel.tenant_id == _current_tenant_id(current_user),
                TenantUserModel.status == 1,
            )
            .distinct()
        )
    rows = session.exec(stmt.order_by(UserModel.name)).all()
    return [{"id": item.id, "name": item.name} for item in rows]


@router.get("/export")
@require_permissions(permission=AppPermission(role=["admin"]))
async def export(session: SessionDep, request: Request, current_user: CurrentUser):
    logs = session.exec(_build_stmt(request, current_user).order_by(SystemLog.create_time.desc(), SystemLog.id.desc())).all()
    resource_map = _resource_name_map(session, [item.id for item in logs if item.id])

    wb = Workbook()
    ws = wb.active
    ws.title = "操作日志"
    headers = ["操作类型", "操作详情", "操作用户", "资源名称", "操作状态", "IP 地址", "创建时间", "错误信息", "备注"]
    ws.append(headers)
    for item in logs:
        row = _format_row(item, resource_map.get(item.id))
        ws.append([
            row["operation_type_name"],
            row["operation_detail_info"],
            row["user_name"],
            row["resource_name"],
            row["operation_status_name"],
            row["ip_address"],
            row["create_time"].strftime("%Y-%m-%d %H:%M:%S") if row["create_time"] else "",
            row["error_message"] or "",
            row["remark"] or "",
        ])

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="system-audit.xlsx"'},
    )
