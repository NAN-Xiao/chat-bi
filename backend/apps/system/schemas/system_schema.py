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

class UserEditor(UserCreator, BaseCreatorDTO):
   pass

class UserGrid(UserEditor):
    create_time: int
    language: str = "zh-CN"
    
class PwdEditor(BaseModel):
    pwd: str
    new_pwd: str