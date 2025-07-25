from typing import Optional
from pydantic import BaseModel

from common.core.schemas import BaseCreatorDTO

class model_status(BaseModel):
    status: bool
    ids: list[int]
    

class UserLanguage(BaseModel):
    language: str
    

class BaseUser(BaseModel):
    account: str
    oid: int

class BaseUserDTO(BaseUser, BaseCreatorDTO):
    language: str
    password: str
    def to_dict(self):
        return {
            "id": self.id,
            "account": self.account,
            "oid": self.oid
        }

class UserCreator(BaseUser):
    name: str
    email: str
    status: int = 1
    oid_list: Optional[list[int]] = None 

class UserEditor(UserCreator, BaseCreatorDTO):
   pass

class UserGrid(UserEditor):
    create_time: int
    language: str = "zh-CN"
    #space_name: Optional[str] = None
    origin: str = ''
    
    
class PwdEditor(BaseModel):
    pwd: str
    new_pwd: str
    
class UserWsBase(BaseModel):
    uid_list: list[int]
    oid: Optional[int] = None
class UserWsDTO(UserWsBase):
    weight: Optional[int] = 0

class UserWsEditor(BaseModel):
    uid: int
    oid: int    
    weight: int = 0

class UserInfoDTO(UserEditor):
    language: str = "zh-CN"
    weight: int = 0
    isAdmin: bool = False
    

class AssistantBase(BaseModel):
    name: str
    domain: str
    type: int = 0
    configuration: Optional[str] = None
    description: Optional[str] = None
class AssistantDTO(AssistantBase, BaseCreatorDTO):
    pass

class AssistantHeader(AssistantDTO):
    unique: Optional[str] = None
    certificate: Optional[str] = None
    online: bool = False
    

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
        
class WorkspaceUser(UserEditor):
    weight: int
    create_time: int
    
class UserWs(BaseCreatorDTO):
    name: str
    
class UserWsOption(UserWs):
    account: str
    
    
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
    
        
class AssistantOutDsSchema(AssistantOutDsBase):
    host: Optional[str] = None
    port: Optional[int] = None
    dataBase: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    db_schema: Optional[str] = None
    extraParams: Optional[str] = None
    tables: Optional[list[AssistantTableSchema]] = None
    