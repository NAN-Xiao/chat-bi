from pydantic import BaseModel


class TenantUsageDailyDTO(BaseModel):
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
    tenant_id: int
    user_id: int
    user_account: str | None = None
    user_name: str | None = None
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_tokens: int = 0
    last_used_time: int = 0
