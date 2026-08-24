# 技术设计

后端在 `backend/apps/system/crud/tenant.py` 增加一个仅用于“未指定空间”场景的默认上下文解析函数，复用 `list_user_tenant_memberships()` 已有的 `is_primary DESC` 排序。`resolve_current_tenant()` 只在 `requested_tenant_id is None` 时调用它；明确指定空间的分支保持严格权限校验。

登录接口和 TokenMiddleware 都复用 `resolve_current_tenant()`，因此登录、刷新和普通请求的上下文规则一致。前端不恢复旧的第一条盲选逻辑，继续由 `workspaceContext.completeBootstrap()` 同步后端返回的 tenant ID。

测试使用现有 tenant CRUD 测试夹具，验证主空间、唯一空间、无空间和显式越权四类边界。
