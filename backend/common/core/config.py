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
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",")]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    PROJECT_NAME: str = "星通智数"
    APP_ENV: Literal["development", "test", "production"] = "development"
    PRODUCTION_CHECKS_ENABLED: bool = True
    AUTO_RUN_MIGRATIONS: bool = True
    #CONTEXT_PATH: str = "/zhishu"
    CONTEXT_PATH: str = ""
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
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
        return self.CONTEXT_PATH + "/api/v1"

    POSTGRES_SERVER: str = 'localhost'
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = 'root'
    POSTGRES_PASSWORD: str = "Password123@pg"
    POSTGRES_DB: str = "zhishu_bi"
    ZHISHU_DB_URL: str = ''
    # ZHISHU_DB_URL: str = 'mysql+pymysql://root:Password123%40mysql@127.0.0.1:3306/zhishu'

    TOKEN_KEY: str = "X-ZHISHU-TOKEN"
    DEFAULT_PWD: str = "elex@123"
    ASSISTANT_TOKEN_KEY: str = "X-ZHISHU-ASSISTANT-TOKEN"
    SENSITIVE_CONFIG_ENCRYPTION_KEY: str | None = None
    DATASOURCE_CONFIG_ENCRYPTION_KEY: str | None = None
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

    CACHE_TYPE: Literal["redis", "memory", "none"] = "memory"
    CACHE_REDIS_URL: str | None = None  # Redis URL, e.g., "redis://[[username]:[password]]@localhost:6379/0"
    CACHE_REDIS_PREFIX: str = "zhishu-cache"

    REDIS_URL: str | None = None
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_USERNAME: str | None = None
    REDIS_PASSWORD: str | None = None
    REDIS_SSL: bool = False
    REDIS_SOCKET_TIMEOUT: float = 10.0
    REDIS_CONNECT_TIMEOUT: float = 3.0
    REDIS_HEALTH_CHECK_INTERVAL: int = 30
    REDIS_MAX_CONNECTIONS: int = 100
    REDIS_KEY_PREFIX: str = "zhishu"

    TASK_QUEUE_NAME: str = "default"
    TASK_QUEUE_RESULT_TTL_SECONDS: int = 60 * 60 * 24
    TASK_QUEUE_POLL_TIMEOUT_SECONDS: int = 5
    TASK_QUEUE_MAX_ATTEMPTS: int = 1
    TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS: int = 60 * 60
    TASK_QUEUE_REQUEUE_INTERVAL_SECONDS: int = 60
    TASK_QUEUE_MAX_PENDING_PER_TENANT: int = 0
    TASK_QUEUE_MAX_PROCESSING_PER_TENANT: int = 0

    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    LOG_DIR: str = "logs"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"
    SQL_DEBUG: bool = False
    BASE_DIR: str = "/opt/zhishu"
    SCRIPT_DIR: str = f"{BASE_DIR}/scripts"
    UPLOAD_DIR: str = "/opt/zhishu/data/file"
    ZHISHU_KEY_EXPIRED: int = 100  # License key expiration timestamp, 0 means no expiration

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn | str:
        if self.ZHISHU_DB_URL:
            return self.ZHISHU_DB_URL
        # return MultiHostUrl.build(
        #     scheme="postgresql+psycopg",
        #     username=urllib.parse.quote(self.POSTGRES_USER),
        #     password=urllib.parse.quote(self.POSTGRES_PASSWORD),
        #     host=self.POSTGRES_SERVER,
        #     port=self.POSTGRES_PORT,
        #     path=self.POSTGRES_DB,
        # )
        return f"postgresql+psycopg://{urllib.parse.quote(self.POSTGRES_USER)}:{urllib.parse.quote(self.POSTGRES_PASSWORD)}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    MCP_IMAGE_PATH: str = '/opt/zhishu/images'
    EXCEL_PATH: str = '/opt/zhishu/data/excel'
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
    ZHISHU_ALLOW_METADATA_QUERIES: bool = False

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

    ORACLE_CLIENT_PATH: str = '/opt/zhishu/db_client/oracle_instant_client'

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
        """将字符串形式的布尔值转换为Python布尔值"""
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
        if isinstance(v, str):
            value = v.lower().strip()
            return "production" if value == "prod" else value
        return v


settings = Settings()  # type: ignore
