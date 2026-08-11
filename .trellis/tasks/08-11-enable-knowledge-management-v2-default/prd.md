# 默认开启知识库 V2 管理

## Goal

让数据库已进入 `V2_ACTIVE` 的环境默认开放知识库 V2 管理页面，避免普通启动命令把管理能力覆盖为维护态，同时保留可审计的显式关闭入口。

## Background

- `backend/common/core/config.py` 当前将 `KNOWLEDGE_MANAGEMENT_V2_ENABLED` 默认设为 `False`。
- `tools/backend-local.ps1` 与 `tools/worker-local.ps1` 在未传 `-EnableKnowledgeManagementV2` 时还会显式写入 `false`，因此只修改 Python 默认值不足以改变本地栈行为。
- 核心数据库当前处于 `V2_ACTIVE`；在该阶段关闭管理开关会按 capability 契约返回 `MAINTENANCE`，不会恢复旧版写入。
- 运行时语义上下文与检索开关是独立能力，不应随管理页面默认开启。

## Requirements

- `Settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED` 默认值改为 `True`，显式环境变量 `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false` 仍必须覆盖默认值。
- `tools/stack-local.ps1`、`tools/backend-local.ps1` 和 `tools/worker-local.ps1` 在普通启动或重启时必须让 API 与 Worker 一致启用管理 V2。
- 本地脚本必须保留显式关闭管理 V2 的回滚参数，且 API 与 Worker 不得出现开关不一致。
- 保持 `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=false` 与 `KNOWLEDGE_RETRIEVAL_ENABLED=false` 的默认行为不变。
- 更新受影响的配置/脚本回归测试以及 `docs/knowledge_base_rag_rollout_runbook.md`，使默认值、启动方式和回滚说明与实现一致。
- 不修改数据库 `knowledge_migration_state.phase`，不执行回填、迁移或数据清理。

## Out Of Scope

- 不默认开启 RAG 运行时上下文或检索。
- 不改变 capability 的 phase 判定矩阵。
- 不重新开放旧版知识库写入。
- 不修改远程、Jenkins 或生产环境。

## Acceptance Criteria

- [ ] 无环境变量覆盖时，`Settings(...).KNOWLEDGE_MANAGEMENT_V2_ENABLED is True`。
- [ ] 显式设置 `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false` 时配置解析结果仍为 `False`。
- [ ] 默认本地 API 与 Worker 环境都解析为 `KNOWLEDGE_MANAGEMENT_V2_ENABLED=true`。
- [ ] 使用显式关闭参数启动时，API 与 Worker 环境都解析为 `false`。
- [ ] runtime context 与 retrieval 默认值继续为 `false`。
- [ ] 相关 Python 与 PowerShell 脚本回归测试通过，运行手册不再描述管理 V2 为默认关闭。
- [ ] 在 `V2_ACTIVE` 数据库阶段，默认 capability 可进入 `management_mode=V2`；显式关闭时仍进入 `MAINTENANCE`。

## Notes

- 这是轻量配置变更，采用 PRD-only 规划。
- 优先保留现有 `-EnableKnowledgeManagementV2` 调用兼容性，并增加语义明确的显式关闭参数；实现时通过测试固定默认与回滚行为。
