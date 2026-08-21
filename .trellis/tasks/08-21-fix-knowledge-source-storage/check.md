# 检查记录

## 规格核对

- API、MCP、Worker 和独立开发入口均通过 `Resolve-SharedRuntimeRoot` 解析共享的文件型运行目录。
- `BASE_DIR`、`LOCAL_MODEL_PATH`、日志、PID 和队列状态仍归当前 worktree 所有，没有扩大共享范围。
- 下载接口继续显式返回源文件不存在错误，前端公共请求层解码 Blob 错误后，由知识库入口展示重新上传并发布的操作提示。
- 没有从数据库正文、规范化内容或空文件重建原始上传文件。

## 自动验证

- `backend\.venv\Scripts\python.exe -m pytest tests/test_stack_local_script.py`：43 passed。
- 显式设置当前 worktree 的 `PYTHONPATH=backend` 后运行 `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_knowledge_base_publish.py`：9 passed；未设置时虚拟环境会误加载另一个 worktree 的模块。
- `node --test src/utils/requestBlobError.test.mjs src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs`：11 passed。
- PowerShell AST 解析：`tools/local-runtime-paths.ps1`、`backend-local.ps1`、`worker-local.ps1`、`dev-local.ps1` 全部通过。
- `backend\.venv\Scripts\python.exe -m ruff check tests/test_stack_local_script.py`：通过。
- 变更前端文件执行 ESLint（关闭仓库现有 Prettier 格式基线规则）：通过。
- `npm run build`：通过，包含 `vue-tsc -b` 与 Vite production build。
- `git diff --check`：通过。
- 在真实 linked worktree 执行目录解析，结果为 `D:\AIWork3\chat-bi_ver\.codex-runtime`，与 Git common dir 父目录一致。

## 运行时验证

- `8002` 已使用修复后的 `tools/backend-local.ps1` 重启并通过健康检查；`5174` 继续由当前 worktree 的 Vite 服务提供页面。
- API 与 Worker 使用同一隔离队列 `local-ELEX-fix-knowledge-source-storage`，PID、日志、队列文件保留在当前 worktree。
- 共享目录实际解析为 `D:\AIWork3\chat-bi_ver\.codex-runtime`；用户随后上传的 ID 27 新文件实际写入该目录，而当前 worktree 私有 `.codex-runtime/file` 为空。
- 用户重新上传 ID 27 后，Worker 完成发布，页面恢复“已发布”；真实点击版本 35 下载返回 `200 OK`。
- ID 26 版本 32 仍没有物理源文件，真实点击返回 `404 Not Found`，页面可见提示“知识源文件不存在，请重新上传源文件后再发布。”，未出现新的未处理 Promise。
- 任务开始时仍存在的 ID 19 版本 29 也通过真实页面点击返回 `200 OK`，证明切换到共享目录后可读取主 checkout 的既有文件。
- 没有伪造或从数据库内容生成原始文件；ID 26 仍需用户提供原件。

## 已知基线

- 对三个变更前端文件直接启用仓库的 `prettier/prettier` 规则会报告大量既存整文件格式和 CRLF 问题；本次没有用自动修复重排整个知识库面板，以免混入无关格式化改动。语义 ESLint、类型检查和构建均通过。
