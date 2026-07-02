"""
脚本说明：这个脚本定义系统管理用到的数据表或数据对象，便于代码和数据库对齐。
"""
import secrets

from sqlalchemy import BigInteger, Boolean, Column, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from common.core.models import SnowflakeBase
from common.utils.time import get_timestamp

TENANT_PUBLIC_ID_PREFIX = "WS"
TENANT_PUBLIC_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TENANT_PUBLIC_ID_DIGITS = "23456789"


def generate_tenant_public_id() -> str:
    """
    是什么：generate_tenant_public_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成系统管理的结果，比如答案、SQL、图表或建议。
    """
    body = "".join(secrets.choice(TENANT_PUBLIC_ID_ALPHABET) for _ in range(8))
    if not any(char.isdigit() for char in body):
        index = secrets.randbelow(len(body))
        body = f"{body[:index]}{secrets.choice(TENANT_PUBLIC_ID_DIGITS)}{body[index + 1:]}"
    return f"{TENANT_PUBLIC_ID_PREFIX}{body}"


class TenantModel(SnowflakeBase, table=True):
    """
    类说明：TenantModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_sys_tenant_public_id"),
        Index("idx_sys_tenant_status", "status"),
        Index("idx_sys_tenant_subscription_status", "subscription_status"),
    )

    public_id: str = Field(
        default_factory=generate_tenant_public_id,
        sa_column=Column(String(32), nullable=False),
    )
    name: str = Field(sa_column=Column(String(255), nullable=False))
    status: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    plan: str = Field(default="default", sa_column=Column(String(64), nullable=False, server_default="default"))
    subscription_status: str = Field(
        default="active",
        sa_column=Column(String(32), nullable=False, server_default="active"),
    )
    billing_mode: str = Field(
        default="manual",
        sa_column=Column(String(32), nullable=False, server_default="manual"),
    )
    trial_end_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    current_period_end_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    contract_no: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    billing_contact: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    billing_email: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    subscription_note: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantUserModel(SnowflakeBase, table=True):
    """
    类说明：TenantUserModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_user"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_sys_tenant_user_tenant_user"),
        Index("idx_sys_tenant_user_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_user_user_id", "user_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    role: str = Field(default="member", sa_column=Column(String(32), nullable=False, server_default="member"))
    member_remark: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    is_primary: bool = Field(default=False, sa_column=Column(Boolean(), nullable=False, server_default="false"))
    status: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantApplicationModel(SnowflakeBase, table=True):
    """
    类说明：TenantApplicationModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_application"
    __table_args__ = (
        Index("idx_sys_tenant_application_applicant", "applicant_user_id"),
        Index("idx_sys_tenant_application_inviter", "invited_by_user_id"),
        Index("idx_sys_tenant_application_status", "status"),
        Index("idx_sys_tenant_application_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_application_type_status", "application_type", "status"),
    )

    applicant_user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    invited_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    application_type: str = Field(default="create", sa_column=Column(String(32), nullable=False, server_default="create"))
    tenant_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    tenant_name: str = Field(sa_column=Column(String(255), nullable=False))
    plan: str = Field(default="default", sa_column=Column(String(64), nullable=False, server_default="default"))
    requested_role: str = Field(default="owner", sa_column=Column(String(32), nullable=False, server_default="owner"))
    reason: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    reviewer_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    review_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    review_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))


class TenantDomainModel(SnowflakeBase, table=True):
    """
    类说明：TenantDomainModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_domain"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_sys_tenant_domain_domain"),
        Index("idx_sys_tenant_domain_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_domain_status", "status"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    domain: str = Field(sa_column=Column(String(255), nullable=False))
    auto_join_role: str = Field(default="member", sa_column=Column(String(32), nullable=False, server_default="member"))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    requested_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    verified_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    verify_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))


class TenantSecurityPolicyModel(SnowflakeBase, table=True):
    """
    类说明：TenantSecurityPolicyModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_security_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_sys_tenant_security_policy_tenant_id"),
        Index("idx_sys_tenant_security_policy_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    sso_required: bool = Field(default=False, sa_column=Column(Boolean(), nullable=False, server_default="false"))
    session_timeout_minutes: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantTrackingConfigModel(SnowflakeBase, table=True):
    """
    类说明：TenantTrackingConfigModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_tracking_config"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_sys_tenant_tracking_config_tenant_id"),
        Index("idx_sys_tenant_tracking_config_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    enabled: bool = Field(default=True, sa_column=Column(Boolean(), nullable=False, server_default="true"))
    default_event_table: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    default_subject_field: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    default_event_name_field: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    default_event_time_field: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    field_role_mappings: list | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    event_name_mappings: list | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    sql_rules: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    notes: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    update_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantTrackingTableModel(SnowflakeBase, table=True):
    """
    类说明：TenantTrackingTableModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_tracking_table"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", name="uq_sys_tenant_tracking_table_name"),
        Index("idx_sys_tenant_tracking_table_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    table_name: str = Field(sa_column=Column(String(255), nullable=False))
    table_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    table_role: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    aliases: list | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    ai_notes: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    update_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantTrackingFieldModel(SnowflakeBase, table=True):
    """
    类说明：TenantTrackingFieldModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_tracking_field"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", "field_name", name="uq_sys_tenant_tracking_field_name"),
        Index("idx_sys_tenant_tracking_field_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_tracking_field_table", "tenant_id", "table_name"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    table_name: str = Field(sa_column=Column(String(255), nullable=False))
    field_name: str = Field(sa_column=Column(String(255), nullable=False))
    field_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    field_role: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    semantic_type: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    aliases: list | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    value_mappings: list | dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    expression: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    required: bool = Field(default=False, sa_column=Column(Boolean(), nullable=False, server_default="false"))
    example_values: list | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    ai_notes: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    update_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantSchemaTableModel(SnowflakeBase, table=True):
    """
    类说明：TenantSchemaTableModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_schema_table"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", name="uq_sys_tenant_schema_table_name"),
        Index("idx_sys_tenant_schema_table_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    table_name: str = Field(sa_column=Column(String(255), nullable=False))
    table_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    update_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantSchemaFieldModel(SnowflakeBase, table=True):
    """
    类说明：TenantSchemaFieldModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_schema_field"
    __table_args__ = (
        UniqueConstraint("tenant_id", "table_name", "field_name", name="uq_sys_tenant_schema_field_name"),
        Index("idx_sys_tenant_schema_field_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_schema_field_table", "tenant_id", "table_name"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    table_name: str = Field(sa_column=Column(String(255), nullable=False))
    field_name: str = Field(sa_column=Column(String(255), nullable=False))
    field_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    update_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)


class TenantSchemaChangeRequestModel(SnowflakeBase, table=True):
    """
    类说明：TenantSchemaChangeRequestModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_schema_change_request"
    __table_args__ = (
        Index("idx_sys_tenant_schema_change_request_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_schema_change_request_datasource", "datasource_id"),
        Index("idx_sys_tenant_schema_change_request_status", "status"),
        Index("idx_sys_tenant_schema_change_request_table", "tenant_id", "table_name"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    datasource_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    change_type: str = Field(sa_column=Column(String(32), nullable=False))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    table_name: str = Field(sa_column=Column(String(255), nullable=False))
    payload: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    requested_by_user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    executed_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    request_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    execution_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    execute_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))


class TenantDataRequestModel(SnowflakeBase, table=True):
    """
    类说明：TenantDataRequestModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_tenant_data_request"
    __table_args__ = (
        Index("idx_sys_tenant_data_request_tenant_id", "tenant_id"),
        Index("idx_sys_tenant_data_request_status", "status"),
        Index("idx_sys_tenant_data_request_type", "request_type"),
    )

    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    request_type: str = Field(sa_column=Column(String(32), nullable=False))
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False, server_default="pending"))
    requested_by_user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    reviewer_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    completed_by_user_id: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    reason: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    review_comment: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    export_manifest: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    review_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    complete_time: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
