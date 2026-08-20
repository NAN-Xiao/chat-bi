# 提交工作空间代码到 release 2.0.0

## Goal

整理当前工作空间中尚未进入远端 release/release_2.0.0 的相关 worktree 提交与文档代码，合并到独立发布分支，完成冲突处理、验证并推送。

## Requirements

- 以远端 `origin/release/release_2.0.0` 为整合基线，不覆盖或重置用户已有改动。
- 盘点当前本地 worktree 分支相对该基线的独有提交，识别与知识库、模板、通用平台能力相关且可进入 2.0.0 的提交。
- 在本任务专用链接 worktree 中按依赖顺序合并选定提交；冲突必须按当前代码职责处理，不使用强制覆盖。
- 对当前主检出的未提交文件单独判断：属于本次工作空间交付的才纳入，无法确认归属的保留在原检出并在交付报告说明。
- 完成必要的前端测试、构建、差异检查和最终分支状态核对。
- 提交使用中文信息并推送当前发布整合分支；如远端拒绝或出现未解决冲突，停止并报告具体原因。

## Acceptance Criteria

- [ ] 远端 2.0.0 基线未被改写，所有合并都发生在专用链接 worktree。
- [ ] 选定的工作分支提交已合入，未选定分支及其原因有记录。
- [ ] 合并后工作区无未解决冲突，测试/构建与 `git diff --check` 通过。
- [ ] 已生成中文提交并成功推送，报告提交哈希、分支、worktree 路径及仍保留的无关改动。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
