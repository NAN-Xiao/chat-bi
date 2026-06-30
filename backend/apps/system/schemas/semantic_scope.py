"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from enum import Enum


class SemanticRecordScopeEnum(str, Enum):
    """
    类说明：SemanticRecordScopeEnum 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    TENANT = "TENANT"
    PLATFORM = "PLATFORM"


def normalize_semantic_scope(value) -> SemanticRecordScopeEnum:
    """
    是什么：normalize_semantic_scope 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(value, SemanticRecordScopeEnum):
        return value
    if value in (None, ""):
        return SemanticRecordScopeEnum.TENANT
    try:
        return SemanticRecordScopeEnum(str(value))
    except ValueError:
        return SemanticRecordScopeEnum.TENANT
