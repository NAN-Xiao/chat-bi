# 知识库上传者与默认启用

- 列表及详情的“更新”显示最近一次文档上传时的用户姓名（`sys_user.name`），不使用登录账号。
- `uploaded_by` 保存上传者 ID，`uploaded_by_name` 保存当时的姓名快照。改名称、说明或状态不改变上传身份。
- 历史记录无法可靠还原最近一次上传者，迁移不回填创建者，页面显示“—”。
- 新建默认启用；替换保留用户选择的启停设置。问答仍只读取启用且 `READY`、正文非空的记录。
- 解析失败会停用并保留错误；容量校验失败保留已解析正文，停用并显示错误，用户调整文档后可重新启用。
- 新建和替换文档都由上传 API 在本机进程中完成解析，等待解析结束后返回最终状态、正文与错误信息，不提交 Redis 队列任务，也不使用响应后的后台兜底。解析在 API 的线程池内执行，避免占用异步事件循环。
- 前端等待解析结束后显示结果；解析失败或容量校验失败时显示具体错误，不提示保存成功。失败记录仍保留，便于查看详情和重新上传。
- 处理期间停用或替换文档不会被旧处理覆盖。自动启用和手动启用共享 PostgreSQL 事务锁，避免并发完成时突破合计容量。
- 等待解析时释放上传事务的数据库连接；解析使用已选定文件的元数据快照，写回前重新加锁读取当前记录。解析期间或完成后被另一上传替换时返回明确的 `409 knowledge_upload_superseded`，记录被删除时返回 `404 knowledge_not_found`，不将另一上传的处理中状态当作本次保存成功。

## 发布顺序

1. 执行 Alembic 迁移 `a71d3c9e6b20`（新增两个可空列，不改变历史启停状态）。
2. 更新 API。新上传文档直接在接收文件的 API 进程中完成解析，`task_id` 为空；知识库上传不依赖 Worker 或队列配置。
3. 发布前端。已有队列任务仍保留原有处理入口：没有文件版本的 legacy 任务仅当上下文 ID 与记录保存的任务 ID 相同时处理；明确文件版本的任务不能覆盖后来上传的文档。其他后台功能仍使用各自配置的任务队列。

本次开发只验证隔离测试数据库中的迁移，不自动升级共享应用数据库。

## 回归测试

常规测试：`backend/.venv/Scripts/python.exe -m pytest backend/tests/test_knowledge_base_inline_processing.py backend/tests/test_knowledge_base_upload.py backend/tests/test_knowledge_base_workspace_admin.py backend/tests/test_knowledge_context.py -q`。

真实锁与隔离级别测试：设置 `KNOWLEDGE_TEST_POSTGRES_URL` 指向独立、可丢弃的 PostgreSQL 测试库后运行 `backend/tests/test_knowledge_base_upload_concurrency.py`。不要指向应用库或演示数据源。测试会创建并删除自己的 `knowledge_base` 表；库中已有同名表时创建会报错，不会覆盖它。
