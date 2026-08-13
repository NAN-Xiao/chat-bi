# 工作空间绑定 ROI 项目 ID - 实施计划

## Implementation Checklist

- [x] 新增 Alembic `157` 迁移及 `TenantModel.roi_project_id`。
- [x] 扩展租户 Schema 的 DTO、创建/编辑输入和统一文本校验。
- [x] 扩展租户 CRUD、创建/编辑路由、DTO 组装、当前工作空间响应和审计字段。
- [x] 扩展后端租户 ROI 测试：格式、必填、默认工作空间、创建/编辑回显、事务回滚。
- [x] 扩展前端 Tenant API 类型、表单状态、回显、提交和四语言文案。
- [x] 扩展前端 ROI 契约测试，覆盖位置、必填、禁用、提交和回显。
- [x] 更新测试内手工创建的 `sys_tenant` 表结构，保持事务集成测试可运行。

## Validation

- [x] 运行目标后端测试：两个目标文件共 `54 passed`。
- [x] 运行前端契约测试：`node src/views/system/tenant/Tenant.roi.test.mjs`。
- [x] 运行前端构建/type-check：`npx vue-tsc -b` 与 `npm run build`。
- [x] 检查 Alembic 单一 head，并验证 157 upgrade/downgrade SQL/迁移行为。
- [x] 在不占用其他工作区标准端口的前提下验证 API 8005、MCP 8006、Worker、前端 5179，并核对固定 LLM 超时配置。
- [x] 通过路由级和 SQLite 事务集成测试验证创建/编辑/读取、无效输入与整体回滚。
- [ ] 浏览器验证管理页创建与编辑抽屉、桌面和移动视口、无横向溢出，并保存/检查截图（当前浏览器会话不是平台系统管理员，`platformOnly` 路由按预期拒绝访问，无法完成受保护页面可视验收）。
- [x] 运行 `trellis-check`，将命令和结果记录到 `check.md`。

## Risky Files And Rollback Points

- `backend/apps/system/api/tenant.py` 已承载事务边界，避免引入中间 commit。
- `backend/tests/test_tenant_roi_datasource_binding.py` 包含手写 SQLite 表定义，模型字段变更必须同步。
- `frontend/src/views/system/tenant/Tenant.vue` 是大型共享页面，只改 ROI 配置区域与表单数据流。
- 工作区已有无关的知识库和路由修改；实施与验证不得覆盖或回退这些用户改动。

## Review Notes

- 根因：默认工作空间编辑请求按设计不提交 `roi_project_id`，但路由仍把 `None` 传给 `update_tenant`，会清空数据库中的既有值，同时审计错误记录为 `unchanged`。
- 修复：默认工作空间编辑时读取并传递既有 `roi_project_id`；显式提交非空值仍在进入事务前返回 400。
- 回归：新增默认工作空间保留值测试，并增强提交失败测试，确认 `roi_project_id` 与其他工作空间字段、绑定和审计一并回滚。
- 验证：在仓库根显式设置 `PYTHONPATH=<repo>/backend` 后，目标后端测试 54 项通过；前端 ROI 契约测试和 `npm run build` 通过；Alembic 为单一 `157workspaceprojectid` head。
