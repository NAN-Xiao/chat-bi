# Implementation Log

- 创建 linked worktree
  `D:\AIWork3\chat-bi_ver-worktrees\merge-release-1.0.0-into-2.0.0`，任务分支为
  `codex/merge-release-1.0.0-into-2.0.0`。
- 执行 `git merge --no-ff origin/release/release_1.0.0`。
- 手工解决 dashboard、SQL 权限、埋点配置及相关测试的 5 个文本冲突。
- 统一 Smart Q&A 日期对象到独立 `date_filter` / `dateFilter` 契约，保留
  `configVersion: 2`，移除通用渲染器中的具体业务表名特判。
- 保留 2.0 权限快照、JSON 路径/事件权限和严格 datasource 隔离，同时合入
  1.0 的跨库与跨 Schema 限定校验。
- 删除两个合并后暴露的失效兼容分支，并以 revision
  `165mergerelease1into2` 汇合 Alembic 迁移链。
