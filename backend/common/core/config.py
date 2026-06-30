"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import secrets
import urllib.parse
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    PostgresDsn,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    """
    是什么：parse_cors 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    """
    类说明：Settings 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    model_config = SettingsConfigDict(
        # 使用顶层 .env 文件（位于 ./backend/ 上一级）。
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    PROJECT_NAME: str = "星通数智"
    APP_ENV: Literal["development", "test", "production"] = "development"
    PRODUCTION_CHECKS_ENABLED: bool = True
    AUTO_RUN_MIGRATIONS: bool = False
    # CONTEXT_PATH: str = "/shuzhi"
    CONTEXT_PATH: str = ""
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 分钟 * 24 小时 * 8 天 = 8 天
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    LOCAL_DEV_FRONTEND_HOSTS: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    ENABLE_LOCAL_DEV_CORS: bool = True

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        """
        是什么：Settings.all_cors_origins 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        origins = [
            *[str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS],
            self.FRONTEND_HOST,
        ]
        if self.ENABLE_LOCAL_DEV_CORS:
            origins.extend(self.LOCAL_DEV_FRONTEND_HOSTS)
        return list(dict.fromkeys(origin.rstrip("/") for origin in origins if origin))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def API_V1_STR(self) -> str:
        """
        是什么：Settings.API_V1_STR 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.CONTEXT_PATH + "/api/v1"

    SHUZHI_DB_HOST: str = "10.1.5.28"
    SHUZHI_DB_PORT: int = 5432
    SHUZHI_DB_DB: str = "zhishu_bi"
    SHUZHI_DB_USER: str = "root"
    SHUZHI_DB_PASSWORD: str = "Password123@pg"
    POSTGRES_SERVER: str = ''
    POSTGRES_PORT: int | None = None
    POSTGRES_USER: str = ''
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    SHUZHI_DB_URL: str = ''
    # SHUZHI_DB_URL: str = 'mysql+pymysql://root:Password123%40mysql@127.0.0.1:3306/shuzhi'

    TOKEN_KEY: str = "X-SHUZHI-TOKEN"
    DEFAULT_PWD: str = "elex@123"
    ASSISTANT_TOKEN_KEY: str = "X-SHUZHI-ASSISTANT-TOKEN"
    SENSITIVE_CONFIG_ENCRYPTION_KEY: str | None = None
    DATASOURCE_CONFIG_ENCRYPTION_KEY: str | None = None
    LEGACY_CONFIG_AES_KEYS: str = ""
    LOGIN_RATE_LIMIT_ENABLED: bool = True
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_FAILURE_WINDOW_SECONDS: int = 15 * 60
    LOGIN_LOCKOUT_SECONDS: int = 15 * 60
    TENANT_RATE_LIMIT_ENABLED: bool = True
    TENANT_CHAT_REQUESTS_PER_MINUTE: int = 60
    TENANT_ANALYSIS_REQUESTS_PER_MINUTE: int = 20
    TENANT_RECOMMEND_REQUESTS_PER_MINUTE: int = 30
    TENANT_LLM_REQUESTS_PER_MINUTE: int = 60
    TENANT_RATE_LIMIT_PLAN_OVERRIDES: str = ""
    TENANT_USAGE_METERING_ENABLED: bool = True
    TENANT_USAGE_QUOTA_ENABLED: bool = True
    TENANT_USAGE_QUOTA_PLAN_LIMITS: str = ""
    MAX_UPLOAD_BYTES: int = 100 * 1024 * 1024

    CACHE_TYPE: Literal["redis", "memory", "none"] = "redis"
    CACHE_REDIS_URL: str | None = None  # Redis 地址示例："redis://[[username]:[password]]@localhost:6379/0"。
    CACHE_REDIS_PREFIX: str = "shuzhi-cache"

    DASHBOARD_SQL_PREVIEW_CACHE_TTL_SECONDS: int = 3600
    DASHBOARD_SQL_PREVIEW_CACHE_MAX_ENTRIES: int = 512
    DASHBOARD_SQL_PREVIEW_DATASOURCE_CONCURRENCY: int = 2
    DASHBOARD_SQL_PREVIEW_WAIT_TIMEOUT_SECONDS: float = 1.0
    DASHBOARD_SQL_PREVIEW_DEDUPE_WAIT_TIMEOUT_SECONDS: float = 8.0
    DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS: int = 60

    SHUZHI_REDIS_URL: str | None = None
    REDIS_URL: str | None = None
    SHUZHI_REDIS_HOST: str = "10.1.5.28"
    SHUZHI_REDIS_PORT: int = 6379
    REDIS_HOST: str = ""
    REDIS_PORT: int | None = None
    REDIS_DB: int = 0
    REDIS_USERNAME: str | None = None
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False
    REDIS_SOCKET_TIMEOUT: float = 10.0
    REDIS_CONNECT_TIMEOUT: float = 3.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_MAX_CONNECTIONS: int = 100
    REDIS_KEY_PREFIX: str = "shuzhi"

    TASK_QUEUE_NAME: str = "default"
    TASK_QUEUE_RESULT_TTL_SECONDS: int = 60 * 60 * 24
    TASK_QUEUE_POLL_TIMEOUT_SECONDS: int = 5
    TASK_QUEUE_MAX_ATTEMPTS: int = 1
    TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS: int = 60 * 60
    TASK_QUEUE_REQUEUE_INTERVAL_SECONDS: int = 60
    TASK_QUEUE_MAX_PENDING_PER_TENANT: int = 0
    TASK_QUEUE_MAX_PROCESSING_PER_TENANT: int = 0

    LOG_LEVEL: str = "INFO"  # 日志级别：DEBUG、INFO、WARNING、ERROR。
    LOG_DIR: str = "logs"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"
    SQL_DEBUG: bool = False
    BASE_DIR: str = "/opt/shuzhi"
    SCRIPT_DIR: str = f"{BASE_DIR}/scripts"
    UPLOAD_DIR: str = "/opt/shuzhi/data/file"
    SHUZHI_KEY_EXPIRED: int = 100  # 许可证密钥过期时间戳，0 表示永不过期。

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn | str:
        """
        是什么：Settings.SQLALCHEMY_DATABASE_URI 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if self.SHUZHI_DB_URL:
            return self.SHUZHI_DB_URL
        # return MultiHostUrl.build(
        #     scheme="postgresql+psycopg",
        #     username=urllib.parse.quote(self.core_db_user),
        #     password=urllib.parse.quote(self.core_db_password),
        #     host=self.core_db_host,
        #     port=self.core_db_port,
        #     path=self.core_db_name,
        # )
        return (
            "postgresql+psycopg://"
            f"{urllib.parse.quote(self.core_db_user)}:"
            f"{urllib.parse.quote(self.core_db_password)}@"
            f"{self.core_db_host}:{self.core_db_port}/{self.core_db_name}"
        )

    @property
    def core_db_host(self) -> str:
        """
        是什么：Settings.core_db_host 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.SHUZHI_DB_HOST

    @property
    def core_db_port(self) -> int:
        """
        是什么：Settings.core_db_port 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.SHUZHI_DB_PORT

    @property
    def core_db_user(self) -> str:
        """
        是什么：Settings.core_db_user 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.SHUZHI_DB_USER

    @property
    def core_db_password(self) -> str:
        """
        是什么：Settings.core_db_password 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.SHUZHI_DB_PASSWORD

    @property
    def core_db_name(self) -> str:
        """
        是什么：Settings.core_db_name 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：其他代码像读取属性一样访问它时，Python 会调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return self.SHUZHI_DB_DB

    MCP_IMAGE_PATH: str = '/opt/shuzhi/images'
    EXCEL_PATH: str = '/opt/shuzhi/data/excel'
    MCP_ENABLED: bool = False
    MCP_IMAGE_HOST: str = 'http://localhost:3000'
    SERVER_IMAGE_HOST: str = 'http://YOUR_SERVE_IP:MCP_PORT/images/'
    SERVER_IMAGE_TIMEOUT: int = 15
    LLM_REQUEST_TIMEOUT: int = 45
    LLM_MAX_RETRIES: int = 1

    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    DEFAULT_EMBEDDING_MODEL: str = 'text-embedding-v4'
    EMBEDDING_PROVIDER: Literal["openai"] = "openai"
    EMBEDDING_MODEL: str = 'text-embedding-v4'
    EMBEDDING_API_BASE_URL: str | None = None
    EMBEDDING_API_KEY: str | None = None
    EMBEDDING_USE_DEFAULT_AI_MODEL_CONFIG: bool = True
    EMBEDDING_REQUEST_TIMEOUT: int = 30
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_NORMALIZE: bool = True
    EMBEDDING_ENABLED: bool = True
    EMBEDDING_DEFAULT_SIMILARITY: float = 0.4
    EMBEDDING_TERMINOLOGY_SIMILARITY: float = EMBEDDING_DEFAULT_SIMILARITY
    EMBEDDING_DATA_TRAINING_SIMILARITY: float = EMBEDDING_DEFAULT_SIMILARITY
    EMBEDDING_DEFAULT_TOP_COUNT: int = 5
    EMBEDDING_TERMINOLOGY_TOP_COUNT: int = EMBEDDING_DEFAULT_TOP_COUNT
    EMBEDDING_DATA_TRAINING_TOP_COUNT: int = EMBEDDING_DEFAULT_TOP_COUNT

    # 是否启用SQL查询行数限制，默认值，可被参数配置覆盖
    GENERATE_SQL_QUERY_LIMIT_ENABLED: bool = True
    GENERATE_SQL_QUERY_HISTORY_ROUND_COUNT: int = 3

    # 安全配置：是否允许元数据查询（SHOW/DESCRIBE/DESC/EXPLAIN）
    # 默认关闭，防止通过元数据查询泄露数据库结构
    SHUZHI_ALLOW_METADATA_QUERIES: bool = False

    PARSE_REASONING_BLOCK_ENABLED: bool = True
    DEFAULT_REASONING_CONTENT_START: str = '<think>'
    DEFAULT_REASONING_CONTENT_END: str = '</think>'

    PG_POOL_SIZE: int = 20
    PG_MAX_OVERFLOW: int = 30
    PG_POOL_RECYCLE: int = 3600
    PG_POOL_PRE_PING: bool = True

    TABLE_EMBEDDING_ENABLED: bool = True
    TABLE_EMBEDDING_COUNT: int = 10
    DS_EMBEDDING_COUNT: int = 10

    ORACLE_CLIENT_PATH: str = '/opt/shuzhi/db_client/oracle_instant_client'
    ORACLE_THICK_MODE_ENABLED: bool = False

    @field_validator('SQL_DEBUG',
                     'EMBEDDING_ENABLED',
                     'GENERATE_SQL_QUERY_LIMIT_ENABLED',
                     'MCP_ENABLED',
                     'PARSE_REASONING_BLOCK_ENABLED',
                     'PG_POOL_PRE_PING',
                     'TABLE_EMBEDDING_ENABLED',
                     'EMBEDDING_USE_DEFAULT_AI_MODEL_CONFIG',
                     'EMBEDDING_NORMALIZE',
                     'REDIS_SSL',
                     'PRODUCTION_CHECKS_ENABLED',
                     'AUTO_RUN_MIGRATIONS',
                     'ENABLE_LOCAL_DEV_CORS',
                     'LOGIN_RATE_LIMIT_ENABLED',
                     'TENANT_RATE_LIMIT_ENABLED',
                     'TENANT_USAGE_METERING_ENABLED',
                     'TENANT_USAGE_QUOTA_ENABLED',
                     mode='before')
    @classmethod
    def lowercase_bool(cls, v: Any) -> Any:
        """
        是什么：Settings.lowercase_bool 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：创建或校验数据对象时，Pydantic 会自动调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower == 'true':
                return True
            elif v_lower == 'false':
                return False
        return v

    @field_validator('CACHE_TYPE', mode='before')
    @classmethod
    def lowercase_cache_type(cls, v: Any) -> Any:
        """
        是什么：Settings.lowercase_cache_type 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：创建或校验数据对象时，Pydantic 会自动调用它。
        做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if v is None:
            return "none"
        if isinstance(v, str):
            value = v.lower().strip()
            if value in ("", "null"):
                return "none"
            return value
        return v

    @field_validator('APP_ENV', mode='before')
    @classmethod
    def normalize_app_env(cls, v: Any) -> Any:
        """
        是什么：Settings.normalize_app_env 是 Settings 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：创建或校验数据对象时，Pydantic 会自动调用它。
        做了什么：把后端基础能力的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        if isinstance(v, str):
            value = v.lower().strip()
            return "production" if value == "prod" else value
        return v


settings = Settings()  # type: ignore
