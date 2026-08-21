# 实施计划

## 实现步骤

- [x] 在版本仓储中增加固定上限与租户隔离的裁剪方法，保护指针及活动发布任务版本。
- [x] 按“发布任务 -> 版本”的顺序删除候选，并返回去重后的源文件 ID。
- [x] 在普通创建草稿和回滚创建草稿两个 API 路径统一调用裁剪提交函数。
- [x] 在两个 API 提交成功后调用引用安全的源文件清理，并记录失败结果。
- [x] 增加仓储测试，覆盖最近 10 个、保护集合、删除顺序和租户边界。
- [x] 增加 API 测试，覆盖普通创建、回滚和文件清理失败。
- [x] 运行聚焦后端测试与 Ruff；运行知识库前端测试和构建，确认现有版本历史消费不回归。
- [x] 启动隔离本地栈，核对 API、MCP、Worker、前端和队列；使用真实 PostgreSQL 回滚事务验证 `RESTRICT/CASCADE` 删除链。
- [x] 将根因、修复和验证写入任务检查记录，并更新后端规范。

## 验证命令

```powershell
D:\AIWork3\chat-bi_ver\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_source_file_cleanup.py
D:\AIWork3\chat-bi_ver\backend\.venv\Scripts\python.exe -m ruff check backend/apps/knowledge_base backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_publish.py backend/tests/test_knowledge_source_file_cleanup.py
node --test frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs frontend/src/views/knowledge-base/KnowledgePage.layout.test.mjs
npm run build
```

## 风险与回滚点

- 版本删除不可恢复；测试必须证明选择集合只删除明确的超限版本。
- 数据库与文件系统不能组成同一事务；文件操作严格放在提交后，失败需保留诊断信息。
- 新版本创建接口已有响应结构，不能为返回清理统计而破坏前端类型契约。
- 浏览器验证不得通过批量创建真实业务版本污染共享数据库；优先使用测试知识库，完成后按既定永久删除流程清理。
