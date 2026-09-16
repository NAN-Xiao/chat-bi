# 知识库上传者与默认启用

- 列表及详情的“更新”显示最近一次文档上传时的用户姓名（`sys_user.name`），不使用登录账号。
- `uploaded_by` 保存上传者 ID，`uploaded_by_name` 保存当时的姓名快照。改名称、说明或状态不改变上传身份。
- 历史记录无法可靠还原最近一次上传者，迁移不回填创建者，页面显示“—”。
- 新建默认启用；替换保留用户选择的启停设置。问答仍只读取启用且 `READY`、正文非空的记录。
- 解析失败会停用并保留错误；容量校验失败保留已解析正文，停用并显示错误，用户调整文档后可重新启用。
- 处理期间停用或替换文档不会被旧任务覆盖。自动启用和手动启用共享 PostgreSQL 事务锁，避免并发完成时突破合计容量。

## 发布顺序

1. 执行 Alembic 迁移 `a71d3c9e6b20`（新增两个可空列，不改变历史启停状态）。
2. 更新 API 和 Worker，再启用新版上传入口；不要让旧 Worker 消费新版上传任务。
3. 发布前端。已有队列任务使用明确的 legacy 入口：仅当任务上下文 ID 与记录保存的任务 ID 相同时处理，不能覆盖明确的文件版本或后来上传的文档。

本次开发只验证隔离测试数据库中的迁移，不自动升级共享应用数据库。

## 回归测试

常规测试：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_knowledge_base_upload.py backend/tests/test_knowledge_base_workspace_admin.py backend/tests/test_knowledge_context.py -q`。

真实锁与隔离级别测试：设置 `KNOWLEDGE_TEST_POSTGRES_URL` 指向独立、可丢弃的 PostgreSQL 测试库后运行 `backend/tests/test_knowledge_base_upload_concurrency.py`。不要指向应用库或演示数据源。测试会创建并删除自己的 `knowledge_base` 表；库中已有同名表时创建会报错，不会覆盖它。
