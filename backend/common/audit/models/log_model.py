from sqlmodel import Field, SQLModel,BigInteger
from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel

_operation_module_values = {
    "WORK" + "SPACE": "project",
    "CHAT": "chat",
    "DATASOURCE": "datasource",
    "DASHBOARD": "dashboard",
    "MEMBER": "member",
    "PERMISSION": "permission",
    "RULES": "rules",
    "PROMPT_WORDS": "prompt_words",
    "USER": "user",
    "AI_MODEL": "ai_model",
    "APPLICATION": "application",
    "THEME": "theme",
    "PARAMS_SETTING": "params_setting",
    "API_KEY": "api_key",
    "TENANT": "tenant",
    "TENANT_APPLICATION": "tenant_application",
    "LOG_SETTING": "log_setting",
    "SETTING": "setting",
    "SYSTEM_MANAGEMENT": "system_management",
    "OPT_LOG": "opt_log",
}
OperationModules = Enum("OperationModules", _operation_module_values, type=str)

class OperationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"

class OperationType(str, Enum):
    CREATE = "create"
    DELETE = "delete"
    UPDATE = "update"
    RESET_PWD = "reset_pwd"
    UPDATE_PWD = "update_pwd"
    UPDATE_STATUS = "update_status"
    UPDATE_TABLE_RELATION = "update_table_relation"
    EDIT = "edit"
    LOGIN = "login"
    VIEW = "view"
    EXPORT = "export"
    IMPORT = "import"
    ADD = "add"
    CREATE_OR_UPDATE = "create_or_update"
    ANALYSIS = "analysis"
    PREDICTION = "prediction"

class SystemLogsResource(SQLModel, table=True):
    __tablename__ = "sys_logs_resource"
    id: Optional[int] = Field(default=None, primary_key=True)
    log_id: Optional[int] = Field(default=None,sa_type=BigInteger())
    resource_id: Optional[str] = Field(default=None)
    resource_name: Optional[str] = Field(default=None)
    module: Optional[str] = Field(default=None)


class SystemLog(SQLModel, table=True):
    __tablename__ = "sys_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=1, sa_type=BigInteger())
    operation_type: str = Field(default=None)
    operation_detail: str = Field(default=None)
    user_id: Optional[int] = Field(default=None, sa_type=BigInteger())
    operation_status: str = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
    user_agent: Optional[str] = Field(default=None)
    execution_time: int = Field(default=0, description="执行时间(毫秒)", sa_type=BigInteger())
    error_message: Optional[str] = Field(default=None)
    create_time: datetime = Field(default_factory=datetime.now)
    module: Optional[str] = Field(default=None)
    resource_id: Optional[str] = Field(default=None)
    request_method: Optional[str] = Field(default=None)
    request_path: Optional[str] = Field(default=None)
    remark: Optional[str] = Field(default=None)
    user_name: Optional[str] = Field(default=None)
    resource_name: Optional[str] = Field(default=None)


class SystemLogInfo(BaseModel):
    id: str = Field(default=None)
    operation_type_name: str = Field(default=None)
    operation_detail_info: str = Field(default=None)
    user_name: str = Field(default=None)
    resource_name: str = Field(default=None)
    operation_status:  str = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
    create_time: datetime = Field(default_factory=datetime.now)
    remark:  str = Field(default=None)

class SystemLogInfoResult(BaseModel):
    id: str = Field(default=None)
    operation_type_name: str = Field(default=None)
    operation_detail_info: str = Field(default=None)
    user_name: str = Field(default=None)
    resource_name: str = Field(default=None)
    operation_status:  str = Field(default=None)
    operation_status_name:  str = Field(default=None)
    ip_address: Optional[str] = Field(default=None)
    create_time: datetime = Field(default_factory=datetime.now)
    error_message:  str = Field(default=None)
    remark:  str = Field(default=None)
