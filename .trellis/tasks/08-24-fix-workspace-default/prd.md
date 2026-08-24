# 修复登录后默认工作空间为空

## Goal

TBD.

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
# 修复登录后默认工作空间为空

## 需求

普通用户登录且请求未指定工作空间时，应自动进入其有效成员关系中的默认工作空间。默认空间由现有 `is_primary` 排序决定；不能因为指定空间无效或无权限而静默切换到其他空间。

## 验收标准

- 登录未携带工作空间 ID 时，后端返回主工作空间的 `tenant_id`、`tenant_name` 和角色。
- 没有主标记但只有一个有效工作空间时，自动进入该空间。
- 没有任何有效工作空间时，仍返回 `workspace_required`，不伪造空间上下文。
- 登录或切换明确指定无权限空间时，继续返回权限错误，不回退到其他空间。
- 前端继续以 `/user/info` 返回的空间作为当前上下文，不在 `loadTenants` 中盲选第一条。
- 增加后端回归测试覆盖默认解析和显式无权限场景。
