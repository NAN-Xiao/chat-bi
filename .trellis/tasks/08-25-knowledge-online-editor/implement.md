# 知识库在线文档编辑器实施清单

1. 安装并锁定 Tiptap Vue、StarterKit、Markdown 及现有 Markdown 结构所需扩展。
2. 新增知识库专用 Markdown 富文本组件，支持只读、外部 Markdown 同步、用户更新和精简命令暴露。
3. 重构 `DocumentEditor.vue` 为目录、精简工具栏和连续文档画布；实现单活动编辑器及全部块结构操作。
4. 将 `KnowledgeBaseV2Panel.vue` 的正文抽屉改为同页全屏编辑模式，重新编排生命周期、上传、冲突和历史版本区域。
5. 实现串行防抖自动保存、服务端 revision 合并、`flushPendingSave()`、保存状态和离开保护。
6. 保持现有校验、发布、冲突、权限、归档、恢复、删除、上传、下载和回滚 API 调用不变，并补充状态回归测试。
7. 更新知识库前端契约测试；新增 Markdown 无修改不回写、精简工具栏、单编辑器、自动保存响应合并和移动布局测试。
8. 运行知识库 Node 测试、`npm run build`、`git diff --check`，并检查依赖锁文件。
9. 用标准本地四服务脚本启动隔离 worktree；核对 `LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。
10. 浏览器验收平台/工作空间知识库：打开编辑、切块、富文本修改、自动保存、结构操作、冲突、校验、发布前置保存、历史版本、只读和返回。
11. 在桌面和 `390x844` 检查页面级水平溢出、顶部操作溢出、目录/工具栏滚动和文本遮挡，保存并人工检查截图。
12. 将实际修改、验证结果、已知风险和恢复方式写回 Trellis 任务；若形成可复用约束，更新前端或知识库 spec。

## Validation Commands

- `node --test frontend/src/views/knowledge-base/*.test.mjs`
- `npm run build`（在 `frontend` 目录）
- `git diff --check`
- `./tools/stack-local.ps1 -Action restart -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`
- `./tools/stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`
- `Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue`

## Risky Files And Rollback Points

- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.vue`：列表与生命周期状态集中，必须避免编辑模式影响筛选和权限。
- `frontend/src/views/knowledge-base/editors/DocumentEditor.vue`：知识块选择、结构操作和画布布局中心。
- 新富文本组件及 Markdown 适配模块：必须证明未编辑内容不写回、受支持内容往返稳定。
- `frontend/package.json`、`frontend/package-lock.json`：依赖变更仅限 Tiptap 编辑能力。
- 自动保存逻辑：任何响应都不能覆盖请求期间产生的本地输入；失败必须保持可见且可重试。

## Implementation Log

- 引入 Tiptap Vue、StarterKit、官方 Markdown 和表格解析扩展，新增 Markdown 输入输出组件；外部内容同步不触发更新事件。
- 文档编辑器改为左侧目录、精简工具栏和全部块连续画布；只挂载一个活动编辑器，保留新增、重命名、复制、排序、启停和删除。
- 知识库面板改为列表/全页编辑两种页面模式；正文不再使用 `760px` 抽屉，版本历史保留为辅助抽屉。
- 新增 `clean / dirty / saving / conflict / error` 自动保存状态机和 `flushPendingSave()`；保存响应通过纯函数合并 revision，保留请求期间的新输入和排序。
- 校验、发布、返回和 `Ctrl+S` 统一等待自动保存；冲突或错误阻止后续动作。
- 未修改后端 API、payload、数据库、发布任务或 RAG 路径。
- 知识文档画布局部禁用右键上下文菜单，移除内置浏览器显示的“Quick annotate/评论/Copy/检查”菜单；键盘复制和其他页面右键行为保持不变。

## Verification Summary

- 知识库 Node 测试：38 passed，0 failed。
- `npx vue-tsc -b --pretty false`：通过。
- `npm run build`：通过，仅有既有动态导入和大 chunk 警告。
- 新增/重写文件定向 ESLint：通过；`KnowledgeBaseV2Panel.vue` 关闭既有 Prettier 规则后语义 ESLint 通过，该文件在任务前已不满足全文件 Prettier 格式。
- `git diff --check`：通过。
- 当前工作树前端 `http://127.0.0.1:5173/` 返回 200；现有 API 返回 401、MCP 根路径返回 404，证明端点可达；模型超时配置输出 `120 900 1`。
- 浏览器被未登录状态重定向到登录页，Chrome 会话不可用，因此无法完成知识编辑真实点击、桌面/移动截图及溢出检查。
- 当前 `8000/8001` 属于另一个活动 linked worktree，且本工作树缺少独立 `backend/.venv`；未终止或冒充该栈，当前任务的四服务独立启动未完成。
