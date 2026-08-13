# 实施计划

- [x] 保存合并前 Git 证据和用户未提交文件清单（28 条 porcelain 记录，16 个顶层状态项）。
- [x] stash 全部已跟踪/未跟踪改动并验证工作区干净（OID `c806e018312f5c8d2beb526feb211cb14f383116`）。
- [x] 同步本地源分支至 `origin/release/release_1.0.0` 最新提交 `85c1b049`。
- [x] 合并源分支到目标分支并逐个解决 8 个实际冲突。
- [x] 检查自动合并的 SQL 执行、日期配置、工作空间切换和种子入口。
- [x] 运行冲突相关后端测试、前端测试、前端构建和 Python 语法检查。
- [x] 使用中文信息创建 merge commit `cbbec0e4`，并验证双父提交与祖先关系。
- [x] 恢复用户 stash；合并期间新增的两项并发知识库编辑也已保留并通过测试。
- [x] 运行 Trellis 检查、记录 `check.md`，核验最终工作区。
- [x] 独立检查固定 merge commit，修复活动看板 seed 中动态数据源解析后的残留常量引用，并补充运行时回归测试。

## Conflict Decisions

- `custom_prompt.py`: 保留 2.0 的类型写法，加入 1.0 的租户级平台 Skill 排除能力。
- `llm.py`: 同时保留知识库上下文注入和日期参数禁用指引。
- `dashboard_date_filter.py`: 保留 2.0 显式 `date_filter` 契约及实时表处理，加入 start-only token 与当天自定义范围修复，不恢复旧 pivot 兼容兜底。
- `sql_permission.py`: 保留 2.0 语义对象权限解析，并加入 `SqlSchemaScopeError` 支持。
- `test_platform_sql_data_skill_migration.py`: 保留 2.0 离线 SQL 测试并加入 153-159 迁移规则测试。
- `datasourceContext.ts`: 保留 2.0 移除旧缓存回退的决策，并加入 1.0 工作空间切换事务隔离。
- 两个 SLG dashboard seed: 合并语义纪元、schema hash、数据源解析及兼容环境导出。

## Post-Merge Review Fix

- 独立检查发现 `tools/seed_slg_bi_activity_dashboard.py` 已移除固定 `DATASOURCE_ID`，但 `sync_datasource_field_metadata(...)` 仍有 4 处残留引用，实际运行会触发 `NameError`。
- 修复为全程使用调用方传入的动态 `datasource_id`，覆盖数据源查询、schema hash 刷新和 semantic epoch 更新。
- 新增 `backend/tests/test_slg_seed_catalog_epoch_wiring.py` 运行时回归，验证动态数据源 ID 一致传递。
- 修复提交：`ac1c25e34b33e894dcec6d7781d86691da33356f`。

## Validation Commands

```powershell
git diff --diff-filter=U --name-only
git show --no-patch --format="%H%n%P%n%s" HEAD
git merge-base --is-ancestor 85c1b049 release/release_2.0.0
python -m compileall <changed-python-files>
pytest <conflict-related-test-selection>
node --test <conflict-related-frontend-tests>
git status --short --branch
```

## Rollback Points

- merge commit 前：`git merge --abort`，随后恢复 stash。
- stash 恢复前：记录 merge commit 和 stash OID，确保两份状态均可追溯。
