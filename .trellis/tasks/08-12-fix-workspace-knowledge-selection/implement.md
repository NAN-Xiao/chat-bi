# Implementation Plan

1. 加载 `trellis-before-dev` 与前端相关规范，确认顶部工作空间筛选器和创建请求模式。
2. 删除 V2 创建弹窗内重复的工作空间表单项。
3. 确保工作空间知识创建请求始终复用页面顶部已选工作空间，并在缺少选择时明确阻止提交。
4. 增加前端静态回归测试覆盖弹窗字段移除、工作空间绑定和范围切换。
5. 使用 `trellis-check` 运行相关测试、前端构建，重启或确认本地四服务状态。
6. 通过浏览器真实创建路径验证桌面与移动视口，保存并检查截图与水平溢出。
7. 将根因、修复和验证结果写入任务记录；如形成可复用约束，更新 `.trellis/spec/`。

## Risky Files

- `frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.vue`

## Validation Commands

- 在 `frontend/` 运行知识库创建回归测试。
- 在 `frontend/` 运行 `npm run build`。
- `./tools/stack-local.ps1 -Action status -BackendPorts 8000 -StartMcp -SkipDatabase -SkipRedis -SkipNginx`
- 独立检查 `5173` 监听并通过浏览器验证实际创建流程。
