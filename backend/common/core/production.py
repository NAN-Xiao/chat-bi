import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from common.core.config import settings
from common.utils.utils import AppLogUtil

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_DEVELOPMENT_DEFAULT_PASSWORDS = {"elex@123", "Zhishu@123456"}


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def _host_from_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    return parsed.hostname or ""


def _is_local_origin(origin: str) -> bool:
    return _host_from_origin(origin).lower() in _LOCAL_HOSTS


def _redis_url_has_auth(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlsplit(url)
    return bool(parsed.password or (parsed.username and "@" in parsed.netloc))


def _is_absolute_path(value: str) -> bool:
    return bool(value) and (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _configured_cors_origins() -> list[str]:
    origins = settings.BACKEND_CORS_ORIGINS
    if isinstance(origins, str):
        return [item.strip().rstrip("/") for item in origins.split(",") if item.strip()]
    return [str(origin).rstrip("/") for origin in origins]


def validate_production_settings() -> list[str]:
    """Return production setting errors, and raise when production checks are active."""
    if settings.APP_ENV != "production":
        return []

    errors: list[str] = []

    if not _env_present("SECRET_KEY") or len(settings.SECRET_KEY) < 32:
        errors.append("SECRET_KEY must be set from environment and be at least 32 characters.")
    if settings.DEFAULT_PWD in _DEVELOPMENT_DEFAULT_PASSWORDS:
        errors.append("DEFAULT_PWD must be changed from the development default.")
    if settings.POSTGRES_PASSWORD == "Password123@pg":
        errors.append("POSTGRES_PASSWORD must be changed from the development default.")
    sensitive_key = settings.SENSITIVE_CONFIG_ENCRYPTION_KEY or settings.DATASOURCE_CONFIG_ENCRYPTION_KEY
    if not (_env_present("SENSITIVE_CONFIG_ENCRYPTION_KEY") or _env_present("DATASOURCE_CONFIG_ENCRYPTION_KEY")):
        errors.append("SENSITIVE_CONFIG_ENCRYPTION_KEY must be set from environment in production.")
    elif len(sensitive_key or "") < 32:
        errors.append("SENSITIVE_CONFIG_ENCRYPTION_KEY must be at least 32 characters.")
    if settings.CACHE_TYPE != "redis":
        errors.append("CACHE_TYPE must be redis for production single-tenant deployments.")
    if settings.AUTO_MIGRATE_ON_STARTUP:
        errors.append("AUTO_MIGRATE_ON_STARTUP must be false in production; run Alembic as a separate deployment step.")

    redis_url = settings.CACHE_REDIS_URL or settings.REDIS_URL
    if not settings.REDIS_PASSWORD and not _redis_url_has_auth(redis_url):
        errors.append("Redis must require authentication through REDIS_PASSWORD, REDIS_URL, or CACHE_REDIS_URL.")

    cors_origins = _configured_cors_origins()
    if not cors_origins:
        errors.append("BACKEND_CORS_ORIGINS must contain the production frontend origin.")
    if any(origin == "*" for origin in cors_origins):
        errors.append("BACKEND_CORS_ORIGINS must not contain '*'.")
    if any(_is_local_origin(origin) for origin in cors_origins):
        errors.append("BACKEND_CORS_ORIGINS must not contain localhost or loopback origins in production.")
    if _is_local_origin(settings.FRONTEND_HOST):
        errors.append("FRONTEND_HOST must be the production frontend origin.")
    if settings.ENABLE_LOCAL_DEV_CORS:
        errors.append("ENABLE_LOCAL_DEV_CORS must be false in production.")

    if settings.LOG_LEVEL.upper() == "DEBUG":
        errors.append("LOG_LEVEL must not be DEBUG in production.")
    if settings.SQL_DEBUG:
        errors.append("SQL_DEBUG must be false in production.")
    if settings.ZHISHU_ALLOW_METADATA_QUERIES:
        errors.append("ZHISHU_ALLOW_METADATA_QUERIES must stay false in production.")
    if settings.TASK_QUEUE_MAX_ATTEMPTS < 2:
        errors.append("TASK_QUEUE_MAX_ATTEMPTS should be at least 2 in production.")
    if settings.TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS <= 0:
        errors.append("TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS must be greater than 0.")
    if not settings.LOGIN_RATE_LIMIT_ENABLED:
        errors.append("LOGIN_RATE_LIMIT_ENABLED must be true in production.")
    if settings.LOGIN_MAX_FAILED_ATTEMPTS <= 0 or settings.LOGIN_MAX_FAILED_ATTEMPTS > 10:
        errors.append("LOGIN_MAX_FAILED_ATTEMPTS must be between 1 and 10 in production.")
    if settings.LOGIN_LOCKOUT_SECONDS <= 0:
        errors.append("LOGIN_LOCKOUT_SECONDS must be greater than 0 in production.")
    if settings.MAX_UPLOAD_BYTES <= 0:
        errors.append("MAX_UPLOAD_BYTES must be greater than 0 in production.")
    if settings.MAX_UPLOAD_BYTES > 100 * 1024 * 1024:
        errors.append("MAX_UPLOAD_BYTES must not exceed 100 MiB in production.")
    if settings.LLM_REQUEST_TIMEOUT <= 0 or settings.LLM_REQUEST_TIMEOUT > 120:
        errors.append("LLM_REQUEST_TIMEOUT must be between 1 and 120 seconds in production.")
    if settings.SQL_QUERY_EXECUTION_TIMEOUT_SECONDS <= 0 or settings.SQL_QUERY_EXECUTION_TIMEOUT_SECONDS > 120:
        errors.append("SQL_QUERY_EXECUTION_TIMEOUT_SECONDS must be between 1 and 120 seconds in production.")
    if settings.SQL_QUERY_DEFAULT_ROW_LIMIT <= 0 or settings.SQL_QUERY_DEFAULT_ROW_LIMIT > 1000:
        errors.append("SQL_QUERY_DEFAULT_ROW_LIMIT must be between 1 and 1000 in production.")
    if settings.ANALYSIS_ASSISTANT_MAX_QUERIES <= 0 or settings.ANALYSIS_ASSISTANT_MAX_QUERIES > 4:
        errors.append("ANALYSIS_ASSISTANT_MAX_QUERIES must be between 1 and 4 in production.")
    if settings.ANALYSIS_ASSISTANT_MAX_SQL_ROWS <= 0 or settings.ANALYSIS_ASSISTANT_MAX_SQL_ROWS > 1000:
        errors.append("ANALYSIS_ASSISTANT_MAX_SQL_ROWS must be between 1 and 1000 in production.")
    if settings.CHAT_EXPORT_MAX_ROWS <= 0 or settings.CHAT_EXPORT_MAX_ROWS > 100000:
        errors.append("CHAT_EXPORT_MAX_ROWS must be between 1 and 100000 in production.")
    if not settings.CHAT_GENERATION_CONCURRENCY_LIMIT_ENABLED:
        errors.append("CHAT_GENERATION_CONCURRENCY_LIMIT_ENABLED must be true in production.")
    if (
        settings.CHAT_MAX_CONCURRENT_GENERATIONS_PER_USER <= 0
        or settings.CHAT_MAX_CONCURRENT_GENERATIONS_PER_USER > 2
    ):
        errors.append("CHAT_MAX_CONCURRENT_GENERATIONS_PER_USER must be between 1 and 2 in production.")
    if (
        settings.CHAT_GENERATION_TOTAL_TIMEOUT_SECONDS <= 0
        or settings.CHAT_GENERATION_TOTAL_TIMEOUT_SECONDS > 600
    ):
        errors.append("CHAT_GENERATION_TOTAL_TIMEOUT_SECONDS must be between 1 and 600 seconds in production.")
    if (
        settings.CHAT_GENERATION_WORKER_MAX_THREADS <= 0
        or settings.CHAT_GENERATION_WORKER_MAX_THREADS > 200
    ):
        errors.append("CHAT_GENERATION_WORKER_MAX_THREADS must be between 1 and 200 in production.")

    for name in ("BASE_DIR", "UPLOAD_DIR", "EXCEL_PATH", "MCP_IMAGE_PATH", "LOG_DIR"):
        if not _is_absolute_path(str(getattr(settings, name))):
            errors.append(f"{name} must be an absolute path in production.")

    if settings.MCP_ENABLED and "YOUR_SERVE_IP" in settings.SERVER_IMAGE_HOST:
        errors.append("SERVER_IMAGE_HOST must be configured when MCP_ENABLED=true.")

    if errors and settings.PRODUCTION_CHECKS_ENABLED:
        message = "Invalid production settings:\n- " + "\n- ".join(errors)
        raise RuntimeError(message)
    return errors


def init_observability() -> None:
    if not settings.SENTRY_DSN:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or settings.APP_ENV,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    AppLogUtil.info("Sentry observability initialized")
