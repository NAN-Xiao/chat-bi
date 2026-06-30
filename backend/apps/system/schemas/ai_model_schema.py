"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""

from typing import List
from pydantic import BaseModel, Field

from apps.swagger.i18n import PLACEHOLDER_PREFIX
from common.core.schemas import BaseCreatorDTO

class AiModelItem(BaseModel):
    """
    类说明：AiModelItem 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    name: str = Field(description=f"{PLACEHOLDER_PREFIX}model_name")
    model_type: int = Field(description=f"{PLACEHOLDER_PREFIX}model_type")
    base_model: str = Field(description=f"{PLACEHOLDER_PREFIX}base_model")
    supplier: int = Field(description=f"{PLACEHOLDER_PREFIX}supplier")
    protocol: int = Field(description=f"{PLACEHOLDER_PREFIX}protocol")
    default_model: bool = Field(default=False, description=f"{PLACEHOLDER_PREFIX}default_model")

class AiModelGridItem(AiModelItem, BaseCreatorDTO):
    """
    类说明：AiModelGridItem 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    usage_count: int = Field(default=0, description=f"{PLACEHOLDER_PREFIX}usage_count")
    total_tokens: int = Field(default=0, description=f"{PLACEHOLDER_PREFIX}total_tokens")

class AiModelConfigItem(BaseModel):
    """
    类说明：AiModelConfigItem 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    key: str = Field(description=f"{PLACEHOLDER_PREFIX}arg_name")
    val: object = Field(description=f"{PLACEHOLDER_PREFIX}arg_val")
    name: str = Field(description=f"{PLACEHOLDER_PREFIX}arg_show_name")


class AiModelRemoteListRequest(BaseModel):
    """
    类说明：AiModelRemoteListRequest 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    api_domain: str = Field(description=f"{PLACEHOLDER_PREFIX}api_domain")
    api_key: str = Field(description=f"{PLACEHOLDER_PREFIX}api_key")


class AiModelRemoteModel(BaseModel):
    """
    类说明：AiModelRemoteModel 表示系统管理里的一类数据，通常用来和数据库表或业务对象对应。
    """
    id: str = Field(description=f"{PLACEHOLDER_PREFIX}model_id")
    name: str = Field(description=f"{PLACEHOLDER_PREFIX}model_name")
    
class AiModelCreator(AiModelItem):
    """
    类说明：AiModelCreator 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    api_domain: str = Field(description=f"{PLACEHOLDER_PREFIX}api_domain")
    api_key: str = Field(description=f"{PLACEHOLDER_PREFIX}api_key")
    config_list: List[AiModelConfigItem] = Field(description=f"{PLACEHOLDER_PREFIX}config_list")
    
class AiModelEditor(AiModelCreator, BaseCreatorDTO):
    """
    类说明：AiModelEditor 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    pass
