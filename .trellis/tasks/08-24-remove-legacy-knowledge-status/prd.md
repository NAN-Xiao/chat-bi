# 移除知识库旧处理逻辑和主表状态字段

## Goal

知识库管理和处理统一使用 V2 版本化模型，删除会产生“待处理”等错误展示的旧内容处理管线及主表状态字段，避免新旧状态并存。

## Background

- 当前 V2 页面仍从 `knowledge_base.status` 展示“处理状态”，但真实发布和索引状态位于 `knowledge_base_version.status/index_status`。
- 已发布知识库可能出现主表 `status=PENDING`、版本 `PUBLISHED/READY`，造成用户误判。
- `backend/apps/knowledge_base/api/knowledge_base.py` 仍保留旧 `/knowledge-base/save` 上传入口和旧处理任务回退。
- `backend/apps/knowledge_base/tasks.py` 同时包含旧 `knowledge_base.process_document` 与当前 V2 发布任务。
- 当前数据库已使用 V2 版本、发布任务和知识块作为检索权威数据。

## Requirements

1. 删除 `knowledge_base.status`、`knowledge_base.task_id`、`knowledge_base.error_message` 三个旧主表字段及其索引。
2. 删除 `KnowledgeBaseStatusEnum` 和上述字段的后端模型、序列化及 API 契约。
3. 删除旧 `/knowledge-base/save` 内容处理入口、旧列表/删除分发和 `knowledge_base.process_document` 任务处理逻辑。
4. 知识库列表、详情、创建、删除统一走 V2 管理实现，不再根据能力状态回退到旧实现。
5. 前端知识库入口只渲染 V2 管理页，不再保留旧卡片页、旧状态轮询和旧上传表单。
6. V2 页面不得显示来自主表的“处理状态”；发布与索引状态必须来自版本和发布任务模型。
7. 保留当前 V2 字段：`knowledge_base_version.error_message`、`knowledge_publish_job.task_id/error_message/status/stage`。
8. 保留迁移阶段/能力安全门，用于部署和维护保护；它们不得再启用旧内容处理路径。
9. 数据库迁移必须可回滚；降级恢复列时只恢复空的兼容列，不伪造历史处理状态。

## Acceptance Criteria

- [ ] 新迁移升级后，`knowledge_base` 不再包含 `status`、`task_id`、`error_message`，`idx_knowledge_base_status` 不存在。
- [ ] `KnowledgeBase` ORM 和前端 `KnowledgeBaseItem` 类型不再暴露旧字段。
- [ ] 应用路由中不存在 `POST /knowledge-base/save`。
- [ ] 任务注册表中不存在 `knowledge_base.process_document`，V2 发布任务仍可注册和执行。
- [ ] `GET /knowledge-base/list` 与删除入口不再调用 legacy 实现。
- [ ] 知识库页面不再显示“处理状态/待处理”，仍能显示已发布、发布中、尚未发布及归档状态。
- [ ] 后端知识库相关测试、迁移检查和前端构建通过。
- [ ] 运行中的 V2 知识库页面完成桌面与移动端浏览器验证，无新增横向溢出。

## Out Of Scope

- 不修改知识检索查询构造或 Top-K 策略。
- 不删除 V2 发布任务、版本错误字段、迁移阶段表或维护安全门。
- 不自动修改现有知识内容、版本、知识块或向量数据。

## Risks

- 删除列是破坏性数据库变更，部署必须先确认所有实例已使用本次代码。
- 仍调用 `/knowledge-base/save` 的外部旧客户端会收到 404，不提供兼容回退。
- 回滚只能恢复字段结构，无法还原被删除的历史字段值。
