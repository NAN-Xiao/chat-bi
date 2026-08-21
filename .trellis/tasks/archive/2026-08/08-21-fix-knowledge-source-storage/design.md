# 技术设计

## 边界与目录模型

保留两类运行数据：

- 工作树私有：日志、PID、队列标识、`BASE_DIR`、本地模型目录，继续位于 `<workspace>/.codex-runtime`。
- checkout 共享：上传文件、Excel 产物、MCP 图片，位于 `<main-checkout>/.codex-runtime/{file,excel,images}`。

启动脚本通过 `git rev-parse --path-format=absolute --git-common-dir` 获取 common Git 目录。linked worktree 返回主 checkout 的 `.git`，其父目录即共享运行数据根目录；普通 checkout 同样解析到自身。命令失败或结果不合法时，明确回退到当前 workspace，而不搜索其他目录。

## 启动入口

- `tools/backend-local.ps1` 与 `tools/worker-local.ps1` 使用同一解析逻辑和相同环境变量映射。
- `tools/dev-local.ps1` 是独立启动入口，也必须遵守相同共享文件目录契约。
- 不把整个 `.codex-runtime` 共享，以免多个工作树覆盖进程状态或日志。

## 下载错误数据流

1. 后端下载接口继续以现有错误码返回 404，不对丢失文件做静默补偿。
2. Axios 在 `responseType: 'blob'` 下将错误 JSON 放入 Blob。
3. 前端请求层异步解析 JSON/text Blob，将 `message`/`detail` 等字段传入既有错误格式化流程。
4. 知识库两个下载入口均捕获异常；对于源文件缺失，展示固定、可操作的中文提示，其他错误沿用解析后的后端消息。

## 兼容性与迁移

- 主 checkout 中已有文件无需迁移，修复后的 worktree 会直接访问它们。
- 只存在于其他 worktree 私有目录的文件不会自动移动，避免错误合并同名文件；需要单独确认后再迁移。
- 已丢失文件无法由代码恢复，用户需重新上传原件。

## 回滚

脚本和前端改动均可按文件回滚；没有数据库迁移和数据写入。回滚后 linked worktree 会恢复私有文件目录行为，但不会影响主 checkout 已有文件。
