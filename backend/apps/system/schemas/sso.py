from typing import Literal

from pydantic import BaseModel, Field


class FeishuSsoConfigEditor(BaseModel):
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
    enabled: bool = False
    authorize_url: str | None = None


class FeishuCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=4096)
