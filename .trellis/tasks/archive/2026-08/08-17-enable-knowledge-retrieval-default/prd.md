# 默认开启知识库检索

## Goal

知识库发布完成且当前上下文满足权限、适用性和索引要求时，Smart Q&A、分析助手等运行时默认使用知识库结构化上下文和向量召回结果；保留显式关闭能力，便于回滚或灰度排障。

## Background / Confirmed Facts

- `Settings.KNOWLEDGE_RUNTIME_CONTEXT_ENABLED` 和 `Settings.KNOWLEDGE_RETRIEVAL_ENABLED` 当前默认值为 `False`。
- 本地 API、MCP 和 Worker 启动脚本会显式写入这两个环境变量；当前未传启用开关时会写入 `false`，因此仅修改 Python 默认值不能改变标准本地启动行为。
- 运行上下文开关控制结构化知识注入，检索开关控制知识块向量召回；二者职责独立，不能合并为一个开关。
- 现有知识库权限、数据源适用性、发布版本和 embedding 校验逻辑保持不变。

## Requirements

- 将两个 Settings 默认值改为 `True`。
- 将标准本地 API、MCP、Worker 和 stack 编排默认设置改为 `true`，并保留显式 `false` 环境变量/命令行关闭路径。
- 为运行脚本增加与现有管理 V2 一致的显式关闭参数；启用和关闭同时指定时必须报明确冲突错误。
- 更新当前运行规范和相关测试，使默认开启与显式关闭行为可验证；不修改归档任务中的历史决策记录。
- 不改变知识检索的权限过滤、相似度阈值、Top-K、上下文长度或知识块切分规则。

## Out Of Scope

- 不修改知识库召回算法、embedding 模型、权限边界、数据源选择或结构化知识内容。
- 不自动修改已有部署环境中的显式环境变量；显式 `false` 仍具有最高优先级。
- 不启动或重启本地服务作为代码变更的一部分；完成后按验证要求检查配置和相关测试。

## Acceptance Criteria

- [x] 在不提供两个知识库开关环境变量时，新建 `Settings` 实例得到两个值均为 `True`。
- [x] 显式设置任一开关为 `false` 时，该开关解析为 `False`，另一个开关不被隐式改变。
- [x] 标准本地 API、MCP、Worker 启动脚本和 stack 编排在无关闭参数时向进程传递 `true`。
- [x] 对 API、MCP、Worker 和 stack 传入对应关闭参数时向进程传递 `false`；启用/关闭冲突时失败并给出明确错误。
- [x] 现有知识库相关测试及新增默认/显式关闭回归测试通过，且 `ruff` 检查受影响 Python 文件无新增问题。
- [x] 当前运行规范不再声称运行时上下文和检索默认关闭，并记录关闭开关作为回滚方式。

## Key Decisions / Risks

- 采用“默认开启、显式关闭回滚”的方式，确保配置默认值与标准本地编排行为一致；代价是服务启动后会开始执行知识库上下文和向量检索，可能增加 embedding/数据库调用，需依赖现有权限、适用性和失败告警路径观察。
- 保持两个开关独立，允许仅关闭结构化上下文或仅关闭向量检索。

## Planning Status

- Lightweight task: PRD plus implementation log.
- Approved and implemented; focused verification completed.
