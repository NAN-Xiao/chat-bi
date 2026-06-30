"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from common.core.config import settings
from common.utils.utils import AppLogUtil

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_DEVELOPMENT_DEFAULT_PASSWORDS = {"Shuzhi@123456", "elex@123"}


def _env_present(name: str) -> bool:
    """
    是什么：_env_present 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return bool(os.environ.get(name))


def _host_from_origin(origin: str) -> str:
    """
    是什么：_host_from_origin 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parsed = urlsplit(origin)
    return parsed.hostname or ""


def _is_local_origin(origin: str) -> bool:
    """
    是什么：_is_local_origin 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return _host_from_origin(origin).lower() in _LOCAL_HOSTS


def _redis_url_has_auth(url: str | None) -> bool:
    """
    是什么：_redis_url_has_auth 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not url:
        return False
    parsed = urlsplit(url)
    return bool(parsed.password or (parsed.username and "@" in parsed.netloc))


def _is_absolute_path(value: str) -> bool:
    """
    是什么：_is_absolute_path 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return bool(value) and (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _configured_cors_origins() -> list[str]:
    """
    是什么：_configured_cors_origins 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    origins = settings.BACKEND_CORS_ORIGINS
    if isinstance(origins, str):
        return [item.strip().rstrip("/") for item in origins.split(",") if item.strip()]
    return [str(origin).rstrip("/") for origin in origins]


def validate_production_settings() -> list[str]:
    """
    是什么：validate_production_settings 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查后端基础能力里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if settings.APP_ENV != "production":
        return []

    errors: list[str] = []

    if not _env_present("SECRET_KEY") or len(settings.SECRET_KEY) < 32:
        errors.append("SECRET_KEY must be set from environment and be at least 32 characters.")
    if settings.DEFAULT_PWD in _DEVELOPMENT_DEFAULT_PASSWORDS:
        errors.append("DEFAULT_PWD must be changed from the development default.")
    if settings.core_db_password == "Password123@pg":
        errors.append("Core database password must be changed from the development default.")
    sensitive_key = settings.SENSITIVE_CONFIG_ENCRYPTION_KEY or settings.DATASOURCE_CONFIG_ENCRYPTION_KEY
    if not (_env_present("SENSITIVE_CONFIG_ENCRYPTION_KEY") or _env_present("DATASOURCE_CONFIG_ENCRYPTION_KEY")):
        errors.append("SENSITIVE_CONFIG_ENCRYPTION_KEY must be set from environment in production.")
    elif len(sensitive_key or "") < 32:
        errors.append("SENSITIVE_CONFIG_ENCRYPTION_KEY must be at least 32 characters.")
    if settings.CACHE_TYPE != "redis":
        errors.append("CACHE_TYPE must be redis for production multi-tenant deployments.")
    if settings.AUTO_RUN_MIGRATIONS:
        errors.append(
            "AUTO_RUN_MIGRATIONS must be false in production; run database migrations as a separate release step."
        )

    redis_url = settings.SHUZHI_REDIS_URL
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
    if settings.SHUZHI_ALLOW_METADATA_QUERIES:
        errors.append("SHUZHI_ALLOW_METADATA_QUERIES must stay false in production.")
    if settings.TASK_QUEUE_MAX_ATTEMPTS < 2:
        errors.append("TASK_QUEUE_MAX_ATTEMPTS should be at least 2 in production.")
    if settings.TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS <= 0:
        errors.append("TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS must be greater than 0.")
    if settings.TASK_QUEUE_MAX_PENDING_PER_TENANT < 0:
        errors.append("TASK_QUEUE_MAX_PENDING_PER_TENANT must be greater than or equal to 0.")
    if settings.TASK_QUEUE_MAX_PROCESSING_PER_TENANT < 0:
        errors.append("TASK_QUEUE_MAX_PROCESSING_PER_TENANT must be greater than or equal to 0.")
    if not settings.TENANT_RATE_LIMIT_ENABLED:
        errors.append("TENANT_RATE_LIMIT_ENABLED must be true in production.")
    if not settings.TENANT_USAGE_METERING_ENABLED:
        errors.append("TENANT_USAGE_METERING_ENABLED must be true in production.")
    if not settings.TENANT_USAGE_QUOTA_ENABLED:
        errors.append("TENANT_USAGE_QUOTA_ENABLED must be true in production.")
    if settings.TENANT_RATE_LIMIT_PLAN_OVERRIDES:
        try:
            plan_overrides = json.loads(settings.TENANT_RATE_LIMIT_PLAN_OVERRIDES)
        except json.JSONDecodeError:
            errors.append("TENANT_RATE_LIMIT_PLAN_OVERRIDES must be valid JSON.")
        else:
            if not isinstance(plan_overrides, dict):
                errors.append("TENANT_RATE_LIMIT_PLAN_OVERRIDES must be a JSON object.")
    if settings.TENANT_USAGE_QUOTA_PLAN_LIMITS:
        try:
            quota_limits = json.loads(settings.TENANT_USAGE_QUOTA_PLAN_LIMITS)
        except json.JSONDecodeError:
            errors.append("TENANT_USAGE_QUOTA_PLAN_LIMITS must be valid JSON.")
        else:
            if not isinstance(quota_limits, dict):
                errors.append("TENANT_USAGE_QUOTA_PLAN_LIMITS must be a JSON object.")
    for name in (
        "TENANT_CHAT_REQUESTS_PER_MINUTE",
        "TENANT_ANALYSIS_REQUESTS_PER_MINUTE",
        "TENANT_RECOMMEND_REQUESTS_PER_MINUTE",
        "TENANT_LLM_REQUESTS_PER_MINUTE",
    ):
        if int(getattr(settings, name)) <= 0:
            errors.append(f"{name} must be greater than 0 in production.")
    if settings.MAX_UPLOAD_BYTES <= 0:
        errors.append("MAX_UPLOAD_BYTES must be greater than 0 in production.")
    if settings.MAX_UPLOAD_BYTES > 100 * 1024 * 1024:
        errors.append("MAX_UPLOAD_BYTES must not exceed 100 MiB in production.")

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
    """
    是什么：init_observability 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存后端基础能力需要的东西，让后续流程能继续往下走。
    """
    if not settings.SENTRY_DSN:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT or settings.APP_ENV,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    AppLogUtil.info("Sentry observability initialized")
