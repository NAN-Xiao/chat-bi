# Implementation Plan

1. 新增 Alembic 迁移，删除旧索引和主表三列，并添加结构测试。
2. 更新 `KnowledgeBase` 模型、序列化与管理 API，移除旧状态契约和 legacy dispatch。
3. 删除旧保存路由与旧文档处理 handler，保留 V2 发布 handler 注册。
4. 更新前端 API 类型和知识库入口，移除旧页面分支及 V2 主表处理状态列。
5. 更新/删除只验证旧兼容行为的测试，补充 V2 单一路径、路由缺失、任务未注册和序列化契约测试。
6. 运行后端知识库测试与 Alembic heads/check，运行前端专项测试和 `npm run build`。
7. 在目标 worktree 启动或验证本地栈，通过浏览器检查知识库列表桌面/移动布局和横向溢出。
8. 执行 `trellis-check`，记录实现与验证结果。

## Risky Files

- `backend/apps/knowledge_base/models.py`
- `backend/apps/knowledge_base/api/management.py`
- `backend/apps/knowledge_base/api/knowledge_base.py`
- `backend/apps/knowledge_base/tasks.py`
- `backend/apps/api.py`
- `frontend/src/views/knowledge-base/index.vue`
- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.vue`
- `frontend/src/api/knowledgeBase.ts`
- `backend/alembic/versions/*`

## Validation Commands

```powershell
cd backend
pytest tests/test_knowledge_base_management_api.py tests/test_knowledge_base_workspace_management.py tests/test_knowledge_base_publish.py tests/test_knowledge_base_serialization.py
python -m alembic heads

cd ../frontend
node --test src/views/knowledge-base/*.test.mjs
npm run build
```

## Rollback Point

在数据库迁移应用前保留系统数据库备份；若测试或运行验证失败，回退应用提交并执行对应 Alembic downgrade。

## Implementation Result

- 新增 Alembic revision `166removelegacykbstate`，升级删除主表旧索引和三列，降级只恢复 nullable 兼容列及索引。
- 删除旧 `/knowledge-base/save` router、legacy list/delete 分发和 `knowledge_base.process_document` handler；保留 V2 capability/cutover 安全门、backfill 和 publish handler。
- `KnowledgeBase` ORM、管理响应和前端 `KnowledgeBaseItem` 不再暴露 `status`、`task_id`、`error_message`。
- 知识库前端入口简化为单一 `KnowledgeBaseV2Panel`，移除旧卡片页、模式选择、轮询/上传表单和主表“处理状态”列。
- 保留 `KnowledgeBaseVersion.error_message` 与 `KnowledgePublishJob.status/stage/task_id/error_message`，RAG、Top-K 和知识块检索逻辑未修改。
- 更新后端/前端运行规范，固化 V2 单一路径和状态归属约束。
- 共享系统数据库未执行 migration；实际升级前必须备份并确认所有应用实例已切换到本次代码。
