# 知识库 RAG 上线与灰度运行手册

本文只描述知识库 V2 管理能力和运行时语义上下文的上线顺序。MCP 不在本手册范围内，默认保持 `MCP_ENABLED=false`。

## 一、发布前边界

- 管理和运行时能力均默认开启：`KNOWLEDGE_MANAGEMENT_V2_ENABLED=true`、`KNOWLEDGE_RUNTIME_CONTEXT_ENABLED=true`、`KNOWLEDGE_RETRIEVAL_ENABLED=true`。三个开关相互独立。
- 需要回滚管理页面时，部署环境显式设置 `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false`；本地脚本使用 `-DisableKnowledgeManagementV2`。关闭管理开关不会恢复旧版写入。
- 需要单独回滚结构化上下文或向量检索时，部署环境显式设置对应开关为 `false`；本地脚本分别使用 `-DisableKnowledgeRuntimeContext` 或 `-DisableKnowledgeRetrieval`。
- Skills 页面、个人空间 Skills、事件字典和数据字典原有写入逻辑不变。
- 共享环境不得直接修改数据库 phase；必须完成备份、回填、投影、双读和队列检查后再切换。
- 平台公共知识只能在消费工作空间当前绑定且授权的数据源中生效。

## 二、上线前检查

1. 确认所有 API、Worker 已包含 phase 屏障、发布作业认领和权限版本复核代码。
2. 确认存储探针当前 generation 可用，所有发布 Worker 使用同一配置指纹。
3. 执行知识库回填并确认剩余、失败记录均为零。
4. 确认已发布版本 `index_status=READY`，Skills 对象投影为最新状态。
5. 执行双读比对，确认旧解析结果与 V2 结果无差异。
6. 确认发布队列无逾期任务，数据库 publish job 与 Redis 任务状态可对账。
7. 运行后端知识库、权限、SQL、Smart Q&A、看板和综合分析回归，以及前端专项测试和构建。
8. 使用当前仓库的备份脚本创建数据库备份：

```powershell
.\tools\postgres-backup-local.ps1
```

备份必须位于 `.codex-runtime/pg-backups`，不得加入 Git。

## 三、phase 切换

在共享环境执行以下命令前，记录执行人、时间、版本、备份路径和回滚窗口：

先从部署清单取得全部活动发布 Worker 的 `worker-id` 和队列名。以下命令中的
`<worker-id>@<queue-name>` 必须覆盖全部活动发布 Worker，可重复传入 `--worker`；
`--compatible-builds-confirmed` 只能在 API 和 Worker 版本清单核对完成后使用：

```powershell
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py status --worker "<worker-id>@<queue-name>"
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py backfill --confirm-phase LEGACY_OPEN
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py verify --worker "<worker-id>@<queue-name>" --compatible-builds-confirmed
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py enter-barrier --worker "<worker-id>@<queue-name>" --compatible-builds-confirmed --confirm-phase LEGACY_OPEN
backend\.venv\Scripts\python.exe backend/scripts/knowledge_base_migrate.py activate-v2 --worker "<worker-id>@<queue-name>" --compatible-builds-confirmed --confirm-phase CUTOVER_BARRIER
```

验收结果：

- `verify` 必须返回 `ready_for_cutover=true`、零不一致、零待处理索引/投影任务，并确认兼容版本完整。
- `enter-barrier` 后新旧写入均返回中文提示“知识库升级中，请稍后重试。”，不得继续写入。
- `activate-v2` 后数据库 phase 为 `V2_ACTIVE`，旧 `/knowledge-base/save` 返回 HTTP 410 和中文提示“知识库已升级，请刷新页面后重新操作。”。
- `enter-barrier` 失败且数据库仍为 `CUTOVER_BARRIER` 时，可在确认未执行 `activate-v2` 后运行 `return-legacy --confirm-phase CUTOVER_BARRIER`；`V2_ACTIVE` 不允许通过该命令恢复旧写。

任一步骤失败都停止切换，不执行强制覆盖或重复激活。

## 四、管理与运行时能力验证

1. 先部署兼容版本，确认所有 API 实例和 Worker 均识别数据库 phase。
2. 确认 `KNOWLEDGE_MANAGEMENT_V2_ENABLED` 使用默认值 `true`（或部署环境显式设为 `true`），调用 `/api/v1/knowledge-base/capabilities`，确认 `management_mode=V2` 后再开放页面。
3. 确认 `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED` 和 `KNOWLEDGE_RETRIEVAL_ENABLED` 使用默认值 `true`（或部署环境显式设为 `true`），验证列表、四类编辑、草稿并发、校验、发布、下载、回滚、平台公共知识适用性和权限页面。
4. 使用已授权且存在 READY 发布版本的工作空间验证 Smart Q&A、AI 看板 SQL、综合分析助手和报告解读，确认结构化知识与知识块召回均遵守当前数据源和权限边界。
5. 在观察窗口持续关注发布失败、检索告警、适用性失败、权限拒绝、embedding 调用、SQL 校验失败和响应延迟；需要隔离问题时只关闭对应运行时开关。

运行时开关关闭时，AI 场景回到现有 tracking/Skill 逻辑，但不得降低数据库 phase、重新开放旧写入或删除 V2 数据。

## 五、回滚

- 管理页面异常：部署环境设置 `KNOWLEDGE_MANAGEMENT_V2_ENABLED=false`；本地脚本传入 `-DisableKnowledgeManagementV2`。保留数据库 phase 和已发布数据，排查后再开放。
- RAG 告警或回答回归：按影响范围将 `KNOWLEDGE_RUNTIME_CONTEXT_ENABLED` 或 `KNOWLEDGE_RETRIEVAL_ENABLED` 显式设为 `false`；本地分别使用 `-DisableKnowledgeRuntimeContext` 或 `-DisableKnowledgeRetrieval`。保留知识库管理和发布结果。
- 发布作业异常：依据数据库 `knowledge_publish_job` 状态处理，不直接删除 Redis 任务；使用失败阶段和心跳信息重试或人工恢复。
- 只有经过审批和备份确认，才允许执行数据库 phase 回退；回退必须使用迁移脚本，不得手工修改 phase 字段。

每次回滚记录影响工作空间、开关值、错误码、请求 ID、恢复时间和后续修复版本。

## 六、完成标准

- V2 页面只由服务端 capabilities 决定，升级中和维护态为只读中文页面。
- 四类知识可逐条编辑、校验、单条发布、下载、重新上传和回滚；并发冲突保留本地编辑内容。
- Smart Q&A、AI 看板 SQL、综合分析助手和报告解读使用统一权限/Schema/Skills/知识快照。
- 前端 1366x768、1440x900、1920x1080 无遮挡、溢出或抽屉底部操作区不可见。
- 所有用户可见错误为中文安全提示，不展示机器码、英文 HTTP 状态、异常类名、堆栈或物理路径。
