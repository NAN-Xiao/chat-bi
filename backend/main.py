import logging
from fastapi.concurrency import asynccontextmanager
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import sentry_sdk
from fastapi import FastAPI, Path, HTTPException
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from apps.api import api_router
from apps.system.middleware.auth import TokenMiddleware
from common.core.config import settings
from common.core.response_middleware import ResponseMiddleware, exception_handler
from alembic.config import Config
from alembic import command

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    yield

def custom_generate_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags and len(route.tags) > 0 else ""
    return f"{tag}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan
)

# Set all CORS enabled origins
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
app.include_router(api_router, prefix=settings.API_V1_STR)

# Register exception handlers
app.add_exception_handler(StarletteHTTPException, exception_handler.http_exception_handler)
app.add_exception_handler(Exception, exception_handler.global_exception_handler)

frontend_dist = os.path.abspath("../frontend/dist")
if not os.path.exists(frontend_dist):
    logging.warning(f"The front-end build directory does not exist: {frontend_dist}")
    logging.warning("Please make sure you have built the front-end project")
    
else:

    @app.get("/", include_in_schema=False)
    async def read_index():
        return FileResponse(path=os.path.join(frontend_dist, "index.html"))
    
    app.mount("/", StaticFiles(directory=frontend_dist), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)