# Implementation Plan

## Implementation

- [x] 将后端 Embedding 默认批量大小改为 10。
- [x] 将批量大小加入安装配置、安装模板和 Jenkins 运行环境生成链路。
- [x] 新增 Embedding 客户端批量切分、输出顺序和显式覆盖测试。
- [x] 新增部署配置传播契约测试。

## Local Verification

- [x] 运行新增的 Embedding 与部署配置测试。
- [x] 运行知识库发布器测试，确认发布批处理与失败传播没有回归。
- [x] 运行受影响 Python 文件的 Ruff 检查。
- [x] 运行相关后端测试集合。

## `.193` Verification

- [x] 记录当前容器镜像和 API/Worker 状态。
- [x] 将修复配置部署到 `.193` 测试容器，API 和两个 Worker 使用同一运行配置。
- [x] 核对 `EMBEDDING_BATCH_SIZE=10`、数据库、Redis 与队列配置。
- [x] 使用默认模型执行 23 条输入的真实 Embedding 冒烟测试。
- [x] 重试 `事件参数对照_通用` 发布并观察任务、Worker 日志及数据库最终状态。
- [x] 确认不存在新的批量大小 HTTP 400。

## Quality And Record

- [x] 使用 `trellis-check` 完成质量门禁并记录结果到 `check.md`。
- [x] 将根因、修复和验证结果写入任务记录；可复用运行契约写入 backend spec。

## Rollback Point

- 代码回滚：恢复配置默认值与部署变量传播改动。
- `.193` 回滚：恢复验证前记录的镜像和运行环境，重新创建 API/Worker 容器并检查健康状态。
