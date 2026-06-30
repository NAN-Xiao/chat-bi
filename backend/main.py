"""
脚本说明：这个脚本是后端应用的入口，负责创建 FastAPI、挂载路由、启动缓存和注册中间件。
"""
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
    是什么：lifespan 是后端启动和关闭时会走的一段准备流程。
    谁调用：FastAPI 启动应用和关闭应用时会自动调用它。
    做了什么：启动时检查配置、准备缓存和模型信息，关闭时把缓存连接收好。
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
    是什么：custom_generate_unique_id 是给接口生成唯一名字的小工具。
    谁调用：FastAPI 生成 OpenAPI 文档时会调用它。
    做了什么：把接口分组和函数名拼在一起，让文档里的接口标识更好认。
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
    是什么：replace_placeholders_in_schema 是用来替换接口文档占位符的小工具。
    谁调用：生成不同语言的 OpenAPI 文档时会调用它。
    做了什么：遍历文档内容，把 PLACEHOLDER 这类标记换成真正要展示的文字。
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
    是什么：get_language_from_request 是用来判断用户想看哪种语言文档的小工具。
    谁调用：打开 OpenAPI 或 Swagger 文档时会调用它。
    做了什么：优先看 URL 里的 lang，没有就再看浏览器语言，最后给出默认语言。
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
    是什么：generate_openapi_for_lang 是按语言生成接口文档内容的小工具。
    谁调用：用户请求 OpenAPI 文档时会调用它。
    做了什么：把接口分组、描述和占位符换成对应语言，并把结果缓存起来。
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
    是什么：custom_openapi 是返回 OpenAPI JSON 文档的接口。
    谁调用：浏览器或工具请求 OpenAPI 地址时，FastAPI 会调用它。
    做了什么：按请求语言生成接口文档，然后以 JSON 形式返回。
    """
    lang = get_language_from_request(request)
    schema = generate_openapi_for_lang(lang)
    return JSONResponse(schema)


@app.get(f"{settings.CONTEXT_PATH}/docs", include_in_schema=False)
async def custom_swagger_ui(request: Request):
    """
    是什么：custom_swagger_ui 是打开 Swagger 页面的接口。
    谁调用：用户访问文档页面时，FastAPI 会调用它。
    做了什么：根据当前语言组装 Swagger 页面，让用户可以在浏览器里看接口。
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
    是什么：health 是检查后端是否还活着的接口。
    谁调用：健康检查工具、运维脚本或浏览器请求时会调用它。
    做了什么：返回服务当前是否可用的简单信息。
    """
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get(f"{settings.CONTEXT_PATH}/ready", include_in_schema=False)
async def ready():
    """
    是什么：ready 是检查后端准备好没有的接口。
    谁调用：健康检查工具或部署系统确认服务可接流量时会调用它。
    做了什么：检查缓存等关键依赖的状态，再告诉外部服务是否已经准备好。
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
