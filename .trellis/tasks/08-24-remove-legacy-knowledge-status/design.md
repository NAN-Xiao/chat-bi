# Technical Design

## Boundary

V2 权威模型保持不变：

- `knowledge_base`：知识库身份、范围、归档和版本指针。
- `knowledge_base_version`：草稿/发布版本及索引状态。
- `knowledge_publish_job`：发布任务状态、阶段、任务 ID 和错误。
- `knowledge_base_chunk`：当前发布版本的检索知识块和向量。

删除的旧模型职责为：主表处理状态、旧单文件上传处理、旧后台解析任务及前端旧卡片页面。

## Backend Changes

1. 新 Alembic 迁移先删除 `idx_knowledge_base_status`，再删除三列；downgrade 恢复 nullable/default 兼容列和索引。
2. `KnowledgeBase` 与响应序列化只保留 V2 管理需要的字段。
3. `management.py` 取消 legacy dispatch，列表和删除始终执行 V2 逻辑。
4. 不再挂载旧 API router，并删除只服务旧入口的代码。
5. 从任务模块移除旧解析 handler，保留 `knowledge_base.publish_version` handler。
6. 能力/迁移安全门继续保护 V2 写操作，但不再返回可执行旧写入的应用路径。

## Frontend Changes

1. `knowledge-base/index.vue` 简化为 V2 页面容器。
2. 删除旧保存 API、旧状态字段类型和旧模式分支的仅旧页面代码。
3. V2 列表移除 `row.status` 的“处理状态”列；发布版本列继续使用版本指针，编辑器继续使用版本/发布任务状态。

## Compatibility

- 不保留 `/knowledge-base/save` 兼容入口，这是用户明确要求删除旧逻辑的行为变化。
- V2 API 路径保持不变。
- 新发布任务字段不变。
- 数据库迁移 downgrade 只恢复结构，不恢复旧业务语义。

## Rollout And Rollback

- 升级前备份系统数据库，并确保没有旧版本应用实例继续写主表旧字段。
- 先部署代码再执行迁移或在单实例维护窗口内原子升级。
- 回滚时先回滚应用，再执行 downgrade；恢复字段仅用于旧代码启动，不保证旧状态准确。
