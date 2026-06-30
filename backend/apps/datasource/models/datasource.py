from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Column, Text, BigInteger, DateTime, Identity, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


class CoreDatasource(SQLModel, table=True):
    __tablename__ = "core_datasource"
    __table_args__ = (
        Index("idx_core_datasource_tenant_id", "tenant_id"),
    )

    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    tenant_id: int = Field(default=1, sa_column=Column(BigInteger(), nullable=False, server_default="1"))
    name: str = Field(max_length=128, nullable=False)
    description: str = Field(max_length=512, nullable=True)
    type: str = Field(max_length=64)
    type_name: str = Field(max_length=64, nullable=True)
    configuration: str = Field(sa_column=Column(Text))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))
    status: str = Field(max_length=64, nullable=True)
    num: str = Field(max_length=256, nullable=True)
    table_relation: List = Field(sa_column=Column(JSONB, nullable=True))
    embedding: str = Field(sa_column=Column(Text, nullable=True))
    recommended_config: int = Field(sa_column=Column(BigInteger()))


class CoreDatasourceUser(SQLModel, table=True):
    __tablename__ = "core_datasource_user"
    __table_args__ = (
        UniqueConstraint("ds_id", "user_id", name="uq_core_datasource_user_ds_user"),
        Index("idx_core_datasource_user_user_id", "user_id"),
        Index("idx_core_datasource_user_ds_id", "ds_id"),
    )

    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    user_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    role: str = Field(default="viewer", sa_column=Column(String(32), nullable=False, server_default="viewer"))
    create_by: int = Field(sa_column=Column(BigInteger(), nullable=True))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))


class CoreDatasourceTenantBinding(SQLModel, table=True):
    __tablename__ = "core_datasource_tenant_binding"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_core_datasource_tenant_binding_tenant"),
        UniqueConstraint("tenant_id", "datasource_id", name="uq_core_datasource_tenant_binding_pair"),
        Index("idx_core_datasource_tenant_binding_datasource", "datasource_id"),
    )

    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    tenant_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    datasource_id: int = Field(sa_column=Column(BigInteger(), nullable=False))
    create_by: int | None = Field(default=None, sa_column=Column(BigInteger(), nullable=True))
    create_time: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=False), nullable=True))


class CoreTable(SQLModel, table=True):
    __tablename__ = "core_table"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    table_name: str = Field(sa_column=Column(Text))
    table_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))
    embedding: str = Field(sa_column=Column(Text, nullable=True))


class DsRecommendedProblem(SQLModel, table=True):
    __tablename__ = "ds_recommended_problem"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    datasource_id: int = Field(sa_column=Column(BigInteger()))
    question: str = Field(sa_column=Column(Text))
    remark: str = Field(sa_column=Column(Text))
    sort: int = Field(sa_column=Column(BigInteger()))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))


class CoreField(SQLModel, table=True):
    __tablename__ = "core_field"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    table_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    field_name: str = Field(sa_column=Column(Text))
    field_type: str = Field(max_length=128, nullable=True)
    field_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))
    field_index: int = Field(sa_column=Column(BigInteger()))


# 数据源创建对象
class CreateDatasource(BaseModel):
    id: int = None
    name: str = ''
    description: str = ''
    type: str = ''
    configuration: str = ''
    create_time: Optional[datetime] = None
    create_by: int = 0
    status: str = ''
    num: str = ''
    tables: List[CoreTable] = []
    recommended_config: int = 1


class RecommendedProblemResponse:
    def __init__(self, datasource_id, recommended_config, questions):
        """
        是什么：RecommendedProblemResponse.__init__ 是 backend/apps/datasource/models/datasource.py 中的同步方法。
        谁调用：由创建 RecommendedProblemResponse 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.datasource_id = datasource_id
        self.recommended_config = recommended_config
        self.questions = questions

    datasource_id: int = None
    recommended_config: int = None
    questions: str = None


class RecommendedProblemBase(BaseModel):
    datasource_id: int = None
    recommended_config: int = None
    problemInfo: List[DsRecommendedProblem] = []


class RecommendedProblemBaseChat:
    def __init__(self, content):
        """
        是什么：RecommendedProblemBaseChat.__init__ 是 backend/apps/datasource/models/datasource.py 中的同步方法。
        谁调用：由创建 RecommendedProblemBaseChat 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.content = content

    content: List[str] = []


# 编辑本地保存的表和字段
class TableObj(BaseModel):
    table: CoreTable = None
    fields: List[CoreField] = []


# 数据源配置信息
class DatasourceConf(BaseModel):
    host: str = ''
    port: int = 0
    username: str = ''
    password: str = ''
    database: str = ''
    driver: str = ''
    extraJdbc: str = ''
    dbSchema: str = ''
    filename: str = ''
    sheets: List = ''
    mode: str = ''
    timeout: int = 30
    lowVersion: bool = False
    ssl: bool = False

    def to_dict(self):
        """
        是什么：DatasourceConf.to_dict 是 backend/apps/datasource/models/datasource.py 中的同步方法。
        谁调用：由持有 DatasourceConf 实例的业务代码、框架回调或测试代码调用。
        做了什么：围绕 to_dict 的语义处理数据源相关逻辑，并把结果返回或写入状态。
        """
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "database": self.database,
            "driver": self.driver,
            "extraJdbc": self.extraJdbc,
            "dbSchema": self.dbSchema,
            "filename": self.filename,
            "sheets": self.sheets,
            "mode": self.mode,
            "timeout": self.timeout,
            "lowVersion": self.lowVersion,
            "ssl": self.ssl
        }


class TableSchema:
    def __init__(self, attr1, attr2=None):
        """
        是什么：TableSchema.__init__ 是 backend/apps/datasource/models/datasource.py 中的同步方法。
        谁调用：由创建 TableSchema 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.tableName = attr1
        self.tableComment = attr2 if attr2 is None or isinstance(attr2, str) else attr2.decode("utf-8")

    tableName: str
    tableComment: str


class TableSchemaResponse(BaseModel):
    tableName: str = ''
    tableComment: str | None = ''


class ColumnSchema:
    def __init__(self, attr1, attr2, attr3):
        """
        是什么：ColumnSchema.__init__ 是 backend/apps/datasource/models/datasource.py 中的同步方法。
        谁调用：由创建 ColumnSchema 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.fieldName = attr1
        self.fieldType = attr2
        self.fieldComment = attr3 if attr3 is None or isinstance(attr3, str) else attr3.decode("utf-8")

    fieldName: str
    fieldType: str
    fieldComment: str


class ColumnSchemaResponse(BaseModel):
    fieldName: str | None = ''
    fieldType: str | None = ''
    fieldComment: str | None = ''


class TableAndFields:
    def __init__(self, schema, table, fields):
        """
        是什么：TableAndFields.__init__ 是 backend/apps/datasource/models/datasource.py 中的同步方法。
        谁调用：由创建 TableAndFields 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.schema = schema
        self.table = table
        self.fields = fields

    schema: str
    table: CoreTable
    fields: List[CoreField]


class FieldObj(BaseModel):
    fieldName: str | None


class PreviewResponse(BaseModel):
    fields: List | None = []
    data: List | None = []
    sql: str | None = ''


class FieldInfo(BaseModel):
    fieldName: object
    fieldType: str


class SheetFields(BaseModel):
    sheetName: str
    fields: List[FieldInfo]


class ImportRequest(BaseModel):
    filePath: str
    sheets: List[SheetFields]
