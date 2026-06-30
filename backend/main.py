import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.concurrency import asynccontextmanager
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from apps.api import api_router
from apps.swagger.i18n import (
    DEFAULT_LANG,
    PLACEHOLDER_PREFIX,
    get_translation,
    i18n_list,
    tags_metadata,
)
from apps.system.crud.aimodel_manage import async_model_info
from apps.system.crud.assistant import init_dynamic_cors
from apps.system.middleware.auth import TokenMiddleware
from apps.system.schemas.permission import RequestContextMiddleware
from common.audit.schemas.request_context import RequestContextMiddlewareCommon
from common.core.app_cache import cache_health, close_app_cache, init_app_cache
from common.core.config import settings
from common.core.migrations import run_migrations
from common.core.production import init_observability, validate_production_settings
from common.core.response_middleware import ResponseMiddleware, exception_handler
from common.utils.utils import AppLogUtil

try:
    from fastapi_mcp import FastApiMCP
except Exception as exc:  # pragma: no cover - 本地运行时的防御性兜底
    FastApiMCP = None
    _FASTAPI_MCP_IMPORT_ERROR = exc
else:
    _FASTAPI_MCP_IMPORT_ERROR = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    是什么：lifespan 是 backend/main.py 中的异步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 lifespan 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    validate_production_settings()
    init_observability()
    if settings.AUTO_RUN_MIGRATIONS:
        run_migrations()
    await init_app_cache()
    init_dynamic_cors(app)
    AppLogUtil.info("✅ 星通数智 初始化完成")
    await async_model_info()  # 异步加密已有模型的密钥和地址
    yield
    await close_app_cache()
    AppLogUtil.info("星通数智 应用关闭")


def custom_generate_unique_id(route: APIRoute) -> str:
    """
    是什么：custom_generate_unique_id 是 backend/main.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 custom_generate_unique_id 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    tag = route.tags[0] if route.tags and len(route.tags) > 0 else ""
    return f"{tag}-{route.name}"


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.CONTEXT_PATH}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)
# 按不同文本缓存接口文档
_openapi_cache: dict[str, dict[str, Any]] = {}

# 替换占位符
def replace_placeholders_in_schema(schema: dict[str, Any], trans: dict[str, str]) -> None:
    """
    是什么：replace_placeholders_in_schema 是 backend/main.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 replace_placeholders_in_schema 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    if isinstance(schema, dict):
        for key, value in schema.items():
            if isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX):
                placeholder_key = value[len(PLACEHOLDER_PREFIX):]
                schema[key] = trans.get(placeholder_key, value)
            else:
                replace_placeholders_in_schema(value, trans)
    elif isinstance(schema, list):
        for item in schema:
            replace_placeholders_in_schema(item, trans)



# 构建 OpenAPI
def get_language_from_request(request: Request) -> str:
    # 从查询参数 ?lang=zh 获取语言
    """
    是什么：get_language_from_request 是 backend/main.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询后端业务相关数据，整理后返回给调用方。
    """
    lang = request.query_params.get("lang")
    if lang in i18n_list:
        return lang
    # 从 Accept-Language 请求头获取语言
    accept_lang = request.headers.get("accept-language", "")
    if "zh" in accept_lang.lower():
        return "zh"
    return DEFAULT_LANG


def generate_openapi_for_lang(lang: str) -> dict[str, Any]:
    """
    是什么：generate_openapi_for_lang 是 backend/main.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：基于输入上下文生成后端业务相关结果，并保存或返回给调用方。
    """
    if lang in _openapi_cache:
        return _openapi_cache[lang]

    # 标签元数据
    trans = get_translation(lang)
    localized_tags = []
    for tag in tags_metadata:
        desc = tag["description"]
        if desc.startswith(PLACEHOLDER_PREFIX):
            key = desc[len(PLACEHOLDER_PREFIX):]
            desc = trans.get(key, desc)
        localized_tags.append({
            "name": tag["name"],
            "description": desc
        })

    # 1. 创建 OpenAPI
    openapi_schema = get_openapi(
        title="星通数智 API Document" if lang == "en" else "星通数智 API 文档",
        version="1.0.0",
        routes=app.routes,
        tags=localized_tags
    )

    # OpenAPI 版本
    openapi_schema.setdefault("openapi", "3.1.0")

    # 2. 获取当前语言的翻译
    trans = get_translation(lang)

    # 3. 替换占位符
    replace_placeholders_in_schema(openapi_schema, trans)

    # 4. 写入缓存
    _openapi_cache[lang] = openapi_schema
    return openapi_schema



# 自定义 /openapi.json 和 /docs
@app.get(f"{settings.CONTEXT_PATH}/openapi.json", include_in_schema=False)
async def custom_openapi(request: Request):
    """
    是什么：custom_openapi 是 backend/main.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 custom_openapi 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    lang = get_language_from_request(request)
    schema = generate_openapi_for_lang(lang)
    return JSONResponse(schema)


@app.get(f"{settings.CONTEXT_PATH}/docs", include_in_schema=False)
async def custom_swagger_ui(request: Request):
    """
    是什么：custom_swagger_ui 是 backend/main.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 custom_swagger_ui 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    lang = get_language_from_request(request)
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=f"./openapi.json?lang={lang}",
        title="星通数智 API Docs",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_js_url="./swagger-ui-bundle.js",
        swagger_css_url="./swagger-ui.css",
    )


@app.get(f"{settings.CONTEXT_PATH}/health", include_in_schema=False)
async def health():
    """
    是什么：health 是 backend/main.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：围绕 health 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get(f"{settings.CONTEXT_PATH}/ready", include_in_schema=False)
async def ready():
    """
    是什么：ready 是 backend/main.py 中的异步 FastAPI 接口处理函数。
    谁调用：由 FastAPI 路由系统在匹配到对应 HTTP 请求时调用。
    做了什么：读取或查询后端业务相关数据，整理后返回给调用方。
    """
    cache = await cache_health()
    ok = cache.get("status") in {"ok", "disabled"}
    return JSONResponse(
        {
            "status": "ok" if ok else "error",
            "service": settings.PROJECT_NAME,
            "cache": cache,
        },
        status_code=200 if ok else 503,
    )


mcp_app = FastAPI()
# MCP 服务和图片路径
images_path = settings.MCP_IMAGE_PATH
os.makedirs(images_path, exist_ok=True)
mcp_app.mount("/images", StaticFiles(directory=images_path), name="images")

mcp = None
if settings.MCP_ENABLED and FastApiMCP is not None:
    mcp = FastApiMCP(
        app,
        name="星通数智 MCP Server",
        description="星通数智 MCP Server",
        describe_all_responses=True,
        describe_full_response_schema=True,
        include_operations=["mcp_datasource_list", "get_model_list", "mcp_question", "mcp_start", "mcp_assistant"]
    )
    mcp.mount(mcp_app)
elif settings.MCP_ENABLED:
    AppLogUtil.warning(f"Skip MCP server setup because fastapi_mcp is unavailable: {_FASTAPI_MCP_IMPORT_ERROR}")
else:
    AppLogUtil.info("MCP server is disabled by MCP_ENABLED=false")

# 设置全部已启用的 CORS 来源
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(TokenMiddleware)
app.add_middleware(ResponseMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(RequestContextMiddlewareCommon)
app.include_router(api_router, prefix=settings.API_V1_STR)

# 注册异常处理器
app.add_exception_handler(StarletteHTTPException, exception_handler.http_exception_handler)
app.add_exception_handler(Exception, exception_handler.global_exception_handler)

if mcp is not None:
    mcp.setup_server()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    # uvicorn.run("main:mcp_app", host="0.0.0.0", port=8001) # MCP 服务
