# Technical Design

## Root Cause

`Settings.EMBEDDING_BATCH_SIZE` 默认值为 32。知识发布器读取模型配置并按该值分批，随后 `OpenAICompatibleEmbeddings` 发送 OpenAI 兼容请求。当前默认模型 `text-embedding-v4` 的服务端上限为每批 10 条，因此包含 255 个知识块的文档在第一批请求即收到 HTTP 400。

## Change Boundary

1. `backend/common/core/config.py` 将通用默认值改为 10。
2. `installer/install.conf` 声明 `SHUZHI_EMBEDDING_BATCH_SIZE=10`。
3. `Jenkinsfile` 校验该部署变量并写入运行环境文件。
4. `installer/shuzhi/templates/shuzhi.conf` 将安装配置传播为运行时 `EMBEDDING_BATCH_SIZE`。
5. 新增 Embedding 客户端批处理测试与部署配置传播测试。

## Runtime Flow

`installer/install.conf` -> Jenkins 生成 `chat-bi.runtime.env` -> API/Worker 使用同一 `EMBEDDING_BATCH_SIZE=10` -> `EmbeddingModelInfo.batch_size` -> `KnowledgePublisher` 和 `OpenAICompatibleEmbeddings` 按不超过 10 条切分 -> `text-embedding-v4` 返回向量 -> 发布落库并进入 `PUBLISHED`。

## Compatibility

- 环境变量仍可显式设置其他正整数，适配不同 OpenAI 兼容服务的能力。
- 不自动解析服务端错误并缩小批量，避免把错误配置变成静默降级。
- 队列配置不变；`.193` 的 `default` 继续作为 API 与 Worker 的共享队列。

## Remote Verification And Rollback

- 在 `.193` 构建或部署修复镜像前记录当前镜像 ID 和容器状态。
- 更新测试环境后确认 API/Worker 环境值、健康状态和 Worker 启动日志。
- 先执行 23 条文本的真实 Embedding 冒烟测试，再重试目标知识库发布。
- 若部署或发布验证失败，恢复当前镜像 `shuzhi:88-f4c1312b` 对应容器和原运行配置，不触碰数据库内容以外的发布状态机正常记录。
