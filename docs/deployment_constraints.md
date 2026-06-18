# 部署与高可用约束

## 当前阶段

开发环境保持简单：默认单个 backend、一个本地 PostgreSQL、一个本地 Redis、可选 Nginx。

生产方向保持可扩展：同一套代码必须支持 Nginx 入口、backend 多副本、Redis 共享状态、后续任务队列。

当前优先目标是“单租户生产可用”，不是云上多租户 SaaS。生产模式必须显式设置
`APP_ENV=production`，并通过 `backend/scripts/production_check.py` 的启动前检查。

## 已落地

- Redis 应用侧基础接入：统一 client、连接池、健康检查、分布式锁工具。
- `/health` 和 `/ready`：提供给 Nginx 或负载均衡做探活。
- Nginx 本地配置：默认代理单副本 `8000`，也支持 `8000,8002,8003`。
- 后端本地启动脚本：默认开发单副本，多端口时启用多副本。
- 任务队列第一版：Redis 队列、任务状态、worker 启动入口、`system.ping` 测试任务、字段同步和 embedding 刷新任务。
- 本地一键编排脚本：`tools/stack-local.ps1` 串联 PostgreSQL、Redis、backend、Nginx 和 worker。
- 本地 PostgreSQL 备份/恢复脚本：`tools/postgres-backup-local.ps1`，默认备份到 `.codex-runtime/pg-backups`。
- 单租户生产配置模板：`deploy/env.production.example`、`deploy/redis/redis.production.conf.template`、
  `deploy/nginx/nginx.production.conf.template` 和 `deploy/systemd/`。

## 暂不做

- 对象存储暂不做，后续多机器部署或文件规模上来后再引入。
- 数据库上云暂不做，本地阶段必须保留自动备份和恢复预案。
- 当前已有手动备份/恢复脚本，自动定时备份后续再接 Windows 计划任务或生产备份策略。
- Docker 暂不作为当前路径依赖，Windows 本地继续使用原生进程和 Nginx zip 版。

## 开发与生产的分界

开发默认：

```text
frontend 5173
backend 8000
PostgreSQL 15432
Redis 6379 可选
Nginx 8080 可选
```

生产/压测目标：

```text
Nginx 80/443
backend 8000/8002/8003
PostgreSQL
Redis
worker 任务队列
```

开发环境不要强制复杂化；生产能力通过配置、脚本和共享状态设施打开。

本地开发默认仍使用单副本：

```powershell
.\tools\stack-local.ps1 -Action start
```

多副本压测或上线前模拟再显式开启：

```powershell
.\tools\stack-local.ps1 -Action start -BackendPorts 8000,8002,8003 -StartWorker -Workers 2
```

当前已有业务动作依赖任务队列，`stack-local.ps1` 默认启动 1 个 worker；只有明确不测试队列时才使用 `-SkipWorker`。

## 多副本约束

- 多副本 backend 必须尽量无状态。
- 用户、权限、助手、数据源等共享缓存不能只放进进程内存；多副本应使用 Redis。
- 多副本启动应顺序启动，或生产环境单独执行迁移后再启动副本，避免多个实例同时执行 Alembic 迁移。
- 上传目录、Excel 目录、图片目录当前仍是本地目录；单机多副本可以共享，多机部署前必须改成共享存储或对象存储。
- MCP 服务目前仍按单实例处理，除非后续明确做 MCP 多副本。

## Redis 约束

第一阶段 Redis 只放适合短期共享状态的数据：

- 登录/权限/助手等元数据缓存。
- 限流计数。
- 任务状态。
- 分布式锁。
- 数据源 schema 和语义层元数据缓存。

暂不做大规模业务查询结果缓存，避免旧数据和权限串数据风险。

## 任务队列约束

任务队列已经有基础设施，当前已迁移单表字段同步、表/数据源 embedding、术语 embedding、SQL 示例 embedding。后续优先拆：

- Excel/CSV 导入。
- 数据源探查和批量选表同步。
- 语义层全量 embedding 重建入口。
- 推荐问题生成。
- 长时间分析任务。

接口模式应变成提交任务返回 `task_id`，worker 后台执行，前端查询状态和结果。

第一版队列要求：

- worker 必须使用 Redis。
- 任务状态保存在 Redis，默认保留 24 小时。
- worker 通过 pending/processing 两级队列领取任务；worker 中断后，超出
  `TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS` 的任务可恢复或最终失败。
- 不向普通用户开放任意任务投递能力；业务接口应只投递白名单任务。
- 任务 payload 不保存敏感明文密钥。
- 现有字段同步任务只传 `table_id`，worker 从系统库读取数据源配置，不把数据源密码写入 Redis payload。
