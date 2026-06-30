from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContext:
    _current_request: ContextVar[Request] = ContextVar("_current_request")

    @classmethod
    def set_request(cls, request: Request):
        """
        是什么：RequestContext.set_request 是 backend/common/audit/schemas/request_context.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：更新审计日志相关状态、配置或持久化数据，并保持后续流程可继续使用。
        """
        return cls._current_request.set(request)

    @classmethod
    def get_request(cls) -> Request:
        """
        是什么：RequestContext.get_request 是 backend/common/audit/schemas/request_context.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：读取或查询审计日志相关数据，整理后返回给调用方。
        """
        try:
            return cls._current_request.get()
        except LookupError:
            raise RuntimeError(
                "No request context found. "
                "Make sure RequestContextMiddleware is installed."
            )

    @classmethod
    def reset(cls, token):
        """
        是什么：RequestContext.reset 是 backend/common/audit/schemas/request_context.py 中的同步方法。
        谁调用：由类本身、子类或框架按照类方法约定调用。
        做了什么：删除或清理审计日志相关数据、缓存或临时状态。
        """
        cls._current_request.reset(token)


class RequestContextMiddlewareCommon(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 设置请求上下文
        """
        是什么：RequestContextMiddlewareCommon.dispatch 是 backend/common/audit/schemas/request_context.py 中的异步方法。
        谁调用：由持有 RequestContextMiddlewareCommon 实例的业务代码、框架回调或测试代码调用。
        做了什么：执行审计日志主流程，协调下游服务并处理结果或异常。
        """
        token = RequestContext.set_request(request)
        try:
            response = await call_next(request)
            return response
        finally:
            RequestContext.reset(token)