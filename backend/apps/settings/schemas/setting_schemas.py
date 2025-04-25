from pydantic import BaseModel

class term_schema(BaseModel):
    id: int
    term: str
    definition: str
    domain: str
    