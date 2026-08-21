# 修复知识源文件跨工作树丢失

## Goal

让共享同一应用数据库的本地 linked worktree 使用稳定、统一的知识源文件目录，避免上传或重新发布后因切换 API/Worker 工作树导致下载 404；下载确实失败时，用户必须看到可操作的中文原因，而不是空 `{}`。

## Background

- 平台知识库“业务术语”版本 34 已发布，但数据库引用的 `.knowledge-stage-766be5fef95d4094b11cf047ba12c23c.md` 在现有工作区均不存在，下载接口返回 404。
- “事件参数对照_通用”的源文件也已丢失；“通用模板-事件参数对照”的源文件仍存在于主 checkout 的 `.codex-runtime/file`。
- 本地 API、Worker 和多个 linked worktree 共享 `10.1.5.28/zhishu_bi_2.0.0`，当前启动脚本却把 `UPLOAD_DIR` 等目录绑定到各自 worktree 的 `.codex-runtime`。
- 重新发布只更新版本状态和索引，不会重新创建原始上传文件。
- 下载接口的 404 错误体以 Blob 返回，当前前端未解析 Blob 中的 JSON，最终只显示空 `{}`。

## Requirements

1. `tools/backend-local.ps1`、`tools/worker-local.ps1` 和同类本地启动入口必须为 `UPLOAD_DIR`、`EXCEL_PATH`、`MCP_IMAGE_PATH` 解析同一个稳定共享目录。
2. 在 linked worktree 中，共享目录应落到 Git common dir 所属主 checkout 的 `.codex-runtime`；日志、PID、队列和其他进程运行状态继续保留在当前 worktree，避免不同开发栈互相接管。
3. 非 linked worktree 或 Git common dir 无法解析时，启动脚本继续使用当前 workspace 的 `.codex-runtime`，且不得切换到旧本地系统数据库或其他隐式存储位置。
4. API 与 Worker 必须使用相同的文件目录解析规则，避免上传、异步发布和下载跨进程不一致。
5. 前端公共请求层应能从 Blob 错误响应中提取现有后端错误消息；知识库下载入口必须捕获失败并展示明确中文提示，不产生未处理 Promise。
6. 当后端报告知识源文件不存在时，用户提示应说明需要重新上传源文件后再发布。
7. 不得用规范化内容、数据库正文或空文件伪造原始上传文件，也不得将重新发布改成静默恢复文件。
8. 修复应补充针对目录契约和下载错误反馈的回归测试，并通过前端构建与真实浏览器点击验证。

## Acceptance Criteria

- [x] 从 linked worktree 启动 API 和 Worker 时，二者的 `UPLOAD_DIR`、`EXCEL_PATH`、`MCP_IMAGE_PATH` 均解析到主 checkout 的 `.codex-runtime` 对应目录。
- [x] 当前 worktree 的日志、PID 和本地任务队列仍保持隔离，不因共享文件目录而互相覆盖。
- [x] 使用主 checkout 中仍存在的知识源文件，通过实际页面下载按钮可以成功下载。
- [x] 对已丢失源文件的知识版本点击下载时，页面展示“知识源文件不存在，请重新上传源文件后再发布”或等价明确提示，不显示 `{}`，控制台没有未处理 Promise。
- [x] 聚焦脚本测试、前端下载行为测试、类型检查/构建全部通过。
- [x] 运行中的 5174/8002 开发环境已重启或核对，并确认实际使用共享文件目录。
- [ ] 变更以中文提交信息提交，并推送/合入 `release/release_2.0.0`，不包含无关用户改动。

## Out Of Scope

- 自动恢复任务开始时已经物理丢失的原始 Markdown 文件；用户已在运行时重新上传 ID 27，ID 26 仍需重新提供原件。
- 引入对象存储或多机共享存储；本次只修复同一台开发机上的 linked worktree。
- 改变知识发布、版本状态、索引生成或权限规则。
