"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
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
    """
    类说明：UserStatus 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    status: int = Field(default=1, description=f"{PLACEHOLDER_PREFIX}status")


class UserLanguage(BaseModel):
    """
    类说明：UserLanguage 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    language: str = Field(description=f"{PLACEHOLDER_PREFIX}language")


class BaseUser(BaseModel):
    """
    类说明：BaseUser 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    account: str = Field(min_length=1, max_length=100, description="用户账号")


class BaseUserDTO(BaseUser, BaseCreatorDTO):
    """
    类说明：BaseUserDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    language: str = Field(pattern=r"^(zh-CN|zh-TW|en|ko-KR)$", default="zh-CN", description="用户语言")
    password: str
    status: int = 1
    origin: int = 0
    name: str
    system_role: str = "viewer"
    tenant_id: Optional[int] = None
    tenant_public_id: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_role: Optional[str] = None
    global_role: Literal["platform_admin", "normal_user"] = "normal_user"
    has_workspace: bool = False
    workspace_status: Literal[
        "active",
        "workspace_required",
        "platform_admin",
        "platform_workspace_delegate",
    ] = "workspace_required"
    workspace_role: Optional[str] = None

    def to_dict(self):
        """
        是什么：BaseUserDTO.to_dict 是 BaseUserDTO 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：拿到 BaseUserDTO 对象的代码，需要完成这个动作时会调用它。
        做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        data = {
            "id": self.id,
            "account": self.account,
        }
        if self.tenant_id is not None:
            data["tenant_id"] = self.tenant_id
        return data

    @field_validator("language")
    def validate_language(cls, lang: str) -> str:
        """
        是什么：BaseUserDTO.validate_language 是 BaseUserDTO 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：创建或校验数据对象时，Pydantic 会自动调用它。
        做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
        """
        if not re.fullmatch(r"^(zh-CN|zh-TW|en|ko-KR)$", lang):
            raise ValueError("Language must be 'zh-CN', 'zh-TW', 'en', or 'ko-KR'")
        return lang


class UserCreator(BaseUser):
    """
    类说明：UserCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    name: str = Field(min_length=1, max_length=100, description=f"{PLACEHOLDER_PREFIX}user_name")
    email: str = Field(min_length=1, max_length=100, description=f"{PLACEHOLDER_PREFIX}user_email")
    status: int = Field(default=1, description=f"{PLACEHOLDER_PREFIX}status")
    origin: Optional[int] = Field(default=0, description=f"{PLACEHOLDER_PREFIX}origin")
    system_role: Literal["system_admin", "collab_admin", "viewer"] = "viewer"
    tenant_role: Optional[Literal["owner", "admin", "member"]] = "member"
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
    """
    类说明：UserEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_ids: Optional[list[int]] = Field(default_factory=list)
    tenant_names: Optional[list[str]] = Field(default_factory=list)
    tenant_roles: Optional[dict[str, str]] = Field(default_factory=dict)


class UserGrid(UserEditor):
    """
    类说明：UserGrid 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    """
    类说明：PwdEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    pwd: str = Field(description=f"{PLACEHOLDER_PREFIX}origin_pwd")
    new_pwd: str = Field(description=f"{PLACEHOLDER_PREFIX}new_pwd")


class UserInfoDTO(UserEditor):
    """
    类说明：UserInfoDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    language: str = "zh-CN"
    weight: int = 0
    isAdmin: bool = False
    tenant_public_id: Optional[str] = None
    tenant_name: Optional[str] = None
    tenant_ids: list[int] = Field(default_factory=list)
    global_role: Literal["platform_admin", "normal_user"] = "normal_user"
    has_workspace: bool = False
    workspace_status: Literal[
        "active",
        "workspace_required",
        "platform_admin",
        "platform_workspace_delegate",
    ] = "workspace_required"
    workspace_role: Optional[str] = None


class AssistantBase(BaseModel):
    """
    类说明：AssistantBase 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    name: str = Field(description=f"{PLACEHOLDER_PREFIX}model_name")
    domain: str = Field(description=f"{PLACEHOLDER_PREFIX}assistant_domain")
    type: int = Field(default=0, description=f"{PLACEHOLDER_PREFIX}assistant_type")  # 0普通小助手 1高级 4页面嵌入
    configuration: Optional[str] = Field(default=None, description=f"{PLACEHOLDER_PREFIX}assistant_configuration")
    description: Optional[str] = Field(default=None, description=f"{PLACEHOLDER_PREFIX}assistant_description")
    enable_custom_model: Optional[bool] = Field(default=False, description=f"{PLACEHOLDER_PREFIX}enable_custom_model")
    custom_model: Optional[str] = Field(description=f"{PLACEHOLDER_PREFIX}custom_model")


class AssistantDTO(AssistantBase, BaseCreatorDTO):
    """
    类说明：AssistantDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    pass


class AssistantPublicInfo(AssistantDTO):
    """
    类说明：AssistantPublicInfo 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    app_id: Optional[str] = None


class AssistantHeader(AssistantDTO):
    """
    类说明：AssistantHeader 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    unique: Optional[str] = None
    certificate: Optional[str] = None
    online: bool = False
    request_origin: Optional[str] = None
    tenant_id: Optional[int] = None


class AssistantValidator(BaseModel):
    """
    类说明：AssistantValidator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
        """
        是什么：AssistantValidator.__init__ 是 AssistantValidator 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：创建 AssistantValidator 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        super().__init__(
            valid=valid,
            id_match=id_match,
            domain_match=domain_match,
            token=token,
            **kwargs
        )


class AssistantFieldSchema(BaseModel):
    """
    类说明：AssistantFieldSchema 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    comment: Optional[str] = None


class AssistantTableSchema(BaseModel):
    """
    类说明：AssistantTableSchema 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    name: Optional[str] = None
    comment: Optional[str] = None
    rule: Optional[str] = None
    sql: Optional[str] = None
    fields: Optional[list[AssistantFieldSchema]] = None


class AssistantOutDsBase(BaseModel):
    """
    类说明：AssistantOutDsBase 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = None
    name: str
    type: Optional[str] = None
    type_name: Optional[str] = None
    comment: Optional[str] = None
    description: Optional[str] = None
    configuration: Optional[str] = None


class AssistantOutDsSchema(AssistantOutDsBase):
    """
    类说明：AssistantOutDsSchema 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
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
    """
    类说明：ApikeyStatus 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: int = Field(description=f"{PLACEHOLDER_PREFIX}id")
    status: bool = Field(description=f"{PLACEHOLDER_PREFIX}status")

class ApikeyGridItem(BaseCreatorDTO):
    """
    类说明：ApikeyGridItem 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    access_key: str = Field(description=f"Access Key")
    secret_key: str = Field(description=f"Secret Key")
    tenant_id: int = Field(default=1, description="Tenant ID")
    status: bool = Field(description=f"{PLACEHOLDER_PREFIX}status")
    create_time: int = Field(description=f"{PLACEHOLDER_PREFIX}create_time")
