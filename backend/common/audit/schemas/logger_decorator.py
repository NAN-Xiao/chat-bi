import time
import functools
import json
import inspect
from typing import Callable, Any, Optional, Dict, Union, List
from fastapi import Request, HTTPException
from datetime import datetime
from pydantic import BaseModel
from sqlmodel import Session, select
import traceback
from common.audit.models.log_model import OperationType, OperationStatus, SystemLog, SystemLogsResource
from common.audit.schemas.request_context import RequestContext
from apps.system.crud.tenant import DEFAULT_TENANT_ID
from apps.system.crud.user import is_platform_workspace_delegate
from apps.system.crud.user import get_user_by_account
from apps.system.schemas.system_schema import UserInfoDTO, BaseUserDTO
from sqlalchemy import and_, select

from common.core.db import engine


def _user_tenant_id(user: Optional[UserInfoDTO]) -> int:
    """
    是什么：_user_tenant_id 是 backend/common/audit/schemas/logger_decorator.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _user_tenant_id 的语义处理审计日志相关逻辑，并把结果返回或写入状态。
    """
    if is_platform_workspace_delegate(user):
        return DEFAULT_TENANT_ID
    try:
        tenant_id = getattr(user, "tenant_id", None)
        return int(tenant_id) if tenant_id not in (None, "") else None
    except (TypeError, ValueError):
        return None


def get_resource_name_by_id_and_module(session, resource_id: Any, module: str) -> List[Dict[str, str]]:
    """
    是什么：get_resource_name_by_id_and_module 是 backend/common/audit/schemas/logger_decorator.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询审计日志相关数据，整理后返回给调用方。
    """
    from common.audit.schemas.log_utils import build_resource_union_query

    resource_union_query = build_resource_union_query()
    resource_alias = resource_union_query.alias("resource")

    # 统一处理为列表
    if not isinstance(resource_id, list):
        resource_id = [resource_id]

    if not resource_id:
        return []

    # 构建查询，使用 IN 条件
    query = select(
        resource_alias.c.id,
        resource_alias.c.name,
        resource_alias.c.module
    ).where(
        and_(
            resource_alias.c.id.in_([str(id_) for id_ in resource_id]),
            resource_alias.c.module == module
        )
    )

    results = session.execute(query).fetchall()

    return [{
        'resource_id': str(row.id),
        'resource_name': row.name or '',
        'module': row.module or ''
    } for row in results]

class LogConfig(BaseModel):
    operation_type: OperationType
    operation_detail: str = None
    module: Optional[str] = None

    # 从参数中提取资源 ID 的表达式
    resource_id_expr: Optional[str] = None

    # 从返回结果中提取资源 ID 的表达式
    result_id_expr: Optional[str] = None

    # 从返回结果中提取资源名称或其他信息的表达式
    remark_expr: Optional[str] = None

    # 是否仅在成功时记录
    save_on_success_only: bool = False

    # 是否忽略错误（发生错误时仍按成功记录）
    ignore_errors: bool = False

    # 是否提取请求参数
    extract_params: bool = True

    # 延迟记录（如果需要从结果中提取资源 ID，可设置为 True）
    delay_logging: bool = False


class SystemLogger:
    @staticmethod
    async def create_log(
            session: Session,
            operation_type: OperationType,
            operation_detail: str,
            user: Optional[UserInfoDTO] = None,
            status: OperationStatus = OperationStatus.SUCCESS,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None,
            execution_time: int = 0,
            error_message: Optional[str] = None,
            module: Optional[str] = None,
            resource_id: Any = None,
            request_method: Optional[str] = None,
            request_path: Optional[str] = None,
            remark: Optional[str] = None,
            tenant_id: Optional[int] = None
    ):
        """
        是什么：SystemLogger.create_log 是 backend/common/audit/schemas/logger_decorator.py 中的异步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：创建、初始化或组装审计日志相关对象和数据，并返回或写入对应状态。
        """
        try:
            log = SystemLog(
                tenant_id=tenant_id or _user_tenant_id(user),
                operation_type=operation_type,
                operation_detail=operation_detail,
                user_id=user.id if user else None,
                user_name=user.username if user else None,
                operation_status=status,
                ip_address=ip_address,
                user_agent=user_agent,
                execution_time=execution_time,
                error_message=error_message,
                module=module,
                resource_id=resource_id,
                request_method=request_method,
                request_path=request_path,
                create_time=datetime.now(),
                remark=remark
            )
            session.add(log)
            session.commit()
            return log
        except Exception as e:
            session.rollback()
            print(f"Failed to create system log: {e}")
            return None

    @staticmethod
    def get_client_info(request: Request) -> Dict[str, Optional[str]]:
        """
        是什么：SystemLogger.get_client_info 是 backend/common/audit/schemas/logger_decorator.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：读取或查询审计日志相关数据，整理后返回给调用方。
        """
        ip_address = None
        user_agent = None

        if request:
            # 获取 IP 地址
            if request.client:
                ip_address = request.client.host
            # 尝试从 X-Forwarded-For 获取真实 IP
            if "x-forwarded-for" in request.headers:
                ip_address = request.headers["x-forwarded-for"].split(",")[0].strip()

            # 获取用户代理
            user_agent = request.headers.get("user-agent")

        return {
            "ip_address": ip_address,
            "user_agent": user_agent
        }

    @staticmethod
    def extract_value_from_object(expression: str, obj: Any):
        """
        是什么：SystemLogger.extract_value_from_object 是 backend/common/audit/schemas/logger_decorator.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：解析、转换或格式化审计日志相关数据，生成后续流程可使用的结构。
        """
        if not expression or obj is None:
            return None

        if expression == 'result_self':
            return obj

        try:
            # 处理点分隔属性访问
            parts = expression.split('.')
            current = obj

            for part in parts:
                if not current:
                    return None

                # 处理字典键访问，例如 data['id']
                if '[' in part and ']' in part:
                    import re
                    # 提取键名，例如 data['id'] -> key='id'
                    match = re.search(r"\[['\"]?([^\]'\"\]]+)['\"]?\]", part)
                    if match:
                        key = match.group(1)
                        # 获取对象部分
                        obj_part = part.split('[')[0]
                        if hasattr(current, obj_part):
                            current = getattr(current, obj_part)
                        elif isinstance(current, dict) and obj_part in current:
                            current = current[obj_part]
                        else:
                            return None

                        # 获取键值
                        if isinstance(current, dict) and key in current:
                            current = current[key]
                        elif hasattr(current, key):
                            current = getattr(current, key)
                        elif isinstance(current, list) and key.isdigit():
                            index = int(key)
                            if 0 <= index < len(current):
                                current = current[index]
                            else:
                                return None
                        else:
                            return None
                    else:
                        return None

                # 处理列表索引，例如 items.0.id
                elif part.isdigit() and isinstance(current, (list, tuple)):
                    index = int(part)
                    if 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None

                # 普通属性访问
                else:
                    if hasattr(current, part):
                        current = getattr(current, part)
                    elif isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return None

            return current if current is not None else None

        except Exception:
            return None

    @staticmethod
    def extract_resource_id(
            expression: Optional[str],
            source: Any,
            source_type: str = "args"  # 位置参数、关键字参数、结果
    ):
        """
        是什么：SystemLogger.extract_resource_id 是 backend/common/audit/schemas/logger_decorator.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：解析、转换或格式化审计日志相关数据，生成后续流程可使用的结构。
        """
        if not expression:
            return None

        try:
            if source_type == "result":
                # 直接从结果对象中提取
                return SystemLogger.extract_value_from_object(expression, source)

            elif source_type == "args":
                # 从函数参数中提取
                if isinstance(source, tuple) and len(source) > 0:
                    # 第一个元素是函数自身
                    func_args = source[0] if isinstance(source[0], tuple) else source

                    # 处理 args[index] 表达式
                    if expression.startswith("args["):
                        import re
                        pattern = r"args\[(\d+)\]"
                        match = re.match(pattern, expression)
                        if match:
                            index = int(match.group(1))
                            if index < len(func_args):
                                value = func_args[index]
                                return value if value is not None else None

                    # 处理属性表达式
                    return SystemLogger.extract_value_from_object(expression, func_args)
                elif isinstance(source, dict):
                        # 简单参数名
                        if expression in source:
                            value = source[expression]
                            return value if value is not None else None

                        # 复杂表达式
                        return SystemLogger.extract_value_from_object(expression, source)

            elif source_type == "kwargs":
                # 从关键字参数中提取
                if isinstance(source, dict):
                    # 简单参数名
                    if expression in source:
                        value = source[expression]
                        return value if value is not None else None

                    # 复杂表达式
                    return SystemLogger.extract_value_from_object(expression, source)

            return None

        except Exception:
            return None

    @staticmethod
    def extract_from_function_params(
            expression: Optional[str],
            func_args: any,
            func_kwargs: dict
    ):
        """
        是什么：SystemLogger.extract_from_function_params 是 backend/common/audit/schemas/logger_decorator.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：解析、转换或格式化审计日志相关数据，生成后续流程可使用的结构。
        """
        if not expression:
            return None

        # 尝试从位置参数中提取
        result = SystemLogger.extract_resource_id(expression, func_args, "args")
        if result:
            return result

        # 尝试从关键字参数中提取
        result = SystemLogger.extract_resource_id(expression, func_kwargs, "kwargs")
        if result:
            return result

        # 尝试将参数封装为对象后提取
        try:
            if func_args:
                # 创建包含所有参数的字典
                params_dict = {}

                # 添加位置参数
                for i, arg in enumerate(func_args):
                    params_dict[f"arg_{i}"] = arg

                # 添加关键字参数
                params_dict.update(func_kwargs)

                # 尝试从字典中提取
                return SystemLogger.extract_resource_id(expression, params_dict, "kwargs")
        except:
            pass

        return None

    @staticmethod
    def get_current_user(request: Optional[Request]):
        """
        是什么：SystemLogger.get_current_user 是 backend/common/audit/schemas/logger_decorator.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：读取或查询审计日志相关数据，整理后返回给调用方。
        """
        if not request:
            return None
        try:
            current_user = getattr(request.state, 'current_user', None)
            if current_user:
                return current_user
        except:
            pass

        return None

    @staticmethod
    def extract_request_params(request: Optional[Request]):
        """
        是什么：SystemLogger.extract_request_params 是 backend/common/audit/schemas/logger_decorator.py 中的同步方法。
        谁调用：由类名、实例或模块内业务代码按照静态方法约定调用。
        做了什么：解析、转换或格式化审计日志相关数据，生成后续流程可使用的结构。
        """
        if not request:
            return None

        try:
            params = {}

            # 查询参数
            if request.query_params:
                params["query"] = dict(request.query_params)

            # 路径参数
            if request.path_params:
                params["path"] = dict(request.path_params)

            # 请求头信息（不记录敏感信息）
            headers = {}
            for key, value in request.headers.items():
                if key.lower() not in ["authorization", "cookie", "set-cookie"]:
                    headers[key] = value
            if headers:
                params["headers"] = headers

            # 请求体：仅记录内容类型和大小
            content_type = request.headers.get("content-type", "")
            content_length = request.headers.get("content-length")
            params["body_info"] = {
                "content_type": content_type,
                "content_length": content_length
            }

            return json.dumps(params, ensure_ascii=False, default=str)

        except Exception:
            return None

    @classmethod
    async def create_log_record(
            cls,
            config: LogConfig,
            status: OperationStatus,
            execution_time: int,
            error_message: Optional[str] = None,
            resource_id: Any = None,
            resource_name: Optional[str] = None,
            request: Optional[Request] = None,
            remark: Optional[str] = None,
            opt_type_ref : OperationType = None,
            resource_info_list : Optional[List] = None,
    ) -> Optional[SystemLog]:
        """
        是什么：SystemLogger.create_log_record 是 backend/common/audit/schemas/logger_decorator.py 中的异步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：创建、初始化或组装审计日志相关对象和数据，并返回或写入对应状态。
        """
        try:
            # 获取用户信息
            user_info = cls.get_current_user(request)
            user_id = user_info.id if user_info else -1
            user_name = user_info.name if user_info else '-1'
            if config.operation_type == OperationType.LOGIN:
                user_id = resource_id
                user_name = resource_name

            # 获取客户端信息
            client_info = cls.get_client_info(request)
            # 获取请求参数
            request_params = None
            if config.extract_params:
                request_params = cls.extract_request_params(request)

            # 创建日志对象
            log = SystemLog(
                tenant_id=_user_tenant_id(user_info),
                operation_type=opt_type_ref if opt_type_ref else config.operation_type,
                operation_detail=config.operation_detail,
                user_id=user_id,
                user_name=user_name,
                operation_status=status,
                ip_address=client_info.get("ip_address"),
                user_agent=client_info.get("user_agent"),
                execution_time=execution_time,
                error_message=error_message,
                module=config.module,
                resource_id=str(resource_id),
                request_method=request.method if request else None,
                request_path=request.url.path if request else None,
                create_time=datetime.now(),
                remark=remark
            )


            with Session(engine) as session:
                session.add(log)
                session.commit()
                session.refresh(log)
                # 统一处理不同类型的 resource_id_info
                if isinstance(resource_id, list):
                    resource_ids = [str(rid) for rid in resource_id]
                else:
                    resource_ids = [str(resource_id)]
                # 批量添加 SystemLogsResource
                resource_entries = []
                for resource_id_details in resource_ids:
                    resource_entry = SystemLogsResource(
                        resource_id=resource_id_details,
                        log_id=log.id,
                        module=config.module
                    )
                    resource_entries.append(resource_entry)
                if resource_entries:
                    session.bulk_save_objects(resource_entries)
                    session.commit()

                if config.operation_type == OperationType.DELETE and resource_info_list is not None:
                    # 批量更新 SystemLogsResource 表的 resource_name
                    for resource_info in resource_info_list:
                        session.query(SystemLogsResource).filter(
                            SystemLogsResource.resource_id == resource_info['resource_id'],
                            SystemLogsResource.module == resource_info['module'],
                        ).update({
                            SystemLogsResource.resource_name: resource_info['resource_name']
                        }, synchronize_session='fetch')
                    session.commit()
                return log

        except Exception as e:
            print(f"[SystemLogger] Failed to create log: {str(traceback.format_exc())}")
            return None


def system_log(config: Union[LogConfig, Dict]):
    """
    是什么：system_log 是 backend/common/audit/schemas/logger_decorator.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 system_log 的语义处理审计日志相关逻辑，并把结果返回或写入状态。
    """
    # If a dictionary is passed in, convert it to a LogConfig object
    if isinstance(config, dict):
        config = LogConfig(**config)

    def decorator(func: Callable) -> Callable:
        """
        是什么：decorator 是 backend/common/audit/schemas/logger_decorator.py 中的同步函数。
        谁调用：由外层函数 system_log 在执行内部流程时调用。
        做了什么：围绕 decorator 的语义处理审计日志相关逻辑，并把结果返回或写入状态。
        """
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            """
            是什么：async_wrapper 是 backend/common/audit/schemas/logger_decorator.py 中的异步函数。
            谁调用：由外层函数 decorator 在执行内部流程时调用。
            做了什么：围绕 async_wrapper 的语义处理审计日志相关逻辑，并把结果返回或写入状态。
            """
            start_time = time.time()
            status = OperationStatus.SUCCESS
            error_message = None
            request = None
            resource_id = None
            resource_name = None
            remark = None
            opt_type_ref = None
            resource_info_list = None
            result = None

            try:
                # 获取当前请求
                request = RequestContext.get_request()
                func_signature = inspect.signature(func)
                bound_args = func_signature.bind(*args, **kwargs)
                bound_args.apply_defaults()
                unified_kwargs = dict(bound_args.arguments)

                # 第一步：尝试从参数中提取资源 ID
                if config.resource_id_expr:
                    resource_id = SystemLogger.extract_from_function_params(
                        config.resource_id_expr,
                        unified_kwargs,
                        kwargs
                    )
                if config.remark_expr:
                    remark = SystemLogger.extract_from_function_params(
                        config.remark_expr,
                        unified_kwargs,
                        kwargs
                    )

                if config.operation_type == OperationType.LOGIN:
                    input_account_dec = SystemLogger.extract_from_function_params(
                        "form_data.username",
                        args,
                        kwargs
                    )
                    from common.utils.crypto import shuzhi_decrypt
                    input_account = await shuzhi_decrypt(input_account_dec)
                    with Session(engine) as session:
                        userInfo = get_user_by_account(session=session, account=input_account)
                        if userInfo is not None:
                            resource_id = userInfo.id
                            resource_name = userInfo.name
                        else:
                            resource_id = -1
                            resource_name = input_account
                if config.operation_type == OperationType.DELETE:
                    with Session(engine) as session:
                        resource_info_list = get_resource_name_by_id_and_module(session, resource_id, config.module)

                if config.operation_type == OperationType.CREATE_OR_UPDATE:
                    opt_type_ref = OperationType.UPDATE if resource_id is not None else OperationType.CREATE
                else:
                    opt_type_ref = config.operation_type
                # 执行原始函数
                result = await func(*args, **kwargs)
                # 第二步：若配置为从结果中提取资源 ID 且此前未提取到，则从结果中提取。
                if config.result_id_expr and not resource_id and result:
                    resource_id = SystemLogger.extract_resource_id(
                        config.result_id_expr,
                        result,
                        "result"
                    )
                return result

            except Exception as e:
                status = OperationStatus.FAILED
                error_message = str(e)

                # If it is an HTTPException, retrieve the status code
                if isinstance(e, HTTPException):
                    error_message = f"HTTP {e.status_code}: {e.detail}"

                # If configured to ignore errors, mark as successful
                if config.ignore_errors:
                    status = OperationStatus.SUCCESS

                raise e

            finally:
                # If configured to only record on success and the current status is failure, skip
                if config.save_on_success_only and status == OperationStatus.FAILED:
                    return

                # 计算执行时间
                execution_time = int((time.time() - start_time) * 1000)
                # 异步创建日志记录
                try:
                    await SystemLogger.create_log_record(
                        config=config,
                        status=status,
                        execution_time=execution_time,
                        error_message=error_message,
                        resource_id=resource_id,
                        resource_name=resource_name,
                        remark=remark,
                        request=request,
                        opt_type_ref=opt_type_ref,
                        resource_info_list=resource_info_list
                    )
                except Exception as log_error:
                    print(f"[SystemLogger] Log creation failed: {log_error}")

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            """
            是什么：sync_wrapper 是 backend/common/audit/schemas/logger_decorator.py 中的同步函数。
            谁调用：由外层函数 decorator 在执行内部流程时调用。
            做了什么：更新审计日志相关状态、配置或持久化数据，并保持后续流程可继续使用。
            """
            start_time = time.time()
            status = OperationStatus.SUCCESS
            error_message = None
            request = None
            resource_id = None
            resource_name = None
            resource_info_list = None
            result = None

            try:
                # 获取当前请求
                request = RequestContext.get_request()
                func_signature = inspect.signature(func)
                bound_args = func_signature.bind(*args, **kwargs)
                bound_args.apply_defaults()
                unified_kwargs = dict(bound_args.arguments)

                # 从参数中提取资源 ID
                if config.resource_id_expr:
                    resource_id = SystemLogger.extract_from_function_params(
                        config.resource_id_expr,
                        unified_kwargs,
                        kwargs
                    )

                # 获取客户端信息
                if config.operation_type == OperationType.DELETE:
                    with Session(engine) as session:
                        resource_info_list = get_resource_name_by_id_and_module(session, resource_id, config.module)

                # 执行原始函数
                result = func(*args, **kwargs)

                # 从结果中提取资源 ID
                if config.result_id_expr and not resource_id and result:
                    resource_id = SystemLogger.extract_resource_id(
                        config.result_id_expr,
                        result,
                        "result"
                    )

                return result

            except Exception as e:
                status = OperationStatus.FAILED
                error_message = str(e)

                if isinstance(e, HTTPException):
                    error_message = f"HTTP {e.status_code}: {e.detail}"

                if config.ignore_errors:
                    status = OperationStatus.SUCCESS

                raise e

            finally:
                if config.save_on_success_only and status == OperationStatus.FAILED:
                    return

                execution_time = int((time.time() - start_time) * 1000)

                # 在同步版本中仍然异步创建日志。
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(
                            SystemLogger.create_log_record(
                                config=config,
                                status=status,
                                execution_time=execution_time,
                                error_message=error_message,
                                resource_id=resource_id,
                                resource_name=resource_name,
                                request=request,
                                resource_info_list=resource_info_list
                            )
                        )
                    else:
                        asyncio.run(
                            SystemLogger.create_log_record(
                                config=config,
                                status=status,
                                execution_time=execution_time,
                                error_message=error_message,
                                resource_id=resource_id,
                                request=request
                            )
                        )
                except Exception as log_error:
                    print(f"[SystemLogger] Log creation failed: {log_error}")

        # 根据函数类型返回合适的包装器
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
