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
- systemd worker：`deploy/systemd/zhishu-worker.service`

## 备份恢复

当前本地已有 Windows 备份脚本：`tools/postgres-backup-local.ps1`。生产 Linux 上建议使用 `pg_dump -Fc`：

```bash
pg_dump -h 127.0.0.1 -p 5432 -U zhishu -d zhishu_bi -Fc -f /data/backups/zhishu_bi_$(date +%F_%H%M%S).dump
```

恢复演练必须在非生产库执行：

```bash
pg_restore -h 127.0.0.1 -p 5432 -U zhishu -d zhishu_bi_restore --clean --if-exists /data/backups/zhishu_bi_YYYY-MM-DD_HHMMSS.dump
```

## 上线验收

- `GET /health` 返回 `200`。
- `GET /ready` 返回 `200`，且 cache 为 Redis `ok`。
- `GET /api/v1/system/tasks/health` 由系统管理员访问时返回 pending/processing/registered tasks。
- 停掉一个 worker 后，超时任务能恢复到 pending 或最终 failed。
- 普通用户无法访问未授权数据源、连接配置、其他用户任务。

## 暂不纳入

- 云上多租户租户模型。
- 对象存储。
- 数据库上云。
- Kubernetes / Helm。
- 自动定时备份编排。
