from enum import Enum


class SemanticRecordScopeEnum(str, Enum):
    TENANT = "TENANT"
    PLATFORM = "PLATFORM"


def normalize_semantic_scope(value) -> SemanticRecordScopeEnum:
    """
    是什么：normalize_semantic_scope 是 backend/apps/system/schemas/semantic_scope.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化系统管理相关数据，生成后续流程可使用的结构。
    """
    if isinstance(value, SemanticRecordScopeEnum):
        return value
    if value in (None, ""):
        return SemanticRecordScopeEnum.TENANT
    try:
        return SemanticRecordScopeEnum(str(value))
    except ValueError:
        return SemanticRecordScopeEnum.TENANT
