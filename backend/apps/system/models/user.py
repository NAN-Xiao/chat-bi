
from sqlmodel import SQLModel, Field

class sys_user(SQLModel, table=True):
    id: int = Field(primary_key=True, index=True)
    account: str = Field(max_length=255, unique=True)
    password: str = Field(max_length=255)
    oid: int = Field(default=1)
