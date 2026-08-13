# 合并 release_1.0.0 到 release_2.0.0

## Goal

将远端最新 `origin/release/release_1.0.0` 的已提交改动完整合入当前目标分支 `release/release_2.0.0`，同时保留目标分支已有能力和当前工作区全部未提交改动。

## Background

- 当前分支为 `release/release_2.0.0`，与 `origin/release/release_2.0.0` 一致，当前提交为 `9cf8c07c`。
- `origin/release/release_1.0.0` 已更新至 `85c1b049`；本地同名分支仍停在 `4fa0c178`，合并应以远端最新提交为准并同步本地分支。
- 两个分支相对共同祖先已分叉：目标分支独有 117 个提交，源分支独有 156 个提交，因此必须生成 merge commit。
- 工作区存在 16 项未提交状态；其中 `frontend/src/router/index.ts` 同时被源分支修改，合并前必须保护全部已跟踪和未跟踪改动，合并后原样恢复。
- `git merge-tree` 预检发现 8 个内容冲突：
  - `backend/apps/chat/curd/custom_prompt.py`
  - `backend/apps/chat/task/llm.py`
  - `backend/apps/dashboard/crud/dashboard_date_filter.py`
  - `backend/apps/datasource/crud/sql_permission.py`
  - `backend/tests/test_platform_sql_data_skill_migration.py`
  - `frontend/src/stores/datasourceContext.ts`
  - `tools/seed_slg_bi_activity_dashboard.py`
  - `tools/seed_slg_bi_expedition_dashboard.py`

## Requirements

1. 合并源固定为 `origin/release/release_1.0.0` 的最新已获取提交，目标固定为当前 `release/release_2.0.0`。
2. 合并提交信息使用中文。
3. 冲突解决必须同时保留 2.0 分支的通用平台/知识库能力与 1.0 分支的缺陷修复；不得通过整文件选择单边版本静默丢弃另一边有效逻辑。
4. 当前工作区的已跟踪修改和未跟踪文件必须在合并前受保护，并在 merge commit 完成后恢复。
5. 不推送远端，除非用户另行明确要求。
6. 合并后不得残留冲突标记或未合并索引项。

## Acceptance Criteria

1. `release/release_2.0.0` 上存在一个父提交分别包含原目标提交 `9cf8c07c` 与源提交 `85c1b049` 的 merge commit。
2. `git merge-base --is-ancestor 85c1b049 release/release_2.0.0` 成功。
3. `git diff --diff-filter=U --name-only` 为空，代码中无本次合并遗留的冲突标记。
4. 合并前记录的用户未提交文件集合在合并后仍存在；`frontend/src/router/index.ts` 的用户修改被正确恢复且不覆盖合并结果。
5. 对 8 个冲突文件运行相关的定向测试或语法/静态校验，并记录无法执行的检查。
6. 最终报告 merge commit、冲突解决摘要、验证结果和未推送状态。

## Out Of Scope

- 不发布、不推送、不创建 PR。
- 不重构与冲突无关的代码。
- 不清理或提交用户当前未提交的知识库相关工作。
- 不启动本地四服务栈，除非验证暴露必须通过运行态复现的问题。

## Technical Notes

- 先用包含未跟踪文件的 Git stash 保护现场；确认 stash 创建成功后再合并。
- 更新本地 `release/release_1.0.0` 为远端最新的 fast-forward 指针，但保持目标分支检出。
- 使用 `--no-ff` 和中文提交信息执行合并；逐个审阅三方冲突，不采用未经审查的批量 `ours`/`theirs`。
- merge commit 完成后恢复 stash；若 stash 恢复冲突，继续解决但不把用户改动纳入 merge commit。
