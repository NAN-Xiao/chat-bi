# 合并检查记录

## Git

- Merge commit: `cbbec0e4bed4116cd450fcbc71e56f826039a61c`
- Parents: `9cf8c07c5afe4f58041563266408429a1d8fdb68` / `85c1b04943134c37d70c5bac934c3d7fc33f01e3`
- `git merge-base --is-ancestor 85c1b049 HEAD`: 通过
- 未合并索引、冲突标记、`git diff --check`: 通过
- 未 push。

## Passed Checks

- 合入的 81 个 Python 文件 `py_compile`: 通过。
- 平台 SQL Data Skill 迁移测试: 22 passed。
- 租户级平台 Skill 排除: 4 passed。
- 相关子查询与 schema scope 权限: 3 passed。
- dashboard 当天自定义范围与 SLG seed 定向测试: 15 passed。
- 工作空间切换前端测试: 16 passed。
- 图表/分析助手前端定向测试: 8 passed。
- 恢复现场后的知识库行操作与布局测试: 13 passed。
- `npm run build`: 通过（仅既有 chunk/dynamic import 警告）。
- 独立 Trellis 全范围检查：完成；发现并修复 1 个活动看板 seed 合并缺陷，无其他可执行合并缺陷。
- 活动看板动态数据源回归：6 passed。
- 相关 SLG seed 定向测试：14 passed。
- 修复文件 `py_compile`、`diff --check`：通过。
- 修复后重新确认源提交 `85c1b049` 与 merge commit `cbbec0e4` 均为当前 HEAD 祖先；无未合并路径或冲突标记。

## Known Test Contract Differences

- 一组跨分支聚合测试运行结果为 99 passed / 53 failed。失败主要来自源分支旧测试继续通过 pivot 调用 2.0 已明确移除的日期兼容路径，以及 SQLite 夹具未创建 2.0 的 `semantic_object_reference` 表。
- 未为通过旧断言而恢复静默兼容。源侧新增功能已由上述精确测试覆盖。
- 独立检查再次运行混合日期套件为 235 passed / 18 failed；18 项仍属于 1.0 旧 pivot/realtime 日期断言与 2.0 显式 `date_filter` 契约冲突。
- Backend mypy 未能启动：当前环境缺少 mypyc 模块 `0aca9ce3d91742c5b361__mypyc`，且系统未安装 `uv`。前端 `vue-tsc`/build 已通过。
- 冲突文件整体 Ruff 有 77 项既有基线告警；本次后续修复文件 Ruff 通过，未混入无关格式清理。

## Post-Merge Defect Fixed

- Root cause: 冲突解决将活动看板 seed 改为运行时解析数据源，但元数据同步函数仍引用已删除的固定 `DATASOURCE_ID` 常量。
- Fix: 4 处引用全部改为函数参数 `datasource_id`，并增加真实调用路径回归测试。
- Commit: `ac1c25e34b33e894dcec6d7781d86691da33356f`。

## Stash Recovery

- 原始 stash `c806e018...` 无冲突应用，`frontend/src/router/index.ts` 用户修改已恢复。
- 合并期间另有知识库 Vue 和测试并发编辑，使用第二个保护 stash `fc9bd048...` 保存；最终工作树同时保留原始归档/恢复改动和后续行操作改动，相关 13 项测试与前端构建通过。
