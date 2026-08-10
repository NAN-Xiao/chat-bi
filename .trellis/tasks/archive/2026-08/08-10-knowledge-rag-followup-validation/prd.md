# 完成知识库 RAG 遗留验证

## Goal

修复独立 worktree 测试路径污染，核对并处理已授权验收临时知识造成的迁移未回填记录，完成只读门禁复核。

## Requirements

- 使用当前独立 worktree 的后端模块执行测试，禁止因 `PYTHONPATH` 或已安装路径污染导入 `D:\AIWork3\chat-bi`。
- 核对 `legacy_backfill_remaining=1` 对应的具体旧知识记录；只有确认属于本轮已授权创建的验收临时知识库时才清理。
- 保留 `knowledge_retrieval_log` 与 `semantic_context_audit`，不得删除管理员或用户创建的业务知识。
- 仅执行迁移 `status` 和 `verify --compatible-builds-confirmed`；不得执行回填、屏障、切换、回退或批量删除命令。
- 主工作区用户未提交改动保持原样。

## Acceptance Criteria

- [ ] 后端测试明确从当前 worktree 导入模块，并记录全量或可解释的验证结果。
- [ ] 未回填旧知识的 ID、来源和是否属于临时验收数据已查明。
- [ ] 安全范围内的临时数据清理完成，审计记录仍可查询。
- [ ] 迁移只读门禁重新执行，剩余阻塞项有准确结论。
- [ ] Trellis 记录完成，分支提交并推送。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
