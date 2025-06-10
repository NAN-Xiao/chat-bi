from pydantic import BaseModel

class model_status(BaseModel):
    status: bool
    ids: list[int]
    

class UserLanguage(BaseModel):
    language: str