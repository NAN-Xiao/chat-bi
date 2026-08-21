# Check Log

- 冲突相关后端测试：141 passed。
- 合并涉及的 27 个后端测试文件：598 passed。
- 前端 Node 测试：13 个文件，17 passed。
- `npm run build`：通过，包含 `vue-tsc -b` 和 Vite 构建；仅有既有导入与大
  chunk 告警。
- Python 冲突文件 `py_compile`：通过。
- `git diff --check`：通过。
- Alembic `heads`：仅 `165mergerelease1into2 (head)`。
- Flam 与修仙种子脚本定向回归：61 passed。
- 全部变更 Python 文件 Ruff `F821` 检查：通过。
- 全量 Ruff 报告 317 项源分支既有格式、旧式注解及未使用参数等问题；未在
  本次合并中做大范围机械格式化。合并暴露的两处 `F821` 已修复并回归。
- `git diff --cached --check`：通过；无未合并路径，合并源为
  `949c3c84`。提交后按预期基线校验本地主 checkout，再以纯快进方式更新目标
  分支。
