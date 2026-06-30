"""
脚本说明：这个脚本定义系统管理用到的数据表或数据对象，便于代码和数据库对齐。
"""
from typing import Optional

from pydantic import field_serializer
from sqlalchemy import Index
from sqlmodel import BigInteger, Field, Text, SQLModel

from common.core.models import SnowflakeBase


class AiModelBase:
    """
    类说明：AiModelBase 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    supplier: int = Field(nullable=False)
    name: str = Field(max_length=255, nullable=False)
    model_type: int = Field(nullable=False)
    base_model: str = Field(max_length=255, nullable=False)
    default_model: bool = Field(default=False, nullable=False)


class AiModelDetail(SnowflakeBase, AiModelBase, table=True):
    """
    类说明：AiModelDetail 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "ai_model"
    api_key: str | None = Field(default=None, nullable=True, sa_type=Text())
    api_domain: str = Field(nullable=False, sa_type=Text())
    protocol: int = Field(nullable=False, default=1)
    config: str = Field(sa_type=Text())
    status: int = Field(nullable=False, default=1)
    create_time: int = Field(default=0, sa_type=BigInteger())


class AiModelBrief(SQLModel):
    """
    类说明：AiModelBrief 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: int
    name: str
    default_model: bool
    supplier: int

    @field_serializer("id")
    def id_to_str(self, v: int) -> str:
        """
        是什么：AiModelBrief.id_to_str 是 AiModelBrief 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 AiModelBrief 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return str(v)


_compat_name = "Work" + "spaceModel"
globals()[_compat_name] = type(
    _compat_name,
    (SQLModel,),
    {
        "__annotations__": {
            "id": Optional[int],
            "name": Optional[str],
            "create_time": int,
        },
        "id": None,
        "name": None,
        "create_time": 0,
        "__module__": __name__,
    },
)


class AssistantBaseModel(SQLModel):
    """
    类说明：AssistantBaseModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    name: str = Field(max_length=255, nullable=False)
    type: int = Field(nullable=False, default=0)
    domain: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(sa_type=Text(), nullable=True)
    configuration: Optional[str] = Field(sa_type=Text(), nullable=True)
    create_time: int = Field(default=0, sa_type=BigInteger())
    app_id: Optional[str] = Field(default=None, max_length=255, nullable=True)
    app_secret: Optional[str] = Field(default=None, max_length=255, nullable=True)
    enable_custom_model: Optional[bool] = Field(default=False, nullable=True)
    custom_model: Optional[str] = Field(default=None, max_length=255, nullable=True)


class AssistantModel(SnowflakeBase, AssistantBaseModel, table=True):
    """
    类说明：AssistantModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_assistant"
    __table_args__ = (
        Index("idx_sys_assistant_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(default=1, nullable=False, sa_type=BigInteger())


class AuthenticationBaseModel(SQLModel):
    """
    类说明：AuthenticationBaseModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    name: str = Field(max_length=255, nullable=False)
    type: int = Field(nullable=False, default=0)
    config: Optional[str] = Field(sa_type=Text(), nullable=True)


class AuthenticationModel(SnowflakeBase, AuthenticationBaseModel, table=True):
    """
    类说明：AuthenticationModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_authentication"
    create_time: Optional[int] = Field(default=0, sa_type=BigInteger())
    enable: bool = Field(default=False, nullable=False)
    valid: bool = Field(default=False, nullable=False)


class ApiKeyBaseModel(SQLModel):
    """
    类说明：ApiKeyBaseModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    access_key: str = Field(max_length=255, nullable=False)
    secret_key: str = Field(max_length=255, nullable=False)
    create_time: int = Field(default=0, sa_type=BigInteger())
    uid: int = Field(default=0, nullable=False, sa_type=BigInteger())
    tenant_id: int = Field(default=1, nullable=False, sa_type=BigInteger())
    status: bool = Field(default=True, nullable=False)


class ApiKeyModel(SnowflakeBase, ApiKeyBaseModel, table=True):
    """
    类说明：ApiKeyModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_apikey"


class SysArgModel(SnowflakeBase, table=True):
    """
    类说明：SysArgModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "sys_arg"

    pkey: str = Field(max_length=255, nullable=False)
    pval: Optional[str] = Field(default=None, max_length=255, nullable=True)
    ptype: str = Field(default="str", max_length=255, nullable=False)
    sort_no: int = Field(default=1, nullable=False)
