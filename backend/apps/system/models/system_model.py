from typing import Optional

from pydantic import field_serializer
from sqlalchemy import Index
from sqlmodel import BigInteger, Field, Text, SQLModel

from common.core.models import SnowflakeBase


class AiModelBase:
    supplier: int = Field(nullable=False)
    name: str = Field(max_length=255, nullable=False)
    model_type: int = Field(nullable=False)
    base_model: str = Field(max_length=255, nullable=False)
    default_model: bool = Field(default=False, nullable=False)


class AiModelDetail(SnowflakeBase, AiModelBase, table=True):
    __tablename__ = "ai_model"
    api_key: str | None = Field(default=None, nullable=True, sa_type=Text())
    api_domain: str = Field(nullable=False, sa_type=Text())
    protocol: int = Field(nullable=False, default=1)
    config: str = Field(sa_type=Text())
    status: int = Field(nullable=False, default=1)
    create_time: int = Field(default=0, sa_type=BigInteger())


class AiModelBrief(SQLModel):
    id: int
    name: str
    default_model: bool
    supplier: int

    @field_serializer("id")
    def id_to_str(self, v: int) -> str:
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
    __tablename__ = "sys_assistant"
    __table_args__ = (
        Index("idx_sys_assistant_tenant_id", "tenant_id"),
    )

    tenant_id: int = Field(default=1, nullable=False, sa_type=BigInteger())


class AuthenticationBaseModel(SQLModel):
    name: str = Field(max_length=255, nullable=False)
    type: int = Field(nullable=False, default=0)
    config: Optional[str] = Field(sa_type=Text(), nullable=True)


class AuthenticationModel(SnowflakeBase, AuthenticationBaseModel, table=True):
    __tablename__ = "sys_authentication"
    create_time: Optional[int] = Field(default=0, sa_type=BigInteger())
    enable: bool = Field(default=False, nullable=False)
    valid: bool = Field(default=False, nullable=False)


class ApiKeyBaseModel(SQLModel):
    access_key: str = Field(max_length=255, nullable=False)
    secret_key: str = Field(max_length=255, nullable=False)
    create_time: int = Field(default=0, sa_type=BigInteger())
    uid: int = Field(default=0, nullable=False, sa_type=BigInteger())
    tenant_id: int = Field(default=1, nullable=False, sa_type=BigInteger())
    status: bool = Field(default=True, nullable=False)


class ApiKeyModel(SnowflakeBase, ApiKeyBaseModel, table=True):
    __tablename__ = "sys_apikey"


class SysArgModel(SnowflakeBase, table=True):
    __tablename__ = "sys_arg"

    pkey: str = Field(max_length=255, nullable=False)
    pval: Optional[str] = Field(default=None, max_length=255, nullable=True)
    ptype: str = Field(default="str", max_length=255, nullable=False)
    sort_no: int = Field(default=1, nullable=False)
