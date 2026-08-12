# Technical Design

## Data Flow

`/system/tenant/list` -> 创建弹窗工作空间选项 -> `POST /knowledge-base/create { tenant_id }` -> 后端工作空间与权限校验 -> `knowledge_base.tenant_id` -> 列表/详情/编辑权限校验。

## Frontend

- 复用 `tenantApi.list()` 和 `TenantInfo`，不创建重复的工作空间 API。
- 创建表单增加可空 `tenant_id`。打开弹窗时加载工作空间：平台管理员不预选；工作空间管理员固定使用当前工作空间。
- 仅在 `ADMIN_PUBLIC` 范围显示工作空间表单项；提交前做明确必选校验。
- 列表加载失败与无可选工作空间分别显示可操作状态，不做默认兜底。

## Backend Contract

- `CreateKnowledgeBaseRequest` 增加可空 `tenant_id`。
- `PLATFORM_PUBLIC` 忽略/拒绝非空工作空间归属并继续写入平台默认租户；前端不提交该字段。
- `ADMIN_PUBLIC` 要求明确可解析的目标工作空间：全局平台管理员可指定有效工作空间；工作空间管理员仅可指定当前工作空间。
- 后端以数据库工作空间状态和权限服务为准，不能信任前端选项。

## Permission Boundary

- 权限服务对全局平台管理员开放工作空间知识管理与读取，以支持管理端完整生命周期。
- 非平台管理员仍通过 `current_tenant_id` 严格限制到当前工作空间。
- 列表可见租户范围按角色计算：全局平台管理员可列出所有有效工作空间知识和平台公共知识；其他用户仅当前工作空间加平台公共知识。
- 详情、版本、发布和归档继续复用统一记录解析与权限服务，避免只放宽创建接口。

## Compatibility And Rollback

- 平台公共知识请求保持兼容。
- 工作空间知识不增加静默兼容兜底；缺少 `tenant_id` 直接返回明确校验错误。
- 回滚时可整体撤销请求字段、选择器和权限扩展，不涉及数据库迁移。
