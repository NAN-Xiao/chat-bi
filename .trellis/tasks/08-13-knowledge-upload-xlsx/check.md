# 检查记录

## 已通过

- `backend/.venv/Scripts/python.exe -m pytest tests/test_knowledge_base_chunking.py tests/test_knowledge_base_publish.py -q`
  - 15 passed。
- `node --test src/views/knowledge-base/KnowledgeSourceUpload.test.mjs src/views/knowledge-base/KnowledgePage.layout.test.mjs`
  - 8 passed。
- `node --test src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs src/views/knowledge-base/KnowledgeSourceUpload.test.mjs`
  - 8 passed，覆盖操作顺序、显式版本选择、上传拒绝消费和 Blob 清理。
- `npm run build`
  - `vue-tsc -b` 与 Vite production build 通过；仅有项目既有的 bundle/dynamic import 警告。
- 本工作区前端在 `0.0.0.0:5190` 启动并返回 HTTP 200；进程命令行确认来自 `D:/AIWork3/chat-bi_ver/frontend`。
- `git diff --check` 通过。

## 扩大检查

- 全部 `test_knowledge_base*.py`：162 passed、7 skipped、2 failed。失败位于 `test_knowledge_base_management_api.py`，分别是并行路由对象缺少 `path`、迁移阶段期望 `LEGACY` 但实际为 `UPGRADING`，与上传/Excel 链路无关。
- 全部知识库前端 Node 测试：28 passed、1 failed。失败是并行加入的归档版本下载逻辑与旧的“不查询 versions”断言冲突；本任务新增测试全部通过。

## 运行环境说明

- 本工作区前端按用户确认使用 `5190`；未操作 `5173`。
- 应用内浏览器访问知识库路由时无登录态，被重定向到登录页，因此未完成真实上传/下载按钮点击；接口回归、前端源码契约测试和构建均已通过。
