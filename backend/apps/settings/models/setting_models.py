from sqlmodel import Field, SQLModel


class term_model(SQLModel, table=True):
    __tablename__ = "terms"

    id: int = Field(primary_key=True, index=True)
    term: str = Field(max_length=255)
    definition: str = Field(max_length=255)
    domain: str = Field(max_length=255)
    create_time: int = Field(default=0)
   