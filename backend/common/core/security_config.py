"""
安全配置模块。
集中管理星通数智应用的安全设置和最佳实践。
"""

from pydantic import BaseModel, Field
from typing import Optional


class SecurityConfig(BaseModel):
    """安全配置项。"""

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
    是什么：get_security_config 是 backend/common/core/security_config.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询核心配置和基础设施相关数据，整理后返回给调用方。
    """
    return DEFAULT_SECURITY_CONFIG


def validate_password_strength(password: str, config: SecurityConfig = DEFAULT_SECURITY_CONFIG) -> tuple[bool, str]:
    """
    是什么：validate_password_strength 是 backend/common/core/security_config.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验核心配置和基础设施相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
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
