"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""

from typing import Optional
from pydantic import BaseModel
from enum import Enum

class LocalLoginSchema(BaseModel):
    """
    类说明：LocalLoginSchema 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    account: str
    password: str
    
class CacheNamespace(Enum):
    """
    类说明：CacheNamespace 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    AUTH_INFO = "shuzhi:auth"
    EMBEDDED_INFO = "shuzhi:embedded"
    def __str__(self):
        """
        是什么：CacheNamespace.__str__ 是 CacheNamespace 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：把对象变成一段好读的文字，方便打印或看日志。
        """
        return self.value
class CacheName(Enum):
    """
    类说明：CacheName 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    USER_INFO = "user:info"
    ASSISTANT_INFO = "assistant:info"
    ASSISTANT_DS = "assistant:ds"
    ASK_INFO = "ask:info"
    DS_ID_LIST = "ds:id:list"
    def __str__(self):
        """
        是什么：CacheName.__str__ 是 CacheName 里的一个步骤，帮它完成系统管理相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：把对象变成一段好读的文字，方便打印或看日志。
        """
        return self.value
    
