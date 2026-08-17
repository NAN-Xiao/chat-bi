# 检查记录

## 用户反馈修正：平台元数据不进入 Markdown

- 根因：原设计用 `template_type` 和 `template_version` front matter 识别上传模板，把已经统一后的内部文档类型和解析协议版本泄露给用户内容；Markdown 渲染器因此把它展示为“元数据”，无标记的合法文档也被拒绝。
- 修正：下载模板和上传文件统一为纯 Markdown；前后端继续校验 UTF-8、H1/H2、有效正文和围栏闭合，但不生成或要求平台元数据。
- 持久化：服务端解析器自动产生 `markdown-v1`，V2 上传通过 `SourceFileRef.parser_version` 写入现有 `knowledge_base_version.parser_version`；客户端和文档均不能指定该值。
- API：V2 格式错误码改为 `KNOWLEDGE_MARKDOWN_FORMAT_INVALID`，错误提示不再要求重新下载模板。

## 本轮验证

- 后端最新聚焦回归：`38 passed`，覆盖纯 Markdown、BOM、非法结构、上传原子性、混合围栏及 `parser_version` 传递。
- 前端最新聚焦回归：`19 passed`，覆盖四类下载模板、三处上传入口、四语言提示、文件预检和结构错误。
- `npm run build`：通过；仅保留既有动态/静态导入和大 chunk 警告。
- 改动后端文件 Ruff：通过；`git diff --check` 通过，仅有仓库行尾转换提示。
- 实际文件 `D:/AIWork3/chat-bi_ver/docs/模版/JSON字段解析_通用.md` 已移除 front matter；前端文件解析器和后端解析器均通过，后端标记 `markdown-v1`。

## 已修复问题

- `backend/apps/knowledge_base/api/knowledge_base.py`：Legacy 创建路径未写入固定内部 `DOCUMENT` 标记。现与 V2 创建一致，所有新记录固定持久化为普通文档。
- `backend/apps/knowledge_base/api/knowledge_base.py`：Legacy 替换源文件在数据库提交前删除旧文件，提交失败可能丢失旧源并遗留新文件。现改为提交失败回滚并删除本次新文件；提交成功后再通过引用感知清理删除无引用旧文件。
- `backend/apps/knowledge_base/markdown_template.py`：移除 YAML front matter 解析和模板类型/版本常量，改为纯 Markdown 结构校验，并由服务端返回 `markdown-v1` 解析器版本。
- `frontend/src/i18n/en.json`：英文知识库上传提示仍宣称支持 Word/Excel。现四个 locale 都只描述符合内容结构要求的 Markdown，不要求下载模板标记。
- `frontend/src/views/knowledge-base/knowledgePayloadTypes.ts`：删除只被测试调用、生产路径未使用且触发 lint 的 `applyParsedUpload` 死辅助函数。
- `backend/apps/knowledge_base/markdown_template.py`、`schemas.py`、`chunking.py` 与前端 `knowledgeMarkdownFormat.ts`：修复混合 Markdown 围栏状态漂移。现在代码块内的伪 H2 不会满足章节校验或生成知识块，反引号围栏内出现 `~~~` 也不会错误结束代码块；补充文件级 UTF-8、扩展名、章节拆分和知识块转换回归。
- `frontend/src/views/knowledge-base/knowledgeMarkdownFormat.ts`：最终构建捕获围栏状态快照的 TypeScript 隐式 `any`，已补充显式 `string | null` 类型并复验构建。
- `.trellis/spec/backend/knowledge-base-rag.md`、`.trellis/spec/frontend/project-runtime.md`：同步单一普通文档模型、纯 Markdown 结构校验、服务端解析器版本、三入口预检及源文件原子清理契约。

## 验证结果

- 最终后端知识库相关回归：181 passed，7 skipped；覆盖纯 Markdown 结构、混合围栏与服务端解析器版本持久化。
- 最终前端知识库 Node 测试：42 passed。
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
