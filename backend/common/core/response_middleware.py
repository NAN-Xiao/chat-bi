"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import json

from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from common.core.config import settings
from common.utils.utils import AppLogUtil


def _allowed_cors_origins() -> set[str]:
    """
    是什么：_allowed_cors_origins 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查后端基础能力里的数据、权限或配置是否合法，不对就及时拦住。
    """
    origins = {origin.rstrip("/") for origin in settings.all_cors_origins if origin}
    for instance in ResponseMiddleware.instances:
        origins.update(
            origin.rstrip("/")
            for origin in instance.allow_origins
            if origin and origin != "'self'"
        )
    return origins


def cors_headers_for_request(request: Request) -> dict[str, str]:
    """
    是什么：cors_headers_for_request 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    origin = request.headers.get("origin")
    if not origin:
        return {}
    normalized_origin = origin.rstrip("/")
    if normalized_origin not in _allowed_cors_origins():
        return {}
    return {
        "Access-Control-Allow-Origin": normalized_origin,
        "Vary": "Origin",
    }


def _safe_http_exception_content(exc: HTTPException):
    """
    是什么：_safe_http_exception_content 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if exc.status_code >= 500:
        return "Internal server error"
    return exc.detail


def _add_security_headers(response):
    """
    是什么：_add_security_headers 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存后端基础能力需要的东西，让后续流程能继续往下走。
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.APP_ENV == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


class ResponseMiddleware(BaseHTTPMiddleware):
    """
    类说明：ResponseMiddleware 用来在请求进入接口前先做一层处理，比如登录、租户或响应格式。
    """
    instances = []

    def __init__(self, app, allow_origins: list[str] | None = None):
        """
        是什么：ResponseMiddleware.__init__ 是 ResponseMiddleware 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：创建 ResponseMiddleware 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        super().__init__(app)
        self.allow_origins = allow_origins or ["'self'"]
        ResponseMiddleware.instances.append(self)

    def update_allow_origins(self, new_allow_origins: list[str] | None = None):
        """
        是什么：ResponseMiddleware.update_allow_origins 是 ResponseMiddleware 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：拿到 ResponseMiddleware 对象的代码，需要完成这个动作时会调用它。
        做了什么：把后端基础能力相关的信息改成最新状态，并保存这些变化。
        """
        if not new_allow_origins:
            return
        self.allow_origins = list(set(self.allow_origins + new_allow_origins))

    async def dispatch(self, request, call_next):
        """
        是什么：ResponseMiddleware.dispatch 是 ResponseMiddleware 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：每个请求经过这个中间件时，FastAPI 会调用它。
        做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
        """
        response = await call_next(request)
        _add_security_headers(response)

        direct_paths = [
            f"{settings.API_V1_STR}/mcp/mcp_question",
            f"{settings.API_V1_STR}/mcp/mcp_assistant",
            f"{settings.CONTEXT_PATH}/openapi.json",
            f"{settings.CONTEXT_PATH}/docs",
            f"{settings.CONTEXT_PATH}/redoc"
        ]

        route = request.scope.get("route")
        # 获取定义的路径模式，例如 '/items/{item_id}'
        path_pattern = '' if not route else route.path_format

        if (isinstance(response, JSONResponse)
                or request.url.path == f"{settings.CONTEXT_PATH}/openapi.json"
                or path_pattern in direct_paths):
            return response
        if response.status_code != 200:
            return response
        if response.headers.get("content-type") == "application/json":
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                raw_data = json.loads(body.decode())

                if isinstance(raw_data, dict) and all(k in raw_data for k in ["code", "data", "msg"]):
                    return JSONResponse(
                        content=raw_data,
                        status_code=response.status_code,
                        headers={
                            k: v for k, v in response.headers.items()
                            if k.lower() not in ("content-length", "content-type")
                        }
                    )

                wrapped_data = {
                    "code": 0,
                    "data": raw_data,
                    "msg": None
                }

                return JSONResponse(
                    content=wrapped_data,
                    status_code=response.status_code,
                    headers={
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ("content-length", "content-type")
                    }
                )
            except Exception as e:
                AppLogUtil.error(f"Response processing error: {str(e)}", exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content="Internal server error",
                    headers={
                        k: v for k, v in response.headers.items()
                        if k.lower() not in ("content-length", "content-type")
                    }
                )
        content_type = response.headers.get("content-type", "")
        static_content_types = ["text/html", "javascript", "typescript", "css"]
        if any(ct in content_type for ct in static_content_types):
            if self.allow_origins:
                frame_ancestors_value = " ".join(self.allow_origins)
                response.headers["Content-Security-Policy"] = f"frame-ancestors {frame_ancestors_value};"

        return response


class exception_handler:
    """
    类说明：exception_handler 表示后端基础能力过程里的特定错误，让上层能更准确地提示或处理。
    """
    @staticmethod
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        是什么：exception_handler.http_exception_handler 是 exception_handler 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        AppLogUtil.error(f"HTTP Exception: {exc.detail}", exc_info=True)
        return _add_security_headers(JSONResponse(
            status_code=exc.status_code,
            content=_safe_http_exception_content(exc),
            headers=cors_headers_for_request(request)
        ))

    @staticmethod
    async def global_exception_handler(request: Request, exc: Exception):
        """
        是什么：exception_handler.global_exception_handler 是 exception_handler 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        AppLogUtil.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
        return _add_security_headers(JSONResponse(
            status_code=500,
            content="Internal server error",
            headers=cors_headers_for_request(request)
        ))
