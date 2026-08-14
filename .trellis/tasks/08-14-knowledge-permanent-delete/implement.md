# 实施计划

## 实现步骤

- [x] 在知识库文件清理模块中实现候选文件收集、全局引用检查和结构化清理结果。
- [x] 扩展版本仓储，按依赖顺序删除发布任务、版本和知识库记录，并让未发布删除返回候选文件 ID。
- [x] 扩展生命周期服务，增加“仅已归档可永久删除”的状态机入口及错误码。
- [x] 新增 V2 永久删除 API，在数据库提交后清理无引用物理文件并返回统计。
- [x] 将同一清理 helper 接入未发布知识库删除和草稿源文件替换成功路径。
- [x] 增加前端 API、逐行 busy 状态、已归档行/详情永久删除按钮及名称确认交互。
- [x] 更新聚焦前端测试，覆盖入口可见性、确认规则和 API 调用。
- [x] 增加后端状态机、仓储/API与文件引用回归测试。
- [x] 执行 Trellis 检查、后端聚焦测试、Ruff、前端测试与构建。
- [x] 使用隔离预览 API 验证已归档桌面页面、权限差异和名称确认交互，不触碰真实业务数据。
- [ ] 完整本地栈的移动端截图验证；本轮浏览器会话中断，未将此项误记为完成。

## 重点验证

- 未归档永久删除被拒绝；已归档且有权限可删除；无权限不可删除。
- 有历史发布任务和检索投影的数据可完整删除，不触发 `RESTRICT` 外键错误。
- 共享 `file_id` 保留，最后引用删除后才清理；文件缺失与 I/O 失败返回不同结果。
- 上传解析失败和 CAS 冲突不删除旧文件，上传成功只清理无引用旧文件。
- 现有归档、恢复、回滚、发布和下载行为不回归。

## 验证命令

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_workspace_management.py backend/tests/test_knowledge_base_publish.py
backend\.venv\Scripts\python.exe -m ruff check backend/apps/knowledge_base backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_workspace_management.py backend/tests/test_knowledge_base_publish.py
node --test frontend/src/views/knowledge-base/KnowledgePage.layout.test.mjs frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs frontend/src/views/knowledge-base/KnowledgeSourceUpload.test.mjs
npm run build
```

## 风险与回滚点

- 数据库删除与文件系统不能形成同一原子事务；数据库提交后文件清理失败必须显式报告并留日志，后续可重试清理，不能回滚为伪成功记录。
- 依赖表有 `CASCADE` 与 `RESTRICT` 混合关系；仓储测试和 PostgreSQL 集成验证需证明删除顺序正确。
- 前端操作列增加按钮后必须检查桌面操作区和移动端横向溢出。
