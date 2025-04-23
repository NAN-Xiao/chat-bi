
from pydantic import BaseModel


class LocalLoginSchema(BaseModel):
    account: str
    password: str