# 修复知识库发布 Embedding 批量上限

## Goal

让已通过校验的知识文档能够在 `10.1.5.193` 测试环境完成发布，避免默认 Embedding 批量大小超过 `text-embedding-v4` 服务上限而在 `EMBED` 阶段失败。

## Background

- 知识库 `事件参数对照_通用` 的发布任务 32、33、34 均在 `EMBED` 阶段失败。
- `.193` 的两个 Worker 原始日志显示 `text-embedding-v4` 返回 HTTP 400：单批输入数量不得超过 10。
- 当前应用默认 `EMBEDDING_BATCH_SIZE=32`，`.193` 的运行配置没有覆盖该值。
- `.193` API 与两个 Worker都使用 `TASK_QUEUE_NAME=default`、同一系统数据库和 Redis；任务确实由这两个 Worker 执行。因此 `default` 是该部署的预期共享队列，不是本次失败根因。

## Requirements

- 将通用 Embedding 默认批量大小从 32 调整为保守的 10，仍允许部署环境显式覆盖。
- Jenkins 运行环境生成、安装配置和安装模板必须显式传播同一个批量大小，避免部署依赖隐式代码默认值。
- `OpenAICompatibleEmbeddings` 必须按配置批量切分输入，并保持输出数量和顺序不变。
- 不增加针对某个模型名或业务知识库的硬编码分支，不通过关闭 Embedding、跳过索引或静默重试掩盖错误。
- 不改变生产型部署的 `default` 队列语义，也不修改本地 `local-*` 隔离队列规则。
- 修复后在 `10.1.5.193` 验证真实 Embedding 请求和知识库发布流程。

## Acceptance Criteria

- [ ] 默认 Embedding 配置解析为 `batch_size=10`。
- [ ] 23 条输入会发出 3 个请求，批量大小依次为 10、10、3，且返回向量顺序与输入一致。
- [ ] 显式配置的正整数批量大小仍被尊重。
- [ ] Jenkinsfile、`installer/install.conf` 和安装模板均包含 `EMBEDDING_BATCH_SIZE` 的显式传播。
- [ ] 相关单元测试、部署配置契约测试和静态检查通过。
- [ ] `.193` 的 API 与 Worker 运行配置均为 `EMBEDDING_BATCH_SIZE=10`。
- [ ] `.193` 真实发布任务不再出现批量大小 HTTP 400，目标版本最终进入 `PUBLISHED` 状态。

## Out Of Scope

- 修改 Markdown 分块规则或知识块内容。
- 修改任务队列实现、队列名称或 Redis 数据结构。
- 操作 `.28` 生产/Jenkins 主机或其他未指定环境。
