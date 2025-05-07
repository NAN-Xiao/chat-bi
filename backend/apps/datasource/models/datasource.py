from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, BigInteger, DateTime, Integer, Identity
from datetime import datetime
from pydantic import BaseModel

class CoreDatasource(SQLModel, table=True):
    __tablename__ = "core_datasource"
    id: int = Field(sa_column=Column(Integer, Identity(always=True), nullable=False, primary_key=True))
    name: str = Field(max_length=128, nullable=False)
    description: str = Field(max_length=512, nullable=True)
    type: str = Field(max_length=64)
    configuration: str = Field(sa_column=Column(Text))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))
    status: str = Field(max_length=64, nullable=True)

class DatasourceConf(BaseModel):
    host: str = ''
    port: int = 0
    username: str = ''
    password: str = ''
    database: str = ''
    driver: str = ''