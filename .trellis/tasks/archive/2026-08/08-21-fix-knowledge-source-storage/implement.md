# 实施计划

1. 为本地启动脚本增加稳定共享运行目录解析，并分别接入 API、Worker、独立开发启动入口。
2. 扩展 `tests/test_stack_local_script.py` 或同层契约测试，验证共享文件目录和私有进程运行目录的边界。
3. 在前端请求层解析 Blob 错误响应，在知识库下载入口捕获并展示明确反馈。
4. 扩展知识库下载行为测试，覆盖成功下载、缺失源文件提示和 busy 状态复位。
5. 运行聚焦 Python/Node 测试、前端 lint/type-check/build，并检查 PowerShell 语法。
6. 重启或核对当前 8002 API 与 5174 前端，输出实际环境目录；通过真实页面分别验证现存文件下载成功和丢失文件提示。
7. 更新前后端运行规范与 Trellis 实施/检查记录。
8. 使用中文提交信息提交当前任务变更，并安全推送/合入 `release/release_2.0.0`。

## 重点验证命令

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_stack_local_script.py
node --test frontend/src/views/knowledge-base/KnowledgeBaseV2Panel.row-actions.test.mjs
cd frontend; npm run build
```

具体 lint、类型检查命令以 `frontend/package.json` 的现有脚本为准。

## 风险与回滚点

- 共享目录解析只影响文件型运行数据；若测试发现进程状态被共享，立即回滚该变量并修正目录分类。
- 不执行数据库修改或自动文件迁移。
- 提交前重新检查主分支和任务分支状态，避免纳入其他 worktree 的用户变更。

## 实施记录

- 根因类别：隐式假设与跨层契约。共享数据库保存文件引用，但 linked worktree 的 API/Worker 曾分别使用私有上传目录；同时 Axios Blob 错误未解码，导致 UI 显示空对象。
- 根因修复：三个本地启动入口统一调用 `Resolve-SharedRuntimeRoot`，只共享文件型产物；前端请求层统一解码 Blob 错误，知识库下载入口负责操作性提示。
- 防复发：新增 PowerShell 目录契约测试、下载错误静态回归测试、前后端 runtime spec，并要求真实点击同时覆盖存在文件 200 与缺失文件提示。
- 已知数据状态：知识库 26/27 的原始文件在任务开始时已经物理丢失；用户随后重新上传 ID 27 并成功发布/下载，ID 26 仍需重新上传，代码未做伪造恢复。
