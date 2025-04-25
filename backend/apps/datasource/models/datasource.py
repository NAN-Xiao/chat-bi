from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, BigInteger, DateTime, Integer, Identity
from datetime import datetime

class core_datasource(SQLModel, table=True):
    id: int = Field(sa_column=Column(Integer, Identity(always=True), nullable=False, primary_key=True))
    name: str = Field(max_length=128, nullable=False)
    description: str = Field(max_length=512, nullable=True)
    type: str = Field(max_length=64)
    configuration: str = Field(sa_column=Column(Text))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))
    status: str = Field(max_length=64, nullable=True)