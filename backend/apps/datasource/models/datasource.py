from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, BigInteger, DateTime, Integer, Identity
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


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


class CoreTable(SQLModel, table=True):
    __tablename__ = "core_table"
    id: int = Field(sa_column=Column(Integer, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    table_name: str = Field(sa_column=Column(Text))
    table_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))


class CoreField(SQLModel, table=True):
    __tablename__ = "core_field"
    id: int = Field(sa_column=Column(Integer, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    table_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    field_name: str = Field(sa_column=Column(Text))
    field_type: str = Field(max_length=128, nullable=True)
    field_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))


# datasource create obj
class CreateDatasource(BaseModel):
    id: int = None
    name: str = ''
    description: str = ''
    type: str = ''
    configuration: str = ''
    create_time: Optional[datetime] = None
    create_by: int = 0
    status: str = ''
    tables: List[CoreTable] = []


# edit local saved table and fields
class EditObj(BaseModel):
    table: CoreTable = None
    fields: List[CoreField] = []


# datasource config info
class DatasourceConf(BaseModel):
    host: str = ''
    port: int = 0
    username: str = ''
    password: str = ''
    database: str = ''
    driver: str = ''
    extraJdbc: str = ''


class TableSchema:
    def __init__(self, attr1, attr2):
        self.tableName = attr1
        self.tableComment = attr2

    tableName: str
    tableComment: str


class ColumnSchema:
    def __init__(self, attr1, attr2, attr3):
        self.fieldName = attr1
        self.fieldType = attr2
        self.fieldComment = attr3

    fieldName: str
    fieldType: str
    fieldComment: str
