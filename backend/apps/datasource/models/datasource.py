"""
脚本说明：这个脚本定义数据源用到的数据表或数据对象，便于代码和数据库对齐。
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy import Column, Text, BigInteger, DateTime, Identity, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import SQLModel, Field


class CoreDatasource(SQLModel, table=True):
    """
    类说明：CoreDatasource 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：CoreDatasourceUser 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：CoreDatasourceTenantBinding 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：CoreTable 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "core_table"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    ds_id: int = Field(sa_column=Column(BigInteger()))
    checked: bool = Field(default=True)
    table_name: str = Field(sa_column=Column(Text))
    table_comment: str = Field(sa_column=Column(Text))
    custom_comment: str = Field(sa_column=Column(Text))
    embedding: str = Field(sa_column=Column(Text, nullable=True))


class DsRecommendedProblem(SQLModel, table=True):
    """
    类说明：DsRecommendedProblem 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "ds_recommended_problem"
    id: int = Field(sa_column=Column(BigInteger, Identity(always=True), nullable=False, primary_key=True))
    datasource_id: int = Field(sa_column=Column(BigInteger()))
    question: str = Field(sa_column=Column(Text))
    remark: str = Field(sa_column=Column(Text))
    sort: int = Field(sa_column=Column(BigInteger()))
    create_time: datetime = Field(sa_column=Column(DateTime(timezone=False), nullable=True))
    create_by: int = Field(sa_column=Column(BigInteger()))


class CoreField(SQLModel, table=True):
    """
    类说明：CoreField 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：CreateDatasource 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
    """
    类说明：RecommendedProblemResponse 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    def __init__(self, datasource_id, recommended_config, questions):
        """
        是什么：RecommendedProblemResponse.__init__ 是 RecommendedProblemResponse 里的一个步骤，帮它完成数据源相关的一件事。
        谁调用：创建 RecommendedProblemResponse 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.datasource_id = datasource_id
        self.recommended_config = recommended_config
        self.questions = questions

    datasource_id: int = None
    recommended_config: int = None
    questions: str = None


class RecommendedProblemBase(BaseModel):
    """
    类说明：RecommendedProblemBase 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    datasource_id: int = None
    recommended_config: int = None
    problemInfo: List[DsRecommendedProblem] = []


class RecommendedProblemBaseChat:
    """
    类说明：RecommendedProblemBaseChat 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    def __init__(self, content):
        """
        是什么：RecommendedProblemBaseChat.__init__ 是 RecommendedProblemBaseChat 里的一个步骤，帮它完成数据源相关的一件事。
        谁调用：创建 RecommendedProblemBaseChat 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.content = content

    content: List[str] = []


# 编辑本地保存的表和字段
class TableObj(BaseModel):
    """
    类说明：TableObj 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    table: CoreTable = None
    fields: List[CoreField] = []


# 数据源配置信息
class DatasourceConf(BaseModel):
    """
    类说明：DatasourceConf 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
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
        是什么：DatasourceConf.to_dict 是 DatasourceConf 里的一个步骤，帮它完成数据源相关的一件事。
        谁调用：拿到 DatasourceConf 对象的代码，需要完成这个动作时会调用它。
        做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    """
    类说明：TableSchema 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    def __init__(self, attr1, attr2=None):
        """
        是什么：TableSchema.__init__ 是 TableSchema 里的一个步骤，帮它完成数据源相关的一件事。
        谁调用：创建 TableSchema 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.tableName = attr1
        self.tableComment = attr2 if attr2 is None or isinstance(attr2, str) else attr2.decode("utf-8")

    tableName: str
    tableComment: str


class TableSchemaResponse(BaseModel):
    """
    类说明：TableSchemaResponse 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    tableName: str = ''
    tableComment: str | None = ''


class ColumnSchema:
    """
    类说明：ColumnSchema 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    def __init__(self, attr1, attr2, attr3):
        """
        是什么：ColumnSchema.__init__ 是 ColumnSchema 里的一个步骤，帮它完成数据源相关的一件事。
        谁调用：创建 ColumnSchema 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.fieldName = attr1
        self.fieldType = attr2
        self.fieldComment = attr3 if attr3 is None or isinstance(attr3, str) else attr3.decode("utf-8")

    fieldName: str
    fieldType: str
    fieldComment: str


class ColumnSchemaResponse(BaseModel):
    """
    类说明：ColumnSchemaResponse 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    fieldName: str | None = ''
    fieldType: str | None = ''
    fieldComment: str | None = ''


class TableAndFields:
    """
    类说明：TableAndFields 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    def __init__(self, schema, table, fields):
        """
        是什么：TableAndFields.__init__ 是 TableAndFields 里的一个步骤，帮它完成数据源相关的一件事。
        谁调用：创建 TableAndFields 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.schema = schema
        self.table = table
        self.fields = fields

    schema: str
    table: CoreTable
    fields: List[CoreField]


class FieldObj(BaseModel):
    """
    类说明：FieldObj 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    fieldName: str | None


class PreviewResponse(BaseModel):
    """
    类说明：PreviewResponse 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    fields: List | None = []
    data: List | None = []
    sql: str | None = ''


class FieldInfo(BaseModel):
    """
    类说明：FieldInfo 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    fieldName: object
    fieldType: str


class SheetFields(BaseModel):
    """
    类说明：SheetFields 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    sheetName: str
    fields: List[FieldInfo]


class ImportRequest(BaseModel):
    """
    类说明：ImportRequest 表示数据源里的一类数据，通常用来和数据库表或业务对象对应。
    """
    filePath: str
    sheets: List[SheetFields]
