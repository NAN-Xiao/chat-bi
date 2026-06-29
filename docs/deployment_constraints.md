# 部署与高可用约束

## 当前阶段

开发环境保持简单：默认单个 backend、一个本地 PostgreSQL、一个本地 Redis、可选 Nginx。

生产方向保持可扩展：同一套代码必须支持 Nginx 入口、backend 多副本、Redis 共享状态、独立 worker 和按租户隔离的业务资产。

当前优先目标是 B2B 多租户高可用基线。生产模式必须显式设置 `APP_ENV=production`，
并通过 `backend/scripts/production_check.py` 的启动前检查。

## 已落地

- Redis 应用侧基础接入：统一 client、连接池、健康检查、分布式锁工具。
- `/health` 和 `/ready`：提供给 Nginx 或负载均衡做探活。
- Nginx 本地配置：默认代理单副本 `8000`，也支持 `8000,8002,8003`。
- 后端本地启动脚本：默认开发单副本，多端口时启用多副本。
- 任务队列第一版：Redis 队列、任务状态、worker 启动入口、`system.ping` 测试任务、字段同步和 embedding 刷新任务。
- 租户级高消耗接口限流：ChatBI 问答、分析助手和推荐问题按租户共享 Redis 计数，超限返回 `429` 或 SSE `error` 事件。
- 租户日用量计量与套餐配额：`sys_tenant_usage_daily` 按租户/日期/指标累计 ChatBI、分析助手、任务队列、Token 和失败次数；`TENANT_USAGE_QUOTA_PLAN_LIMITS` 可按套餐配置 daily/monthly 上限，超额返回 `quota_exceeded`。
- 人工商业化订阅状态：`sys_tenant` 保存 `subscription_status`、服务期、试用期、合同编号和商务联系人。`past_due` 和服务期到期只作为运营跟进状态，不自动停服；只有 SaaS 管理员人工设置 `suspended` 或 `cancelled` 后，ChatBI 生成、分析助手和任务入队等高消耗能力才会被拦截。
- 租户生命周期请求：`sys_tenant_data_request` 支持租户注销、数据导出、数据删除的提交、SaaS 审核、完成记录。审核通过或完成记录本身不自动停用租户、不自动删除数据；SaaS 管理员必须按线下/运维清单执行后手动标记。
- 企业邮箱域：`sys_tenant_domain` 支持企业提交邮箱域，SaaS 管理员审核为 `verified` 后，同域邮箱用户登录或 token 校验时可自动加入对应租户；`pending/disabled` 域不会自动归属。
- 租户安全策略：`sys_tenant_security_policy` 支持 IP 白名单、强制 SSO 标记和会话超时配置。当前强制 SSO 先按登录来源拦截本地账号，完整 SSO IdP 配置仍待后续实现；SaaS 管理员为运维支持绕过租户级 IP/SSO 策略。
- 成员准入增强：企业管理员可批量邀请已有账号，每个账号返回独立结果，并写入租户审计日志，方便后续成员变更追溯。
- 本地一键编排脚本：`tools/stack-local.ps1` 串联 PostgreSQL、Redis、backend、Nginx 和 worker。
- 本地 PostgreSQL 备份/恢复脚本：`tools/postgres-backup-local.ps1`，默认备份到 `.codex-runtime/pg-backups`。
- 生产 PostgreSQL 定时备份：`deploy/scripts/zhishu-postgres-backup.sh` 结合
  `deploy/systemd/zhishu-postgres-backup.service` 和 `deploy/systemd/zhishu-postgres-backup.timer`，
  使用 `pg_dump -Fc` 生成备份并按保留天数清理。
- 生产日志轮转：`deploy/logrotate/zhishu` 覆盖应用日志、Nginx 访问/错误日志和 Redis 日志，
  防止单机多副本运行时磁盘被日志写满。
- 生产配置模板：`deploy/env.production.example`、`deploy/redis/redis.production.conf.template`、
  `deploy/nginx/nginx.production.conf.template` 和 `deploy/systemd/`。
- 多租户运行边界：`sys_tenant/sys_tenant_user` 提供企业和成员关系；数据源、语义层、ChatBI 对话、看板、API Key、自定义助手、审计日志和用量计量均带租户范围；企业 owner/admin 可管理本租户项目、语义层和公开自定义 Agent。
- 数据源 Excel/CSV 临时导入文件按租户目录保存，避免共享临时目录被跨租户文件名引用。
- 生产数据库迁移拆分：启动默认不自动迁移；生产必须 `AUTO_RUN_MIGRATIONS=false`，通过
  `python -m scripts.db_migrate` 或 `zhishu-migrate.service` 在 API 副本启动前单独执行一次。

## 暂不做

- 对象存储暂不做，后续多机器部署或文件规模上来后再引入。
- 数据库上云暂不做，本地阶段必须保留自动备份和恢复预案。
- Windows 本地自动定时备份暂不做；需要时再接 Windows 计划任务。生产 Linux 已提供 systemd timer。
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
- 当前租户上下文必须来自已验证的登录 token、API Key 或 embedded assistant token；普通请求不能通过 header 任意切换到未授权租户。
- 查询、看板、分析助手、推荐问题和自定义 Agent 必须先验证当前租户和数据源授权，再读取 schema、语义层或执行 SQL。
- 高消耗接口限流必须使用租户维度共享计数，避免某个租户在多 API 副本下绕过单进程限额。
- 多副本下用量计量和套餐配额必须写入共享系统库，不依赖进程内存；生产必须保持
  `TENANT_USAGE_METERING_ENABLED=true` 和 `TENANT_USAGE_QUOTA_ENABLED=true`，数据库迁移必须先创建 `sys_tenant_usage_daily`。
- 欠费或服务期到期不能由程序自动停服；只能由 SaaS 管理员审核后手动把租户订阅状态切换为 `suspended` 或 `cancelled`。`past_due` 租户仍可继续使用高消耗功能，除非同时触发套餐配额上限。
- 租户注销、数据导出、数据删除请求必须走 SaaS 管理员审核；请求完成状态只是审计记录，不能由 API 副本自动清理业务表或自动停用租户。
- 邮箱域自动归属只认 SaaS 已验证域名；多副本下该归属关系写入系统库，不依赖单进程内存。
- 租户 IP 白名单和 SSO 强制策略必须在所有 API 副本上通过共享系统库读取，不能用本地配置分叉。
- 生产环境禁止 API 副本启动时自动执行 Alembic 迁移；生产配置检查会拒绝
  `AUTO_RUN_MIGRATIONS=true`。迁移必须作为发布步骤单独执行一次，再启动或滚动重启 API 副本。
- 上传目录、Excel 目录、图片目录当前仍是本地目录；单机多副本可以共享，多机部署前必须改成共享存储或对象存储。
- MCP 服务目前仍按单实例处理，除非后续明确做 MCP 多副本。

## Redis 约束

第一阶段 Redis 只放适合短期共享状态的数据：

- 登录/权限/助手等元数据缓存。
- 限流计数。
- 任务状态。
- 分布式锁。
- 数据源 schema 和语义层元数据缓存。

生产环境必须开启 `TENANT_RATE_LIMIT_ENABLED=true`，并按套餐或部署规模配置：

- `TENANT_CHAT_REQUESTS_PER_MINUTE`
- `TENANT_ANALYSIS_REQUESTS_PER_MINUTE`
- `TENANT_RECOMMEND_REQUESTS_PER_MINUTE`
- `TENANT_LLM_REQUESTS_PER_MINUTE`

租户表已有 `plan` 字段。第一版商业套餐通过 `TENANT_RATE_LIMIT_PLAN_OVERRIDES` 覆盖不同套餐限额，
例如 `default/basic/enterprise` 分别配置不同的 ChatBI、分析助手和推荐问题每分钟请求数。
未配置或无法识别的 plan 会回退到全局限额。

套餐级日/月用量通过 `TENANT_USAGE_QUOTA_PLAN_LIMITS` 配置，基于 `sys_tenant_usage_daily` 中的聚合指标判断。
第一版支持 `chat`、`analysis`、`recommend`、`task` 四类 quota：

```json
{
  "default": {
    "daily": {"chat": 100, "analysis": 20, "recommend": 100, "task": 200},
    "monthly": {"chat": 2000, "analysis": 400, "recommend": 2000, "task": 5000}
  }
}
```

暂不做大规模业务查询结果缓存，避免旧数据和权限串数据风险。

## 任务队列约束

任务队列已经有基础设施，当前已迁移单表字段同步、表/数据源 embedding。后续优先拆：

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
- 多租户部署必须配置 `TASK_QUEUE_MAX_PENDING_PER_TENANT` 和
  `TASK_QUEUE_MAX_PROCESSING_PER_TENANT`，防止单一租户积压大量任务或占满全部 worker。
- 不向普通用户开放任意任务投递能力；业务接口应只投递白名单任务。
- 任务 payload 不保存敏感明文密钥。
- 现有字段同步任务只传 `table_id`，worker 从系统库读取数据源配置，不把数据源密码写入 Redis payload。
