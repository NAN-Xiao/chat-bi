"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from typing import Generic, TypeVar

from fastapi import HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from pydantic import BaseModel, Field
from sqlmodel import SQLModel
from starlette.status import HTTP_401_UNAUTHORIZED

from apps.swagger.i18n import PLACEHOLDER_PREFIX
from common.core.config import settings


class TokenPayload(BaseModel):
    """
    类说明：TokenPayload 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    account: str | None = None
    id: int | None = None
    tenant_id: int | None = None
    auth_origin: int | None = None

class Token(SQLModel):
    """
    类说明：Token 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    access_token: str
    token_type: str = "bearer"
    platform_info: dict | None = None

class XOAuth2PasswordBearer(OAuth2PasswordBearer):
    """
    类说明：XOAuth2PasswordBearer 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    async def __call__(self, request: Request) -> str | None:
        """
        是什么：XOAuth2PasswordBearer.__call__ 是 XOAuth2PasswordBearer 里的一个步骤，帮它完成后端基础能力相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：让这个对象能配合 Python 的特殊用法工作。
        """
        authorization = request.headers.get(settings.TOKEN_KEY)
        if request.headers.get(settings.ASSISTANT_TOKEN_KEY):
            authorization = request.headers.get(settings.ASSISTANT_TOKEN_KEY)
        scheme, param = get_authorization_scheme_param(authorization)

        if not authorization or scheme.lower() not in  ["bearer", "assistant"]:
            if self.auto_error:
                raise HTTPException(
                    status_code=HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        return param




T = TypeVar('T')

class PaginationParams(BaseModel):
    """
    类说明：PaginationParams 把后端基础能力相关的数据和行为放在一起，便于其他代码直接复用。
    """
    page: int = 1
    size: int = 20
    order_by: str | None = None
    desc: bool = False

class PaginatedResponse(BaseModel, Generic[T]):
    """
    类说明：PaginatedResponse 用来描述后端基础能力的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    items: list[T] = Field(description=f"{PLACEHOLDER_PREFIX}grid_items")
    total: int = Field(description=f"{PLACEHOLDER_PREFIX}grid_total")
    page: int = Field(description=f"{PLACEHOLDER_PREFIX}page_num")
    size: int = Field(description=f"{PLACEHOLDER_PREFIX}page_size")
    total_pages: int = Field(description=f"{PLACEHOLDER_PREFIX}grid_total_pages")


class BaseCreatorDTO(BaseModel):
    """
    类说明：BaseCreatorDTO 用来描述后端基础能力的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: int = Field(description="ID")
    class Config:
        """
        类说明：Config 放后端基础能力的配置项，让后续流程能按同一套规则运行。
        """
        json_encoders = {
            int: lambda v: str(v) if isinstance(v, int) and v > (2**53 - 1) else v
        }
