# 检查记录

## 已修复问题

- `backend/apps/knowledge_base/api/knowledge_base.py`：Legacy 创建路径未写入固定内部 `DOCUMENT` 标记。现与 V2 创建一致，所有新记录固定持久化为普通文档。
- `backend/apps/knowledge_base/api/knowledge_base.py`：Legacy 替换源文件在数据库提交前删除旧文件，提交失败可能丢失旧源并遗留新文件。现改为提交失败回滚并删除本次新文件；提交成功后再通过引用感知清理删除无引用旧文件。
- `backend/apps/knowledge_base/markdown_template.py`：前端 YAML 解析器拒绝重复 front matter 键，后端 PyYAML 原先接受最后一个值。现后端安全加载器也拒绝重复键，避免绕过前端时出现契约漂移。
- `frontend/src/i18n/en.json`：英文知识库上传提示仍宣称支持 Word/Excel。现四个 locale 都只描述下载模板格式的 Markdown。
- `frontend/src/views/knowledge-base/knowledgePayloadTypes.ts`：删除只被测试调用、生产路径未使用且触发 lint 的 `applyParsedUpload` 死辅助函数。
- `.trellis/spec/backend/knowledge-base-rag.md`、`.trellis/spec/frontend/project-runtime.md`：同步单一普通文档模型、严格 Markdown 模板、三入口预检及源文件原子清理契约。

## 验证结果

- 最终后端知识库相关回归：210 passed，7 skipped；包含最新重复 YAML key 回归用例。
- 最终前端聚焦 Node 测试：41 passed。
- 前端类型检查与生产构建：`npm run build` 通过；仅保留既有动态导入和大 chunk 警告。
- 改动后端文件 Ruff：通过。
- 后端知识库模块与测试 `compileall`：通过。
- 改动前端文件语义 ESLint（关闭既有 Prettier/CRLF 规则）：通过。
- `git diff --check`：通过；仅有 Git 的 LF/CRLF 转换提示。
- Trellis 任务校验：通过，implement/check context 均登记 3 个适用 spec。

## 环境与剩余验证

- 后端 Mypy 无法启动：共享虚拟环境缺少编译模块 `0aca9ce3d91742c5b361__mypyc`，在类型分析前即失败；不是本次代码产生的类型错误。
- 共享虚拟环境还注入了另一个旧 worktree 的 backend 路径；最终测试显式将当前 worktree 的 `backend` 放到 `PYTHONPATH` 首位，并核对导入文件均来自当前 worktree。
- 仓库级 Ruff 仍有 31 条既有问题，位于本任务未修改的 `api/publish.py`、`models.py` 和 `validation_context.py`。
- 前端完整 Prettier lint 仍受大型历史 Vue 文件和 CRLF 基线影响；本次改动文件的非 Prettier 语义规则已通过。
- 主会话已使用隔离端口启动并验证完整四服务栈：前端 `5200`、API `8040`、MCP `8041`、Worker 队列 `local-unify-knowledge-document-type-8040`。前端返回 200，API 登录方式端点返回预期 401，且核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。
- 隔离端口没有可复用登录态，浏览器进入真实应用后被重定向到 `#/login`。未输入仓库未知的默认密码，因此四模板真实点击下载/上传、发布流程及登录后桌面/移动截图仍未完成。临时服务、进程和 `.venv` junction 已清理。
