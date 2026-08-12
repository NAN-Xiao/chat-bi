# 知识文档多知识块编辑实施清单

1. 扩展后端 `DocumentPayload`、规范化、校验和对象引用解析，加入旧 Markdown 到单块的确定性兼容。
2. 扩展检索切片模型和迁移，使文档切片记录 `source_block_id`，并保持旧切片可读。
3. 增加块级内容与结构保存服务/API，返回结构化 409 冲突详情；补充权限和并发测试。
4. 更新前端 payload 类型和序列化逻辑，构建多块编辑器及块级错误定位。
5. 更新管理页保存与冲突流程，支持不同块并行语义、同块对比和结构冲突刷新。
6. 更新上传解析，使普通文档按标题生成块预览且无标题内容不丢失。
7. 运行知识库后端测试、前端契约测试和 `npm run build`。
8. 使用标准本地四服务启动脚本验证 API、Worker、MCP、前端及固定 LLM 超时配置。
9. 在真实页面完成桌面和移动视口的新增、编辑、复制、排序、删除、保存和冲突路径验收，保存并检查截图和水平溢出。
10. 将检查结果和未完成风险写入任务记录；若形成可复用约束，更新 `.trellis/spec/`。
11. 参考目录/正文模式，将多块折叠列表收敛为左侧目录和右侧单一活动块编辑器；补充选择状态契约并重新执行桌面、移动端浏览器验收。
12. 精简编辑抽屉，移除知识类型切换、文档级元数据和源文件替换入口；验证隐藏字段保存时仍保持原值。
13. 将标题编辑入口移动到左侧知识块目录，右侧详情只保留检索状态和 Markdown 正文；补充桌面、移动端和保存契约验收。
14. 去除 Markdown 正文编辑器的输入框和聚焦边框，保留原有编辑、自动高度和保存逻辑。
15. 统一知识块操作按钮为项目风格的紧凑方形图标按钮，移除 `circle` 椭圆/圆形描边样式并验收桌面、移动端布局。

## 实施记录（2026-08-12）

- [x] 普通知识文档 payload 升级为稳定 `blocks[] + structure_revision`，旧 `markdown` 读取时确定性迁移为一个正文块，保存后不再双写旧字段。
- [x] 块级内容保存按 `block_revision` 检测冲突；结构保存按 `structure_revision` 检测冲突；409 返回服务端块或结构快照。
- [x] 发布按启用知识块边界切片，`knowledge_base_chunk.source_block_id` 可追踪来源块，并透传到检索引用、预览和语义上下文快照。
- [x] 前端支持知识块新增、复制、上下移动、启停、删除、折叠和目录导航；同块冲突支持本地/服务端对比、载入服务端及本地重试。
- [x] 文件替换按 Markdown 标题生成新块结构并递增结构版本。
- [x] 本次改动文件 Ruff 检查通过；`git diff --check` 通过。
- [x] 后端知识库测试（排除已知基线失败 `test_knowledge_base_management_api.py`）154 passed、7 skipped；最终状态机与审计回归 18 passed。
- [x] 前端知识库契约测试 19 passed；`npm run build` 通过。
- [x] Alembic 图解析为单一 head `156knowledgedocblock`。
- [x] 块内容与结构保存写入租户隔离操作审计，记录文档、版本、操作人、操作类型和受影响块 ID，并与草稿修改同事务提交。
- [x] 隔离四服务验收：前端 5179、API 8005、MCP 8006 和 Worker `local-DONGJINCHAO-chat-bi_ver` 均运行；固定 LLM 配置为 120/900/1。
- [x] 参考站点布局调整：目录保持展示全部块，详情区只挂载活动块；新增、复制自动选中新块，排序按 ID 保持选择，删除选择相邻块。
- [x] 桌面和 390x844 窄屏验收：根页面无水平溢出，窄屏抽屉为 100% 宽，目录可横向滚动且详情区只渲染一个知识块。
- [x] 双标签并发验收：不同块依次保存无冲突；同块后提交返回本地/服务端对比，本地正文保留；测试正文已恢复。
- [x] 精简编辑抽屉：知识类型切换、数据源绑定、标签、物理对象引用和替换源文件入口已移除；序列化契约证明隐藏元数据保持原值。
- [x] 标题编辑已移动到左侧目录的铅笔按钮，检索状态位于块头部，右侧正文表单只保留 Markdown 内容；标题弹窗取消不改数据，保存继续使用原块级并发流程。
- [x] 最新前端契约测试 20 passed，生产构建通过；桌面与 390x844 实际页面验收无水平溢出。
- [x] 验收截图保存在 `evidence/document-editor-directory-detail-desktop.png`、`evidence/document-editor-directory-detail-mobile.png` 和 `evidence/document-editor-trimmed-controls-desktop.png`。
- [x] 知识块操作按钮统一为项目现有紧凑方形图标按钮：实际渲染为 `28x28px`、`6px` 圆角、无边框，悬停使用项目蓝色/危险红色反馈；桌面端及 `390x844` 移动端均无水平溢出并完成截图验收。
- [x] 移除知识块正文下方的“下载当前源文件”入口；源文件属于整份文档版本，统一从版本历史行下载，避免误认为是当前知识块的文件。

## 已知基线问题

- 全量 `test_knowledge_base_*.py` 中 `test_knowledge_base_management_api.py` 有两个与本次改动无关的既有失败：测试遍历到不含 `path` 的 `_IncludedRouter`；LEGACY phase 的当前能力状态返回 `UPGRADING` 而旧断言期待 `LEGACY`。

## 重点验证

- `backend/.venv/Scripts/python.exe -m pytest` 运行知识库相关测试。
- `node --test` 运行知识库前端契约测试。
- `npm run build`。
- `git diff --check`。
- `tools/stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`，并独立检查 5173。

## 风险文件与回滚点

- `backend/apps/knowledge_base/schemas.py`：公共 payload 契约，必须保持旧 payload 解析。
- `backend/apps/knowledge_base/lifecycle_service.py` 与 `version_repository.py`：并发事务边界。
- `backend/apps/knowledge_base/chunking.py`：发布和 RAG 引用一致性。
- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.vue`：已有用户工具栏修改，局部编辑且不覆盖。
- 数据库迁移只允许增加可空列，禁止清理历史版本或切片。
