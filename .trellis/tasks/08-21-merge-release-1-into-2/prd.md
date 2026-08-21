# 合并 release 1.0.0 到 release 2.0.0

## Goal

将 release/release_1.0.0 合并到 release/release_2.0.0，解决跨版本冲突、迁移分叉并完成回归验证。

## Requirements

- 将 `origin/release/release_1.0.0` 的提交历史完整合并到以
  `origin/release/release_2.0.0` 为基线的任务分支。
- 解决文本冲突时保留 2.0 的权限、数据源隔离和显式日期契约，合入 1.0
  的跨库/跨 Schema 校验及通用能力。
- 合并后的 Alembic 迁移图只能有一个 head。
- 不引入静默兼容兜底，不覆盖主 checkout 的用户改动，不推送远端。

## Acceptance Criteria

- [x] 所有 Git 冲突已解决，暂存区无未合并路径或冲突标记。
- [x] Smart Q&A 日期配置和 SQL 权限等跨版本契约已统一。
- [x] Alembic 分叉通过 merge revision 汇合。
- [x] 后端测试、前端测试、构建及静态检查完成并记录。
- [x] 创建中文合并提交，并将本地目标分支安全推进到该提交。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
