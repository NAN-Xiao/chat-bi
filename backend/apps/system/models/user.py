"""
脚本说明：这个脚本定义系统管理用到的数据表或数据对象，便于代码和数据库对齐。
"""
from typing import List, Optional

from sqlalchemy import Column, BigInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field

from common.core.models import SnowflakeBase
from common.core.security import default_password_hash
from common.utils.time import get_timestamp


class BaseUserPO(SQLModel):
    """
    类说明：BaseUserPO 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    account: str = Field(max_length=255, unique=True)
    name: str = Field(max_length=255, unique=True)
    password: str = Field(default_factory=default_password_hash, max_length=255)
    email: str = Field(max_length=255)
    status: int = Field(default=0, nullable=False)
    origin: int = Field(nullable=False, default=0)
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    language: str = Field(max_length=255, default="zh-CN")
    system_role: str = Field(default="viewer", sa_column=Column(String(32), nullable=False, server_default="viewer"))
    #system_variables: List = Field(sa_column=Column(JSONB, nullable=True))
    system_variables: Optional[List] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True)
    )


class UserModel(SnowflakeBase, BaseUserPO, table=True):
    """
    类说明：UserModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_user"


class UserPlatformBase(SQLModel):
    """
    类说明：UserPlatformBase 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    uid: int = Field(nullable=False, sa_type=BigInteger())
    origin: int = Field(nullable=False, default=0)
    platform_uid: str = Field(max_length=255, nullable=False)


class UserPlatformModel(SnowflakeBase, UserPlatformBase, table=True):
    """
    类说明：UserPlatformModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_user_platform"


class TrialApplicationModel(SnowflakeBase, table=True):
    """
    类说明：TrialApplicationModel 记录未登录访客提交的试用账号申请。
    """
    __tablename__ = "sys_trial_application"

    account: str = Field(max_length=100, nullable=False, index=True)
    name: str = Field(max_length=100, nullable=False)
    email: str = Field(max_length=100, nullable=False, index=True)
    password_hash: str = Field(max_length=255, nullable=False)
    company: Optional[str] = Field(default=None, max_length=255)
    reason: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    status: str = Field(default="pending", max_length=32, nullable=False, index=True)
    reviewer_user_id: Optional[int] = Field(default=None, sa_type=BigInteger())
    review_comment: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    approved_user_id: Optional[int] = Field(default=None, sa_type=BigInteger())
    create_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    update_time: int = Field(default_factory=get_timestamp, sa_type=BigInteger(), nullable=False)
    review_time: Optional[int] = Field(default=None, sa_type=BigInteger())
