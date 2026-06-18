# 单租户生产可用基线

这份基线面向“一个客户/一个组织独立部署”的生产形态，不等同于云上多租户 SaaS。

## 必须完成

- 稳定入口：Nginx 统一暴露 `80/443`，后端只监听内网 `127.0.0.1:8000`。
- Redis：生产必须启用 `CACHE_TYPE=redis`，配置密码、AOF、内存上限和 `noeviction`。
- 任务队列：worker 独立进程运行；任务使用 Redis pending/processing 队列，worker 中断后由超时恢复机制重投。
- 数据库备份：PostgreSQL 至少每天全量备份，保留 7-14 天，并每次上线前确认恢复命令可用。
- 日志监控：`LOG_LEVEL=INFO`，关闭 `SQL_DEBUG`，Nginx、API、worker、Redis、PostgreSQL 日志都纳入采集。
- 密钥管理：`SECRET_KEY`、数据库密码、Redis 密码、模型 API Key 不得使用开发默认值，不得提交到 Git。
- 权限边界：普通用户不能看到未授权数据源、连接配置、其他用户任务、其他用户对话。
- 安全基线：登录限流、上传大小限制、上传/下载路径校验、统一 5xx 异常脱敏、CORS 不允许未知来源、生产禁用默认密码接口。
- 依赖漏洞：上线前必须通过前端 `npm audit --omit=dev` 和后端 `pip-audit`，不得带已知高危生产依赖漏洞上线。

## 当前检查状态

截至 2026-06-18，本轮已经补齐：

- 后端依赖漏洞已升级并回归：`pip-audit --path backend/.venv/Lib/site-packages` 返回 `No known vulnerabilities found`。
- 前端生产依赖审计已通过：`npm audit --omit=dev` 返回 `found 0 vulnerabilities`。
- 密码存储已从新写入 MD5 改为 bcrypt；旧 MD5 密码仍可登录一次，并在认证成功后自动重写为 bcrypt。
- 数据源连接配置和大模型 `api_key/api_domain` 新写入时使用服务端版本化 Fernet 加密；旧固定 AES 密文仍可读取。
- 生产配置检查要求 `SENSITIVE_CONFIG_ENCRYPTION_KEY`、`SECRET_KEY`、数据库密码、Redis 密码等从环境变量提供，且不能使用开发默认值。
- 生产配置检查覆盖 Redis、任务队列、CORS、默认密码、登录限流、上传大小和绝对路径。
- 登录失败限流支持 Redis，开发环境可回退进程内存；生产仍要求 `CACHE_TYPE=redis`。
- 全局异常处理隐藏 5xx 内部错误细节，并补充基础安全响应头。
- ASK token 和 embedded token 不再信任未验签 payload 中的关键身份字段。
- Excel/CSV 上传统一限制扩展名、文件名和最大大小，下载错误文件限制在指定目录内。
- 仪表盘富文本渲染使用 DOMPurify；搜索高亮先转义 HTML，并转义正则关键字。
- 生产环境不再暴露 `/user/defaultPwd`。

代码侧不再有已知阻断项。真正上线前仍必须在目标机器完成一次现场验收：

- Nginx TLS 证书、域名、反向代理和静态资源路径验收。
- PostgreSQL 备份文件实际生成，并恢复到非生产库成功。
- 多 backend 副本通过 Nginx 轮询，Redis 共享缓存和限流状态正常。
- worker 故障后，超时任务能恢复到 pending 或最终 failed。
- 日志采集、告警接收人、磁盘空间和备份保留策略确认。

## 生产启动前检查

在 `backend` 目录执行：

```bash
APP_ENV=production python scripts/production_check.py
```

生产环境中 `PRODUCTION_CHECKS_ENABLED=true` 时，API 启动也会自动执行同一套检查；不满足要求会直接启动失败。

## 推荐配置文件

- 环境变量模板：`deploy/env.production.example`
- Redis 模板：`deploy/redis/redis.production.conf.template`
- Nginx 模板：`deploy/nginx/nginx.production.conf.template`
- systemd API：`deploy/systemd/zhishu-api.service`
- systemd API 多副本：`deploy/systemd/zhishu-api@.service`
- systemd worker：`deploy/systemd/zhishu-worker.service`
- systemd worker 多实例：`deploy/systemd/zhishu-worker@.service`

## 备份恢复

当前本地已有 Windows 备份脚本：`tools/postgres-backup-local.ps1`。生产 Linux 上建议使用 `pg_dump -Fc`：

```bash
pg_dump -h 127.0.0.1 -p 5432 -U zhishu -d zhishu_bi -Fc -f /data/backups/zhishu_bi_$(date +%F_%H%M%S).dump
```

恢复演练必须在非生产库执行：

```bash
pg_restore -h 127.0.0.1 -p 5432 -U zhishu -d zhishu_bi_restore --clean --if-exists /data/backups/zhishu_bi_YYYY-MM-DD_HHMMSS.dump
```

验收标准：

- 备份命令退出码为 `0`，备份文件大小非 `0`。
- 恢复库可连接，核心表存在，管理员账号和数据源配置可查询。
- 恢复演练记录包含备份文件名、恢复库名、执行时间、执行人和结果。

## 多副本/worker 演练

单机生产可以先跑 2-3 个 API 副本和 1-2 个 worker。示例：

```bash
systemctl start zhishu-api@8000
systemctl start zhishu-api@8002
systemctl start zhishu-worker@1
systemctl start zhishu-worker@2
```

也可以继续使用固定单副本服务：

```bash
systemctl start zhishu-api
systemctl start zhishu-worker
```

验收动作：

- Nginx upstream 至少配置两个 backend，`/ready` 连续访问都返回 `200`。
- `CACHE_TYPE=redis`，`/ready` 中 cache 状态为 `ok`。
- 创建一个 `system.ping` 任务，worker 能消费并返回 `succeeded`。
- 在任务 running 时停掉 worker，超过 `TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS` 后，新 worker 能恢复任务或按最大重试次数标记失败。
- 停掉任意一个 backend 副本，Nginx 仍能把请求转到其他健康副本。

## 上线验收

- `GET /health` 返回 `200`。
- `GET /ready` 返回 `200`，且 cache 为 Redis `ok`。
- `GET /api/v1/system/tasks/health` 由系统管理员访问时返回 pending/processing/registered tasks。
- 停掉一个 worker 后，超时任务能恢复到 pending 或最终 failed。
- 普通用户无法访问未授权数据源、连接配置、其他用户任务。
- 依赖审计无生产阻断漏洞。
- `APP_ENV=production python scripts/production_check.py` 返回 `Production settings check passed.`
- 管理员新建或更新数据源/大模型配置后，数据库中对应敏感字段以 `fernet:v1:` 开头。

## 暂不纳入

- 云上多租户租户模型。
- 对象存储。
- 数据库上云。
- Kubernetes / Helm。
- 自动定时备份编排。
