"""
脚本说明：这个脚本定义操作日志的输入输出结构，帮接口和业务代码统一数据格式。
"""
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContext:
    """
    类说明：RequestContext 用来描述操作日志的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    _current_request: ContextVar[Request] = ContextVar("_current_request")

    @classmethod
    def set_request(cls, request: Request):
        """
        是什么：RequestContext.set_request 是 RequestContext 里的一个步骤，帮它完成操作日志相关的一件事。
        谁调用：需要通过类本身做这件事时，代码会调用它。
        做了什么：把操作日志相关的信息改成最新状态，并保存这些变化。
        """
        return cls._current_request.set(request)

    @classmethod
    def get_request(cls) -> Request:
        """
        是什么：RequestContext.get_request 是 RequestContext 里的一个步骤，帮它完成操作日志相关的一件事。
        谁调用：需要通过类本身做这件事时，代码会调用它。
        做了什么：把操作日志需要的数据找出来，整理成后面好用的样子。
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
        是什么：RequestContext.reset 是 RequestContext 里的一个步骤，帮它完成操作日志相关的一件事。
        谁调用：需要通过类本身做这件事时，代码会调用它。
        做了什么：把操作日志不再需要的数据、缓存或临时内容清理掉。
        """
        cls._current_request.reset(token)


class RequestContextMiddlewareCommon(BaseHTTPMiddleware):
    """
    类说明：RequestContextMiddlewareCommon 用来描述操作日志的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    async def dispatch(self, request: Request, call_next):
        # 设置请求上下文
        """
        是什么：RequestContextMiddlewareCommon.dispatch 是 RequestContextMiddlewareCommon 里的一个步骤，帮它完成操作日志相关的一件事。
        谁调用：拿到 RequestContextMiddlewareCommon 对象的代码，需要完成这个动作时会调用它。
        做了什么：把操作日志的主要流程跑起来，一步步调用需要的处理。
        """
        token = RequestContext.set_request(request)
        try:
            response = await call_next(request)
            return response
        finally:
            RequestContext.reset(token)