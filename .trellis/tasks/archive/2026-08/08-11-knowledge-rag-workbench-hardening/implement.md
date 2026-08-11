# 实施计划

1. 更新知识库页面状态模型、列表错误状态和重试入口。
2. 更新检索结果、语义上下文和助手快照的数据契约，补充失败状态。
3. 更新检索预览与聊天引用组件，展示可核验来源信息并隐藏内部 ID。
4. 添加或更新 frontend/backend 定向回归测试。
5. 运行前端测试、构建、实际页面验证；尝试 backend 定向测试并记录环境阻塞。
6. 执行 Trellis check，确认跨层数据流、权限边界和工作区变更范围。

验证命令：

- `node --test` 知识库和引用相关 `.mjs` 测试
- `npm run build`（`frontend/`）
- `backend\\.venv\\Scripts\\python.exe -m pytest` 知识库定向测试（若环境可用）
- 浏览器访问 `/system/knowledge-base`，检查 capability、空态、错误态和引用展示

## 本次执行记录

- 已完成能力探测错误态、列表错误/空态分离、检索失败类型透传、引用来源元数据和聊天/预览展示。
- 前端定向测试：12 项通过；`npm run build` 通过，包含 `vue-tsc -b`。
- 后端目标文件 `compileall` 通过；pytest 未能收集，当前环境缺少 `fastapi`、`sqlalchemy`，且没有可用 `backend/.venv`；ruff/mypy 命令也不可用。
- 浏览器验证：桌面知识库页面正常进入服务端明确返回的 `LEGACY` 模式，空列表正常显示；桌面页面无横向溢出。移动端发现全局顶栏既有横向菜单使页面整体溢出，知识库内容区未新增该问题，未在本任务中扩展全局导航改造。
- 未开启 `KNOWLEDGE_MANAGEMENT_V2_ENABLED`；pgvector 索引、hybrid/rerank、PDF/PPTX/OCR 和评测中心仍为后续任务。

## 本轮页面实现与验证

- 将实际可见的旧版知识库管理页改为密集管理表格，增加全部/平台/工作空间范围筛选、源文件、处理状态、更新时间和权限列；详情抽屉拆分为概览与源文档两个 Tab。
- 管理员的编辑入口进入编辑抽屉，普通用户只显示查看；平台公共知识的新增、修改、删除权限继续由后端 `KnowledgePermissionService` 强校验，前端仅做入口收敛。
- 修复范围筛选与移动端控件的最小宽度问题，数据表横向滚动限制在内容区内；补充布局测试覆盖平台知识只读展示。
- 知识库相关前端测试 12 项通过，`npm run build` 通过，后端知识库模块 `compileall` 通过，`git diff --check` 通过。
- 定向 pytest 仍无法执行：当前工作区不存在 `backend/.venv`，系统 Python 也未提供项目所需的 FastAPI/SQLAlchemy 运行环境。
- 当前工作区前端已在 `http://127.0.0.1:5174/` 实际验证；`5173` 监听的是相邻 `D:\AIWork3\chat-bi` 工作区旧实例。当前 API 明确返回 V2 管理模式，桌面主内容区无横向溢出；移动端整体横向滚动来自既有全局侧栏/顶栏，未扩展全局导航改造。

## 部署版本错位复盘

- 用户截图中的 `405 Method Not Allowed` 来自新版前端请求 `GET /knowledge-base/capabilities`，但目标环境后端仍是 release 1.0，未注册 capability 路由；中间版本前端随后静默回退到旧版卡片页，因此同时出现 405 提示和“暂无知识库”。
- Jenkins `chat-ai` 任务的参数默认值和 Git BranchSpec 均固定为 `release/release_1.0.0`；最新构建 174 使用提交 `2788ab9c`，不会自动包含 release 2.0 的 `6825c5fa`。
- release 2.0 已取消 capability 失败后的 LEGACY 静默回退，并补充应用主路由级回归测试，确保最终 `api_router` 同时挂载 `GET /knowledge-base/capabilities` 和 `GET /knowledge-base/list`。
- 未修改远程 Jenkins 配置、release 1.0 分支或运行中容器；部署 release 2.0 前必须先明确调整流水线分支并进行完整前后端同版本发布。
- 已将发布版本一致性、最终应用路由验证和禁止 capability 静默回退的契约写入 `.trellis/spec/backend/project-runtime.md`，并在跨层检查指南中增加 CI 分支与部署 API 核验清单。
- 本仓库不存在 `src/templates/markdown/spec/` 或 `packages/cli/src/templates/` 等规范模板同步目录，本次无需同步模板副本。
- 本轮复验：知识库前端测试 13/13 通过，主路由回归测试文件 `compileall` 通过，`git diff --check` 通过；定向 pytest 仍因当前 Python 环境缺少 `fastapi` 在收集阶段阻塞。
