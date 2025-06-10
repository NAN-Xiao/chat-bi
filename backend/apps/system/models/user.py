
from typing import Optional
from sqlmodel import SQLModel, Field

class sys_user(SQLModel):
    id: int = Field(primary_key=True, index=True)
    account: str = Field(max_length=255, unique=True)
    password: str = Field(max_length=255)
    oid: int = Field(default=1)

    def to_dict(self):
        return {
            "id": self.id,
            "account": self.account,
            "oid": self.oid
        }
        
class user_grid(sys_user, table=True):
    __tablename__ = "sys_user"
    name: str
    email: str
    status: int
    create_time: int
    language: str = Field(max_length=255, default="zh-CN")

