# 实施计划

## 1. 建立严格 Markdown 内容契约

- [x] 新增前端 Markdown 格式解析/校验模块，集中定义结构校验和用户提示。
- [x] 确保四个现有纯 Markdown 下载模板通过同一前端校验器。
- [x] 新增后端 Markdown 内容结构校验模块并返回稳定错误类型。
- [x] 增加共享 good/base/bad fixture 契约测试，覆盖纯 Markdown、BOM、非法 UTF-8、缺少 H1/H2/正文及未闭合围栏。

## 2. 统一上传入口为 Markdown

- [x] 新建弹窗、列表行上传、编辑页替换源文件统一调用异步前端校验器，只接受 `.md / .markdown`。
- [x] 更新 accept、提示和文件状态清理，确保校验失败不保留上一次选择。
- [x] 后端 V2 和 legacy 上传入口统一限制扩展名，并在保存草稿前执行权威 Markdown 结构校验。
- [x] 覆盖格式失败后 payload、revision、source reference 和暂存文件不变的回归测试。

## 3. 移除用户知识类型及运行时分支

- [x] 删除创建表单类型字段、列表类型列、响应类型字段和前端多类型分支。
- [x] 简化前端 payload/editor 为普通 Document，删除不再使用的三类专用编辑组件和辅助组件。
- [x] 创建 API 禁止 `knowledge_type` 输入并固定持久化 `DOCUMENT`。
- [x] 简化后端 schema、normalizer、validator、object reference projection、structured context、chunking 和 publisher 的类型分支，仅保留 Document 行为。
- [x] 保留固定内部存储判别值和普通文档对象引用能力，更新受影响测试。

## 4. Focused Verification

- [x] 前端模板、上传、布局、payload 序列化和行操作 Node 测试：41 passed。
- [x] 后端知识库相关与 object reference 回归：210 passed，7 skipped。
- [x] `npm run build`，包含 `vue-tsc -b`。
- [x] 改动文件 `ruff check` 与后端 `compileall`；Mypy 因共享虚拟环境缺失 mypyc 编译模块无法启动，详见 `check.md`。
- [x] `git diff --check`。

## 5. Runtime And Browser Gate

- [x] 使用当前 worktree 的隔离端口启动/验证前端、API、MCP 和 Worker，不接管其他 worktree 进程。
- [x] 核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。
- [ ] 真实点击下载四种模板并逐一上传；验证纯 Markdown 可选中，Word、Excel 和结构错误文件均显示“格式错误”。隔离端口无登录态，停在登录页。
- [ ] 验证创建、编辑知识块、替换源文件、校验、发布和下载源文件完整路径。隔离端口无登录态，未越权使用未知密码。
- [ ] 检查登录后桌面和移动视口、页面级横向溢出、顶部操作区和列表操作列，保存并人工检查截图。

## 6. 用户反馈：移除文档内平台元数据

- [x] 下载模板和普通 Markdown 上传不再生成或要求 `template_type`、`template_version` front matter。
- [x] 前后端共享纯 Markdown 内容结构契约，继续覆盖编码、标题、正文和围栏错误。
- [x] 服务端使用 `markdown-v1` 自动标记解析器，并在 V2 源文件替换时写入 `knowledge_base_version.parser_version`。
- [x] 修正运行时错误提示、错误码、测试与项目规范，并移除前端 `yaml` 直接依赖。
- [x] 最终纠偏回归：前端知识库 42 passed；后端知识库 181 passed、7 skipped；混合围栏解析、文件级 UTF-8/扩展名、服务端解析器持久化、前端构建、Ruff、ESLint、compileall 与 `git diff --check` 通过。Mypy 仍受共享环境缺失 mypyc 模块阻塞。
- [x] 主会话移除主检出文档样例中的平台 front matter 后，验证 `JSON字段解析_通用.md` 可直接通过前后端解析。

## Risk And Rollback Points

- payload adapter 简化会影响发布和对象权限投影，完成第 3 步后必须先跑后端定向回归再进入运行时验收。
- 上传失败必须发生在 CAS 保存前；若测试发现 revision 或文件引用被改写，停止后续步骤并修正事务边界。
- 不修改数据库数据或执行知识库回填；若运行时发现非 Document 记录，停止并重新进入规划，不添加静默兼容。
