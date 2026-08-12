# Implementation Plan

1. 加载 `trellis-before-dev` 与前后端相关规范，确认现有 API、权限和测试模式。
2. 扩展知识库创建请求契约及后端目标工作空间校验。
3. 调整统一知识库权限与列表可见范围，保证平台管理员创建后能继续管理，其他角色不越权。
4. 在 V2 创建弹窗增加工作空间选项、加载/空/错误状态和必选校验，保留现有工具栏改动。
5. 增加前端静态/组件回归测试和后端权限/API 回归测试。
6. 使用 `trellis-check` 运行相关测试、前端构建，重启或确认本地四服务状态。
7. 通过浏览器真实创建路径验证桌面与移动视口，保存并检查截图与水平溢出。
8. 将根因、修复和验证结果写入任务记录；如形成可复用权限约束，更新 `.trellis/spec/`。

## Risky Files

- `backend/apps/knowledge_base/permissions.py`
- `backend/apps/knowledge_base/api/_helpers.py`
- `backend/apps/knowledge_base/api/management.py`
- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.vue`

## Validation Commands

- `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_knowledge_base_permissions.py backend/tests/test_knowledge_base_management_api.py`
- 在 `frontend/` 运行新增知识库创建回归测试。
- 在 `frontend/` 运行 `npm run build`。
- `./tools/stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`
- 独立检查 `5173` 监听并通过浏览器验证实际创建流程。
