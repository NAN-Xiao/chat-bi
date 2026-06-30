"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from pydantic import BaseModel


class TenantUsageDailyDTO(BaseModel):
    """
    类说明：TenantUsageDailyDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_id: int
    usage_date: str
    metric: str
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_tokens: int = 0
    task_count: int = 0
    update_time: int = 0


class TenantUsageUserDTO(BaseModel):
    """
    类说明：TenantUsageUserDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_id: int
    user_id: int
    user_account: str | None = None
    user_name: str | None = None
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_tokens: int = 0
    last_used_time: int = 0


class TenantUsageModelDTO(BaseModel):
    """
    类说明：TenantUsageModelDTO 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    tenant_id: int
    model_id: int | None = None
    model_name: str
    model_code: str
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    last_used_time: int = 0
