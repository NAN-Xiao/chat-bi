# Technical Design

## Data Flow

页面顶部工作空间筛选器 -> 创建弹窗范围 -> `POST /knowledge-base/create { tenant_id }` -> 后端工作空间与权限校验 -> `knowledge_base.tenant_id` -> 列表/详情/编辑权限校验。

## Frontend

- 复用现有 `workspaceFilter`，不在创建弹窗维护第二份工作空间选择状态。
- 创建时直接以顶部筛选器的当前值作为 `tenant_id`，创建表单本身不保存工作空间字段。
- 删除创建弹窗内的工作空间表单项；仅在 `ADMIN_PUBLIC` 范围提交 `tenant_id`，缺少顶部选择时做明确校验。

## Backend Contract

- 后端创建契约保持不变，继续校验前端提交的 `tenant_id`。
- `PLATFORM_PUBLIC` 不提交工作空间 ID；`ADMIN_PUBLIC` 使用顶部筛选器传递的明确目标工作空间。

## Permission Boundary

- 权限服务与后端权限边界保持现状，不在本次 UI 去重中扩展跨工作空间能力。

## Compatibility And Rollback

- 平台公共知识请求保持兼容；工作空间知识缺少顶部工作空间时由前端明确阻止。
- 回滚时只需恢复创建弹窗工作空间表单项，不涉及数据库迁移。
