import re
from typing import Literal, Optional,List

from pydantic import BaseModel, Field, create_model, field_validator

from apps.swagger.i18n import PLACEHOLDER_PREFIX
from common.core.schemas import BaseCreatorDTO

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9]+([._-][a-zA-Z0-9]+)*@"
    r"([a-zA-Z0-9]+(-[a-zA-Z0-9]+)*\.)+"
    r"[a-zA-Z]{2,}$"
)
PWD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)"
    r"(?=.*[~!@#$%^&*()_+\-={}|:\"<>?`\[\];',./])"
    r"[A-Za-z\d~!@#$%^&*()_+\-={}|:\"<>?`\[\];',./]{8,20}$"
)


class UserStatus(BaseCreatorDTO):
    status: int = Field(default=1, description=f"{PLACEHOLDER_PREFIX}status")


class UserLanguage(BaseModel):
    language: str = Field(description=f"{PLACEHOLDER_PREFIX}language")


class BaseUser(BaseModel):
    account: str = Field(min_length=1, max_length=100, description="用户账号")


class BaseUserDTO(BaseUser, BaseCreatorDTO):
    language: str = Field(pattern=r"^(zh-CN|zh-TW|en|ko-KR)$", default="zh-CN", description="用户语言")
    password: str
    status: int = 1
    origin: int = 0
    name: str
    system_role: str = "viewer"
    tenant_id: Optional[int] = None
    tenant_code: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_role: Optional[str] = None

    def to_dict(self):
        data = {
            "id": self.id,
            "account": self.account,
        }
        if self.tenant_id is not None:
            data["tenant_id"] = self.tenant_id
        return data

    @field_validator("language")
    def validate_language(cls, lang: str) -> str:
        if not re.fullmatch(r"^(zh-CN|zh-TW|en|ko-KR)$", lang):
            raise ValueError("Language must be 'zh-CN', 'zh-TW', 'en', or 'ko-KR'")
        return lang


class UserCreator(BaseUser):
    name: str = Field(min_length=1, max_length=100, description=f"{PLACEHOLDER_PREFIX}user_name")
    email: str = Field(min_length=1, max_length=100, description=f"{PLACEHOLDER_PREFIX}user_email")
    status: int = Field(default=1, description=f"{PLACEHOLDER_PREFIX}status")
    origin: Optional[int] = Field(default=0, description=f"{PLACEHOLDER_PREFIX}origin")
    system_role: Literal["system_admin", "collab_admin", "viewer"] = "viewer"
    tenant_role: Literal["owner", "admin", "member"] = "member"
    tenant_id: Optional[int] = None
    project_ids: Optional[list[int]] = Field(default=None, description=f"{PLACEHOLDER_PREFIX}ds_id")
    project_role_map: Optional[dict[int, str]] = Field(default=None, description=f"{PLACEHOLDER_PREFIX}ds_role")
    system_variables: Optional[List] = Field(default=[])

    """ @field_validator("email")
    def validate_email(cls, lang: str) -> str:
        if not re.fullmatch(EMAIL_REGEX, lang):
            raise ValueError("Email format is invalid!")
        return lang """


class UserEditor(UserCreator, BaseCreatorDTO):
    pass


class UserGrid(UserEditor):
    create_time: int = Field(description=f"{PLACEHOLDER_PREFIX}create_time")
    language: str = Field(default="zh-CN" ,description=f"{PLACEHOLDER_PREFIX}language") 
    # space_name: Optional[str] = None
    # origin: str = ''


globals()["UserWsEditor"] = create_model(
    "UserWsEditor",
    uid=(int, ...),
    **{"o" + "id": (int, ...), "weight": (int, 0)},
)


class PwdEditor(BaseModel):
    pwd: str = Field(description=f"{PLACEHOLDER_PREFIX}origin_pwd")
    new_pwd: str = Field(description=f"{PLACEHOLDER_PREFIX}new_pwd")


class UserInfoDTO(UserEditor):
    language: str = "zh-CN"
    weight: int = 0
    isAdmin: bool = False
    tenant_ids: list[int] = Field(default_factory=list)


class AssistantBase(BaseModel):
    name: str = Field(description=f"{PLACEHOLDER_PREFIX}model_name")
    domain: str = Field(description=f"{PLACEHOLDER_PREFIX}assistant_domain")
    type: int = Field(default=0, description=f"{PLACEHOLDER_PREFIX}assistant_type")  # 0普通小助手 1高级 4页面嵌入
    configuration: Optional[str] = Field(default=None, description=f"{PLACEHOLDER_PREFIX}assistant_configuration")
    description: Optional[str] = Field(default=None, description=f"{PLACEHOLDER_PREFIX}assistant_description")
    enable_custom_model: Optional[bool] = Field(default=False, description=f"{PLACEHOLDER_PREFIX}enable_custom_model")
    custom_model: Optional[str] = Field(description=f"{PLACEHOLDER_PREFIX}custom_model")


class AssistantDTO(AssistantBase, BaseCreatorDTO):
    pass


class AssistantPublicInfo(AssistantDTO):
    app_id: Optional[str] = None


class AssistantHeader(AssistantDTO):
    unique: Optional[str] = None
    certificate: Optional[str] = None
    online: bool = False
    request_origin: Optional[str] = None
    tenant_id: int = 1


class AssistantValidator(BaseModel):
    valid: bool = False
    id_match: bool = False
    domain_match: bool = False
    token: Optional[str] = None

    def __init__(
            self,
            valid: bool = False,
            id_match: bool = False,
            domain_match: bool = False,
            token: Optional[str] = None,
            **kwargs
    ):
        super().__init__(
            valid=valid,
            id_match=id_match,
            domain_match=domain_match,
            token=token,
            **kwargs
        )


class AssistantFieldSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    comment: Optional[str] = None


class AssistantTableSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    comment: Optional[str] = None
    rule: Optional[str] = None
    sql: Optional[str] = None
    fields: Optional[list[AssistantFieldSchema]] = None


class AssistantOutDsBase(BaseModel):
    id: Optional[int] = None
    name: str
    type: Optional[str] = None
    type_name: Optional[str] = None
    comment: Optional[str] = None
    description: Optional[str] = None
    configuration: Optional[str] = None


class AssistantOutDsSchema(AssistantOutDsBase):
    host: Optional[str] = None
    port: Optional[int] = None
    dataBase: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    db_schema: Optional[str] = None
    extraParams: Optional[str] = None
    mode: Optional[str] = None
    tables: Optional[list[AssistantTableSchema]] = None


class ApikeyStatus(BaseModel):
    id: int = Field(description=f"{PLACEHOLDER_PREFIX}id")
    status: bool = Field(description=f"{PLACEHOLDER_PREFIX}status")

class ApikeyGridItem(BaseCreatorDTO):
    access_key: str = Field(description=f"Access Key")
    secret_key: str = Field(description=f"Secret Key")
    tenant_id: int = Field(default=1, description="Tenant ID")
    status: bool = Field(description=f"{PLACEHOLDER_PREFIX}status")
    create_time: int = Field(description=f"{PLACEHOLDER_PREFIX}create_time")
