
from typing import Optional
from pydantic import BaseModel
from enum import Enum

class LocalLoginSchema(BaseModel):
    account: str
    password: str
    
class CacheNamespace(Enum):
    AUTH_INFO = "shuzhi:auth"
    EMBEDDED_INFO = "shuzhi:embedded"
    def __str__(self):
        """
        是什么：CacheNamespace.__str__ 是 backend/apps/system/schemas/auth.py 中的同步方法。
        谁调用：由 Python 运行时、框架协议或相关内置操作按需调用。
        做了什么：生成对象的文本表示，便于日志、调试或展示。
        """
        return self.value
class CacheName(Enum):
    USER_INFO = "user:info"
    ASSISTANT_INFO = "assistant:info"
    ASSISTANT_DS = "assistant:ds"
    ASK_INFO = "ask:info"
    DS_ID_LIST = "ds:id:list"
    def __str__(self):
        """
        是什么：CacheName.__str__ 是 backend/apps/system/schemas/auth.py 中的同步方法。
        谁调用：由 Python 运行时、框架协议或相关内置操作按需调用。
        做了什么：生成对象的文本表示，便于日志、调试或展示。
        """
        return self.value
    
