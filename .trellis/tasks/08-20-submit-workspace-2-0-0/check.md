# 整合检查记录

## 分支与范围

- 基线：`origin/release/release_2.0.0`，整合分支：`codex/submit-workspace-2.0.0`。
- 独立链接 worktree：`D:\AIWork3\chat-bi_ver-worktrees\submit-workspace-2.0.0`。
- 已纳入未合入基线的代码/文档提交：SSR Jenkins 安装修复、知识库草稿状态修复、修仙业务知识文档及相关任务记录。
- 归档布局、知识块滚动旧提交的运行时代码已在 2.0.0 基线中有等价更新，未重复覆盖。
- 主检出菜单修复通过可恢复 Git 对象取回并以文件级补丁应用；外部 pull/reset 后无法恢复的二进制模板和未跟踪模板未伪造。

## 待执行验证

- [ ] 受影响 Node 契约测试
- [ ] SSR 构建契约测试
- [ ] 前端生产构建
- [ ] 文档/SQL 静态检查
- [ ] `git diff --check`

## 实际结果

- [x] Node 知识库契约测试：28/28 通过。
- [x] Jenkins SSR 构建契约测试：3/3 通过。
- [x] `git diff --cached --check` 通过后完成提交。
- [ ] 前端生产构建：未通过，当前整合 worktree 缺少完整依赖安装；使用外部依赖路径运行 `vue-tsc` 时暴露仓库既有全量类型解析错误，未归因于本次变更。
- [x] 未纳入远端 2.0.0 的整合提交已创建，等待推送。
