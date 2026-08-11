# 检查记录

## 已修复问题

- `frontend/src/views/knowledge-base/knowledgeMarkdownTemplates.ts`：原实现与点击同一调用栈内释放 Blob URL，浏览器可能尚未完成下载接管。改为移除临时锚点后在下一事件循环释放 URL。
- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.vue`：Element Plus `command` 事件允许 `string | number | object`，原处理函数错误收窄为模板对象。下拉项改为传递模板 ID，处理函数接受组件事件联合类型并只下载匹配模板。
- `frontend/tests/knowledgeMarkdownTemplates.test.ts`：原测试只检查函数返回后 URL 最终已释放，无法发现过早释放。增加点击、锚点移除、延迟调度和 URL 释放的顺序断言，并锁定模板 ID command 与事件处理签名。
- `.trellis/spec/frontend/project-runtime.md`：补充 Blob 下载 URL 必须延迟释放的可复用前端约束。

## 内容与布局审查

- 四类模板 ID、显示名、文件名和内容一一对应，均为 UTF-8 Markdown，包含填写提示和可替换示例，不含真实凭据或固定数据源 ID。
- 模板均使用围栏外 ATX 标题组织章节；业务 SQL 使用 `sql` 围栏代码块，符合现有标题切片规则。
- 顶部操作区保留 `min-width: 0` 和换行能力，980px 以下转为纵向头部；680px 以下输入、选择控件和模板入口占满宽度，模板按钮允许两行文本，避免在极窄内容区继续扩大滚动宽度。

## 验证结果

- 聚焦测试：`node --test tests/knowledgeMarkdownTemplates.test.ts`，3 passed。
- 前端构建与 TypeScript：`npm run build`，通过；仅有仓库既有 Rollup 导入和大 chunk 警告。
- 定向 ESLint：新增模板模块和测试通过；Vue 组件关闭既有 Prettier 规则后的语义 lint 通过。
- 完整定向 ESLint：未通过，原因是 `KnowledgeBaseV2Panel.vue` 在本任务前已存在大量整文件 Prettier 格式违规和一条属性顺序警告；未为本任务制造整文件格式化差异。
- `git diff --check`：通过；仅有 Git 的 LF/CRLF 行尾提示。
- 登录态浏览器在 1440x900 和 768x900 下验证：模板菜单四项完整，无页面级横向溢出，操作区无重叠；截图见 `artifacts/knowledge-template-desktop.png` 和 `artifacts/knowledge-template-narrow-768.png`。
- 真实点击普通文档、业务术语与 SQL、事件参数、表字段与 JSON Path 四项，下载目录生成对应 `.md` 文件；UTF-8 中文无替换字符，业务模板包含 `sql` 围栏。
- 390x844 下既有全局顶栏和固定侧栏仍使根页面 `scrollWidth=455`、`clientWidth=375`，不属于本组件；本次控件修复后 `.content-main` 为 `scrollWidth=150`、`clientWidth=150`，未继续扩大页面宽度，截图见 `artifacts/knowledge-template-mobile.png`。
- 打开既有知识编辑抽屉，确认替换源文件、保存草稿、校验、发布和版本历史入口保持可见。

## 剩余边界

- 全局管理控制台尚未适配 390px 手机宽度：顶栏品牌、工作空间控件和固定侧栏共同造成根页面横向溢出。本任务没有扩大到共享布局重构；模板控件自身已在该宽度下限制为内容区宽度。
- 验收期间创建的临时知识库 `发布验收-20260810` 归档时后端返回通用失败提示，记录仍保留。该问题与模板下载无关，未在本任务中修改知识库生命周期逻辑。

## 发布前全链路验收（2026-08-11）

- 隔离服务：前端 `5174` 与 API `8002/health` 均返回 200；独立 Worker 使用 `local-visual-knowledge-base-rag` 队列。既有 1.0 的 `5173/8000/8001` 未被停止或接管，`8001` 返回 404 证明 MCP 进程仍在监听；本功能保持 `MCP_ENABLED=false`。
- 生命周期：真实完成新建、Markdown 上传、草稿保存、校验、发布、源文件下载和发布任务 `SUCCEEDED · FINALIZE`。双页面并发创建草稿一方成功、一方返回 HTTP 409，并显示中文提示“该知识已有未发布草稿，请先处理当前草稿后再回滚。”
- AI 调用链：真实 Smart Q&A 成功生成折线图（`chat_id=866`、`record_id=2868`）；真实 AI 看板 SQL 生成并预览 7 行数据；真实综合分析助手完成分析并显示“已使用知识库（4）”。三条最新审计分别为 `SMART_QA`、`dashboard_ai_sql`、`analysis_assistant`，均命中 4 个切片且无 retrieval failure。
- 权限与对象投影：Schema、表、字段、JSON Path、事件权限、语义对象解析/投影及四个 AI surface 定向测试 `249 passed, 1 skipped`；知识库全套相关测试 `159 passed, 7 skipped`。
- 前端：模板聚焦测试 `3 passed`，新增模块与测试 ESLint 通过，`vue-tsc -b && vite build` 通过；构建仅有仓库既有动态导入和大 chunk 警告。
- 后端：修改文件 Ruff 通过，多切片哈希回归 `3 passed`，`git diff --check` 通过。Mypy 未进入类型分析，当前虚拟环境中的 `mypyc` 二进制模块名与安装包引用不一致，命令启动即报 `ModuleNotFoundError`；需重建/同步虚拟环境后补跑。
- 清理：临时知识库 `7` 已发布第二版并归档，`archived=true`；Smart Q&A、AI 看板、综合分析助手审计记录均保留。
- 发布阻塞：GitHub Actions `Synchronize to Gitee` 最近 5 次均失败。最新运行 `31467472538` 的镜像步骤退出码 1；完整日志需登录 GitHub，目标 Gitee 仓库为私有或不可匿名访问，本地无法验证 Secrets 和镜像落地。
