
from pydantic import BaseModel
from enum import Enum

class LocalLoginSchema(BaseModel):
    account: str
    password: str
    
class CacheNamespace(Enum):
    AUTH_INFO = "sqlbot:auth"
    def __str__(self):
        return self.value
class CacheName(Enum):
    USER_INFO = "user:info"

    def __str__(self):
        return self.value