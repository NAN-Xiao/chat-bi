from enum import Enum


class SemanticRecordScopeEnum(str, Enum):
    TENANT = "TENANT"
    PLATFORM = "PLATFORM"


def normalize_semantic_scope(value) -> SemanticRecordScopeEnum:
    if isinstance(value, SemanticRecordScopeEnum):
        return value
    if value in (None, ""):
        return SemanticRecordScopeEnum.TENANT
    try:
        return SemanticRecordScopeEnum(str(value))
    except ValueError:
        return SemanticRecordScopeEnum.TENANT
