# 检查记录

## 已通过

- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_knowledge_base_retrieval.py backend/tests/test_knowledge_base_state_machine.py backend/tests/test_knowledge_base_management_api.py backend/tests/test_knowledge_base_workspace_management.py backend/tests/test_knowledge_base_publish.py -q`：60 passed。
- `frontend` 知识库契约测试 `node --test src/views/knowledge-base/*.test.mjs`：36 passed。
- `npm run build`：`vue-tsc -b` 与 Vite production build 通过。
- Ruff 定向检查：通过。
- `git diff --check`：通过。
- `http://127.0.0.1:5173/`：200；现有 API `8000`、MCP `8001` 和前端 `5173` 均监听。
- 本次分支 API 验证启动时核对：`LLM_REQUEST_TIMEOUT=120`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

## 未通过或受环境限制

- 全量后端测试：1567 passed、39 failed、8 skipped。失败集中在日期过滤、仪表盘数据源/租户绑定和旧 SQLite 字段，未命中本次知识库改动；本次涉及的 60 条定向测试全部通过。
- Mypy 无法启动：共享虚拟环境的 mypyc 模块损坏，报 `ModuleNotFoundError: No module named '0aca9ce3d91742c5b361__mypyc'`。
- 浏览器真实知识库页：当前登录令牌由既有 `8000` 进程的随机密钥签发，无法在分支 API 上复用；未读取浏览器存储、伪造令牌或输入未知凭据，因此只完成了页面启动与根路径健康检查，未伪装为已完成登录后截图验收。

## 行为核对

- V2 列表和编辑抽屉已移除“参与检索”开关及 `setActive` 调用。
- V2 `PUT /knowledge-base/{id}/active` 路由和生命周期服务方法已移除。
- 向量候选只按当前 `PUBLISHED` 版本、当前版本指针和未归档条件过滤；历史 `active=false` 不再阻断召回。
- 发布成功和归档恢复会同步 `active=true`，归档仍置为 `false`，仅用于历史数据一致性。
