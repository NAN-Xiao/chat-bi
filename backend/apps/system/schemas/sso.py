"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from typing import Literal

from pydantic import BaseModel, Field


class FeishuSsoConfigEditor(BaseModel):
    """
    类说明：FeishuSsoConfigEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    enable: bool = False
    app_id: str = Field(default="", max_length=255)
    app_secret: str | None = Field(default=None, max_length=1024)
    redirect_uri: str = Field(default="", max_length=1024)
    authorize_url: str | None = Field(default=None, max_length=1024)
    token_url: str | None = Field(default=None, max_length=1024)
    tenant_access_token_url: str | None = Field(default=None, max_length=1024)
    user_info_url: str | None = Field(default=None, max_length=1024)
    scope: str | None = Field(default=None, max_length=512)
    token_mode: Literal["oauth_v2", "authen_v1"] = "oauth_v2"


class FeishuSsoConfigDTO(BaseModel):
    """
    类说明：FeishuSsoConfigDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    enable: bool = False
    valid: bool = False
    app_id: str = ""
    redirect_uri: str = ""
    authorize_url: str = ""
    token_url: str = ""
    tenant_access_token_url: str = ""
    user_info_url: str = ""
    scope: str | None = None
    token_mode: Literal["oauth_v2", "authen_v1"] = "oauth_v2"
    secret_configured: bool = False


class FeishuLoginStatusDTO(BaseModel):
    """
    类说明：FeishuLoginStatusDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    enabled: bool = False
    authorize_url: str | None = None


class FeishuCallbackRequest(BaseModel):
    """
    类说明：FeishuCallbackRequest 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=4096)
