# Quality Check

## Automated Verification

- 后端知识库测试：`161 passed, 7 skipped`。跳过项为需要显式隔离 PostgreSQL 的测试。
- 最终专项后端回归：`17 passed`。
- 修正 downgrade 空列语义后复测迁移、运行配置和管理 API：`16 passed`（仅既有依赖弃用警告）。
- Ruff `F/I`：通过。
- Alembic heads：唯一 head 为 `166removelegacykbstate`。
- 前端知识库测试：`37 passed`。
- Markdown 模板测试：`6 passed`。
- 前端 `npm run build`：通过，仅有既有 chunk size / dynamic import 警告。
- `git diff --check`：通过。

## Contract Verification

- 最终应用 router 不再注册 `POST /knowledge-base/save`。
- 任务注册表不再包含 `knowledge_base.process_document`，仍包含 `knowledge_base.publish_version`。
- `knowledge_base` 身份模型不再包含旧状态、任务和错误字段；版本与发布任务字段仍保留。
- list/delete 不再按 capability phase 分发到 legacy 实现；写操作仍受 V2 cutover/maintenance 安全门保护。
- 前端入口只渲染 V2 管理面板，页面与语言包不再展示“处理状态/待处理”。

## Browser Verification

- 运行页面：`http://127.0.0.1:5173/#/system/knowledge-base/platform`。
- 桌面 `1440x900` 与移动端 `390x844` 均完成真实页面检查。
- 两个视口均无页面级横向溢出，无“处理状态/待处理”，浏览器控制台无错误。
- 截图：`screenshots/knowledge-base-desktop.png`、`screenshots/knowledge-base-mobile.png`。

## Deployment Safety

- 未对共享系统数据库执行破坏性 migration。
- 临时 worktree API 验证后已停止；主工作区 API/MCP/Worker 未改动。
- `5173` 当前由任务 worktree 的 Vite 提供页面。
