"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""

from pydantic import BaseModel, Field
from typing import Optional


class SecurityConfig(BaseModel):
    """
    类说明：SecurityConfig 放后端基础能力的配置项，让后续流程能按同一套规则运行。
    """

    # SSL/TLS 设置
    verify_ssl_certificates: bool = Field(
        default=True,
        description="Enable SSL certificate verification for external requests"
    )

    ssl_cert_path: Optional[str] = Field(
        default=None,
        description="Path to custom CA bundle for SSL verification"
    )

    # JWT 设置
    jwt_verify_signature: bool = Field(
        default=True,
        description="Enable JWT signature verification"
    )

    jwt_verify_expiration: bool = Field(
        default=True,
        description="Enable JWT expiration verification"
    )

    # 请求超时设置
    default_request_timeout: int = Field(
        default=30,
        description="Default timeout for HTTP requests in seconds"
    )

    database_connection_timeout: int = Field(
        default=10,
        description="Default timeout for database connections in seconds"
    )

    # 密码安全
    min_password_length: int = Field(
        default=8,
        description="Minimum password length"
    )

    require_password_uppercase: bool = Field(
        default=True,
        description="Require at least one uppercase letter in passwords"
    )

    require_password_lowercase: bool = Field(
        default=True,
        description="Require at least one lowercase letter in passwords"
    )

    require_password_digit: bool = Field(
        default=True,
        description="Require at least one digit in passwords"
    )

    require_password_special: bool = Field(
        default=True,
        description="Require at least one special character in passwords"
    )

    # 限流设置
    enable_rate_limiting: bool = Field(
        default=True,
        description="Enable rate limiting for API endpoints"
    )

    rate_limit_per_minute: int = Field(
        default=60,
        description="Maximum requests per minute per user"
    )

    # SQL 注入防护
    use_parameterized_queries: bool = Field(
        default=True,
        description="Always use parameterized queries to prevent SQL injection"
    )

    # XSS 防护
    sanitize_html_input: bool = Field(
        default=True,
        description="Sanitize HTML input to prevent XSS attacks"
    )

    # CSRF 防护
    enable_csrf_protection: bool = Field(
        default=True,
        description="Enable CSRF protection for state-changing requests"
    )

    # 日志与监控
    log_security_events: bool = Field(
        default=True,
        description="Log security-related events"
    )

    log_failed_auth_attempts: bool = Field(
        default=True,
        description="Log failed authentication attempts"
    )

    max_failed_auth_attempts: int = Field(
        default=5,
        description="Maximum failed authentication attempts before account lockout"
    )

    account_lockout_duration_minutes: int = Field(
        default=15,
        description="Duration of account lockout in minutes"
    )


# 默认安全配置
DEFAULT_SECURITY_CONFIG = SecurityConfig()


def get_security_config() -> SecurityConfig:
    """
    是什么：get_security_config 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    return DEFAULT_SECURITY_CONFIG


def validate_password_strength(password: str, config: SecurityConfig = DEFAULT_SECURITY_CONFIG) -> tuple[bool, str]:
    """
    是什么：validate_password_strength 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查后端基础能力里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if len(password) < config.min_password_length:
        return False, f"Password must be at least {config.min_password_length} characters long"

    if config.require_password_uppercase and not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if config.require_password_lowercase and not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if config.require_password_digit and not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    if config.require_password_special:
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in password):
            return False, "Password must contain at least one special character"

    return True, ""
