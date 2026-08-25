# 知识库在线文档编辑器技术设计

## 1. 页面边界

`KnowledgeBaseV2Panel.vue` 继续拥有列表筛选、记录加载、权限、草稿、校验、发布和冲突状态，但编辑入口从 `el-drawer` 改为同组件内的页面模式：

- `editorVisible=false`：渲染现有列表页。
- `editorVisible=true`：渲染全页知识文档工作区。
- 不新增后端接口，不改变现有 `/system/knowledge-base/platform|workspace` 路由和作用域解析。
- 返回编辑列表时保留当前组件中的关键词、工作空间和归档筛选；关闭前先执行保存收敛。

## 2. 组件分工

- `KnowledgeBaseV2Panel.vue`：生命周期顶栏、自动保存队列、冲突、校验、发布、源文件、历史版本和编辑/列表模式切换。
- `KnowledgePayloadEditor.vue`：透传文档 payload、只读状态和保存状态。
- `editors/DocumentEditor.vue`：目录、精简工具栏、连续文档画布、活动块选择、块结构操作。
- 新增 `editors/KnowledgeMarkdownEditor.vue`：封装 Tiptap Vue 编辑器，输入输出均为 Markdown，并通过 `defineExpose` 暴露撤销、重做、段落、列表和引用命令。
- 新增纯函数模块负责 Markdown 内容比较、保存响应合并和编辑器格式能力判断，便于 Node 单测覆盖。

## 3. 编辑器选择与 Markdown 契约

使用 Tiptap 3 的 Vue、StarterKit 和官方 Markdown 扩展。原因：

- ProseMirror 提供成熟的选择、撤销、列表和粘贴行为，避免手写 `contenteditable` 或使用已废弃的 `document.execCommand`。
- 官方 Markdown 扩展允许初始化 Markdown 并通过 `getMarkdown()` 回写，后端仍以 Markdown 为权威格式。
- 编辑器无内置工具栏，便于严格实现已确认的精简工具栏。

编辑器规则：

- 初始化、外部冲突载入和活动块切换时设置 Markdown 内容，但不发出用户修改事件。
- 仅 `onUpdate` 产生 payload 更新；只读或未实际编辑时绝不重新序列化块正文。
- 工具栏不暴露加粗、斜体、下划线、表格和链接命令；解析扩展仍可读取已有语法，防止内容破坏。
- 预览继续使用项目 `markdown-it` 并通过 `v-dompurify-html` 输出。
- 对官方 Markdown 扩展无法无损解析的输入，保持原 Markdown，禁止仅因组件挂载触发保存；回归夹具覆盖平台允许的主要 Markdown 结构。

## 4. 连续画布与单编辑器实例

画布按 `blocks[]` 顺序渲染所有块：

- 活动块：标题输入与 `KnowledgeMarkdownEditor`。
- 非活动块：标题和清洗后的 Markdown 预览；点击后切换为活动块。
- 目录使用稳定块 ID 定位；切换时保持浏览位置并将对应块滚动到可见区域。
- 新增/复制后激活新块；排序保持当前块 ID；删除活动块后选择相邻块。
- 桌面左侧目录独立滚动；移动端目录变为横向滚动条，正文保持单列。

## 5. 自动保存状态机

新增状态：`clean | dirty | saving | conflict | error`。

1. 用户修改 payload 后递增本地 mutation 序号，状态变为 `dirty`，启动短防抖。
2. 防抖到期后克隆当前 payload 和 mutation 序号，进入 `saving`，调用现有块级/结构保存流程。
3. 保存期间继续允许输入；新输入只更新实时 payload 并标记待续保存，不发起并行请求。
4. 响应返回后，将服务端 `block_revision`、`structure_revision` 和文档 `revision` 合并到实时 payload：当前内容仍等于请求快照时可采用服务端块；当前内容已变化时保留实时标题、正文、状态和顺序，只更新对应服务端 revision。
5. 若 mutation 序号已变化，重新进入 `dirty` 并安排下一次保存；否则进入 `clean`。
6. 409 进入 `conflict` 并沿用现有冲突快照；网络或业务错误进入 `error`，不清除本地内容。

校验、发布、返回和 `Ctrl+S` 调用统一的 `flushPendingSave()`：取消防抖、等待在途保存、继续保存最新变更，直到 `clean` 或出现错误/冲突。只有 `clean` 才能继续后续动作。

## 6. 生命周期与辅助功能

- 顶栏保留作用域、适用性、草稿/发布状态和工作空间开关。
- 主要命令为创建草稿、校验和发布；自动保存状态替代常驻“保存草稿”按钮，`Ctrl+S` 仍可立即保存。
- 源文件上传放入顶栏的上传入口，仍调用现有严格 Markdown 替换接口。
- 历史版本使用右侧辅助抽屉/面板打开，保留下载和回滚操作；该辅助抽屉不是正文编辑容器。
- 归档记录保持只读，并在顶栏提供恢复/永久删除。

## 7. 兼容与安全

- `KnowledgePayload`、API 请求体、后端 schema 和数据库均不修改。
- 隐藏的 `tags`、`datasource_neutral` 和 `object_references` 继续由 payload 规范化和结构保存原样携带。
- 只读态不注册保存调度，不暴露结构操作，编辑器设置为不可编辑。
- `beforeunload` 在 `dirty/saving/conflict/error` 时提示；应用内返回优先尝试 flush，失败则停留页面。
- Markdown 预览继续禁用原始 HTML，并经过 DOMPurify，不能因引入富文本编辑器扩大脚本注入面。

## 8. 回滚

- 前端回滚可恢复原 `DocumentEditor.vue` 文本框和 `KnowledgeBaseV2Panel.vue` 抽屉模板；后端数据无迁移，无需数据回滚。
- 新依赖只服务于前端编辑组件，删除组件和 package 依赖即可回退。
- 自动保存出现不可接受问题时可保留全页布局并恢复显式保存按钮，不影响块级 API。
