# B2B 多租户高可用生产基线

这份基线面向 B2B 商业化 ChatBI 产品：同一套 SaaS 服务多个企业租户，核心目标是租户隔离、权限清晰、ChatBI 功能完整、可横向扩展、部署和运维友好。

当前仓库支持的生产形态是“共享系统库 + 租户级业务隔离 + 多 API 副本 + Redis 共享状态 + 独立 worker”。它可以用于单客户私有化部署，也可以作为多企业托管部署的第一阶段；所有新增业务能力都必须默认带 `tenant_id`、数据源授权和租户用量治理。

## 必须完成

- 稳定入口：Nginx 统一暴露 `80/443`，后端只监听内网 `127.0.0.1:8000`。
- Redis：生产必须启用 `CACHE_TYPE=redis`，配置密码、AOF、内存上限和 `noeviction`。
- 租户级限流：生产必须启用 `TENANT_RATE_LIMIT_ENABLED=true`，并为 ChatBI 问答、分析助手和推荐问题配置每分钟上限；可通过 `TENANT_RATE_LIMIT_PLAN_OVERRIDES` 按 `default/basic/enterprise` 等套餐覆盖限额，防止单个租户占满模型、数据库和 worker 资源。
- 租户用量计量与套餐配额：生产必须启用 `TENANT_USAGE_METERING_ENABLED=true` 和 `TENANT_USAGE_QUOTA_ENABLED=true`，并完成数据库迁移创建 `sys_tenant_usage_daily`，用于按天汇总 ChatBI、分析助手、任务队列、Token 和失败计数；可通过 `TENANT_USAGE_QUOTA_PLAN_LIMITS` 配置 `default/basic/enterprise` 等套餐的 daily/monthly 用量上限。
- 商业订阅状态：生产租户通过 `subscription_status`、服务期、试用期、合同编号和商务联系人进行人工运营管理。欠费或到期不得自动停服，必须由 SaaS 管理员审核后手动设置 `suspended` 或 `cancelled`，才会暂停 ChatBI 生成、分析助手和任务队列等高消耗能力。
- 租户生命周期与数据请求：租户注销、数据导出、数据删除必须走 `sys_tenant_data_request` 的提交、SaaS 审核、完成记录流程。完成记录不自动停用租户、不自动删除业务数据，SaaS 管理员需按运维清单手动执行。
- 企业域名与安全策略：企业邮箱域必须经 SaaS 管理员验证后才允许自动归属；租户级 IP 白名单和强制 SSO 策略必须在 tenant context 解析时执行。当前 SSO 强制登录基于用户登录来源拦截本地账号，完整 IdP 配置仍是后续项。
- 任务队列：worker 独立进程运行；任务使用 Redis pending/processing 队列，worker 中断后由超时恢复机制重投，并配置租户级 pending/processing 上限。
- 数据库备份：PostgreSQL 至少每天全量备份，保留 7-14 天，并每次上线前确认恢复命令可用。
- 日志监控：`LOG_LEVEL=INFO`，关闭 `SQL_DEBUG`，Nginx、API、worker、Redis、PostgreSQL 日志都纳入采集。
- 密钥管理：`SECRET_KEY`、数据库密码、Redis 密码、模型 API Key 不得使用开发默认值，不得提交到 Git。
- 权限边界：普通用户不能看到未授权数据源、连接配置、其他用户任务、其他用户对话。
- 多租户边界：所有企业资产必须按当前租户过滤，包括用户成员关系、数据源、语义层、ChatBI 对话、图表看板、自定义 Agent、分析助手、API Key、审计日志和用量计量。
- 企业自治：企业 `owner/admin` 可以管理本企业成员、项目数据源、公开 Data Skills 和公开自定义 Agent；普通成员只能使用授权项目，项目 viewer/editor 只影响项目使用和看板编辑，不等同于企业管理员。
- 安全基线：登录限流、上传大小限制、上传/下载路径校验、统一 5xx 异常脱敏、CORS 不允许未知来源、生产禁用默认密码接口。
- 依赖漏洞：上线前必须通过前端 `npm audit --omit=dev` 和后端 `pip-audit`，不得带已知高危生产依赖漏洞上线。

## 当前检查状态

截至 2026-06-18，本轮已经补齐：

- 后端依赖漏洞已升级并回归：`pip-audit --path backend/.venv/Lib/site-packages` 返回 `No known vulnerabilities found`。
- 前端生产依赖审计已通过：`npm audit --omit=dev` 返回 `found 0 vulnerabilities`。
- 密码存储已从新写入 MD5 改为 bcrypt；旧 MD5 密码仍可登录一次，并在认证成功后自动重写为 bcrypt。
- 数据源连接配置和大模型 `api_key/api_domain` 新写入时使用服务端版本化 Fernet 加密；旧固定 AES 密文仍可读取。
- 生产配置检查要求 `SENSITIVE_CONFIG_ENCRYPTION_KEY`、`SECRET_KEY`、数据库密码、Redis 密码等从环境变量提供，且不能使用开发默认值。
- 生产配置检查覆盖 Redis、任务队列、CORS、默认密码、登录限流、上传大小、绝对路径和生产 API 启动自动迁移禁用。
- 租户用量计量和套餐配额已加入生产配置检查；`/api/v1/system/tenant/usage` 可供 SaaS 管理员或企业管理员查看授权范围内的日聚合用量。
- SaaS 管理员租户管理页已支持维护套餐、订阅状态、服务期、试用期、合同编号、商务联系人和备注；`past_due` 仅作为运营跟进状态，不会自动停止服务。
- SaaS 管理员租户管理页已支持邮箱域审核、租户注销/数据导出/数据删除请求审核和完成记录；企业准入页支持邮箱域提交、租户级安全策略、数据请求提交和批量邀请。
- 企业 owner/admin 已纳入本租户数据源管理员、Data Skills 管理员和自定义 Agent 管理员模型；普通成员仍必须通过项目授权访问 ChatBI、看板和分析助手。
- 数据源 Excel/CSV 临时导入文件已按租户目录隔离，避免共享 `EXCEL_PATH` 下通过文件名跨租户引用临时文件。
- 登录失败限流支持 Redis，开发环境可回退进程内存；生产仍要求 `CACHE_TYPE=redis`。
- 生产 PostgreSQL 备份脚本与 systemd timer 已提供：`deploy/scripts/zhishu-postgres-backup.sh`、
  `deploy/systemd/zhishu-postgres-backup.service`、`deploy/systemd/zhishu-postgres-backup.timer`。
- 生产日志轮转配置已提供：`deploy/logrotate/zhishu`，覆盖 `/opt/zhishu/logs/*.log`、
  `/var/log/nginx/zhishu.*.log` 和 `/var/log/redis/zhishu-redis.log`。
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
- 配置 `TASK_QUEUE_MAX_PENDING_PER_TENANT` 和 `TASK_QUEUE_MAX_PROCESSING_PER_TENANT`，避免单个租户占满队列或 worker。
- 配置 `TENANT_CHAT_REQUESTS_PER_MINUTE`、`TENANT_ANALYSIS_REQUESTS_PER_MINUTE`、`TENANT_RECOMMEND_REQUESTS_PER_MINUTE` 和可选的 `TENANT_RATE_LIMIT_PLAN_OVERRIDES`，并确认不同套餐超过上限时接口返回 `429` 或 SSE `error` 事件。
- 确认 `TENANT_USAGE_METERING_ENABLED=true`、`TENANT_USAGE_QUOTA_ENABLED=true`，并在产生一次 ChatBI、分析助手或任务队列调用后，`sys_tenant_usage_daily` 中出现对应租户的日聚合记录；将测试租户套餐限额调低后，超额请求应返回 `quota_exceeded`。
- 验证一个测试租户的邮箱域从 `pending` 到 `verified` 后，同域邮箱用户登录会自动加入该租户；`disabled` 域不会再自动归属。
- 验证租户 IP 白名单会阻止非白名单来源，强制 SSO 会阻止本地账号；SaaS 管理员仍能进入租户管理和审核流程。
- 验证租户注销、数据导出、数据删除请求从提交到审核到完成均有审计记录，且完成后不会自动停用租户或自动删除业务表。
- 日志采集、告警接收人、磁盘空间和备份保留策略确认。

## 生产启动前检查

在 `backend` 目录执行：

```bash
APP_ENV=production python scripts/production_check.py
```

生产环境中 `PRODUCTION_CHECKS_ENABLED=true` 时，API 启动也会自动执行同一套检查；不满足要求会直接启动失败。

生产环境必须设置 `AUTO_RUN_MIGRATIONS=false`。数据库迁移作为发布步骤单独执行一次，不能由每个 API 副本在启动时自动执行：

```bash
APP_ENV=production python -m scripts.db_migrate
```

推荐发布顺序：

1. 先生成 PostgreSQL 备份并确认备份文件有效。
2. 执行 `APP_ENV=production python scripts/production_check.py`。
3. 执行 `APP_ENV=production python -m scripts.db_migrate`。
4. 滚动启动或重启 API 副本和 worker。

## 推荐配置文件

- 环境变量模板：`deploy/env.production.example`
- Redis 模板：`deploy/redis/redis.production.conf.template`
- Nginx 模板：`deploy/nginx/nginx.production.conf.template`
- logrotate 模板：`deploy/logrotate/zhishu`
- systemd API：`deploy/systemd/zhishu-api.service`
- systemd API 多副本：`deploy/systemd/zhishu-api@.service`
- systemd 数据库迁移：`deploy/systemd/zhishu-migrate.service`
- systemd worker：`deploy/systemd/zhishu-worker.service`
- systemd worker 多实例：`deploy/systemd/zhishu-worker@.service`
- systemd PostgreSQL 备份：`deploy/systemd/zhishu-postgres-backup.service`
- systemd PostgreSQL 定时器：`deploy/systemd/zhishu-postgres-backup.timer`

## 备份恢复

本地 Windows 可继续使用 `tools/postgres-backup-local.ps1`。生产 Linux 使用
`deploy/scripts/zhishu-postgres-backup.sh`，默认从 `/etc/zhishu/zhishu.env` 读取数据库连接信息。
先确认环境变量中已配置：

```bash
BACKUP_DIR=/var/backups/zhishu/postgres
BACKUP_RETENTION_DAYS=14
PG_DUMP_BIN=pg_dump
PG_RESTORE_BIN=pg_restore
```

部署时安装脚本和 timer：

```bash
install -o root -g root -m 0755 deploy/scripts/zhishu-postgres-backup.sh /opt/zhishu/deploy/scripts/zhishu-postgres-backup.sh
install -o root -g root -m 0644 deploy/systemd/zhishu-postgres-backup.service /etc/systemd/system/zhishu-postgres-backup.service
install -o root -g root -m 0644 deploy/systemd/zhishu-postgres-backup.timer /etc/systemd/system/zhishu-postgres-backup.timer
install -o zhishu -g zhishu -m 0700 -d /var/backups/zhishu/postgres
systemctl daemon-reload
```

手动生成一次备份：

```bash
systemctl start zhishu-postgres-backup.service
systemctl status zhishu-postgres-backup.service --no-pager
ls -lh /var/backups/zhishu/postgres
```

确认手动备份成功后再启用每天定时备份：

```bash
systemctl enable --now zhishu-postgres-backup.timer
systemctl list-timers zhishu-postgres-backup.timer
```

恢复演练必须在非生产库执行：

```bash
PGPASSWORD="$POSTGRES_PASSWORD" "$PG_RESTORE_BIN" \
  -h 127.0.0.1 \
  -p 5432 \
  -U zhishu \
  -d zhishu_bi_restore \
  --clean \
  --if-exists \
  /var/backups/zhishu/postgres/zhishu_bi-YYYYMMDDTHHMMSSZ.dump
```

验收标准：

- 备份命令退出码为 `0`，备份文件大小非 `0`。
- 备份目录权限为 `0700`，备份文件权限不向其它用户开放。
- `.sha256` 校验文件存在；`sha256sum -c` 能通过。
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
- `AUTO_RUN_MIGRATIONS=false`，上线前只通过 `zhishu-migrate.service` 或 `python -m scripts.db_migrate` 执行一次迁移。
- `CACHE_TYPE=redis`，`/ready` 中 cache 状态为 `ok`。
- 创建一个 `system.ping` 任务，worker 能消费并返回 `succeeded`。
- 在任务 running 时停掉 worker，超过 `TASK_QUEUE_VISIBILITY_TIMEOUT_SECONDS` 后，新 worker 能恢复任务或按最大重试次数标记失败。
- 停掉任意一个 backend 副本，Nginx 仍能把请求转到其他健康副本。

## 日志轮转

生产部署时安装 logrotate 配置：

```bash
install -o root -g root -m 0644 deploy/logrotate/zhishu /etc/logrotate.d/zhishu
logrotate -d /etc/logrotate.d/zhishu
```

确认路径与生产实际一致：

- 应用日志：`/opt/zhishu/logs/*.log`，由后端 `LOG_DIR` 控制。
- Nginx 日志：`/var/log/nginx/zhishu.access.log`、`/var/log/nginx/zhishu.error.log`。
- Redis 日志：`/var/log/redis/zhishu-redis.log`。

上线验收时至少执行一次 dry-run；如果生产路径改过，要先调整 `deploy/logrotate/zhishu` 再安装。
真实轮转由系统 logrotate 定时任务触发，也可以在维护窗口手动执行：

```bash
logrotate -f /etc/logrotate.d/zhishu
```

验收标准：

- `logrotate -d /etc/logrotate.d/zhishu` 不报错。
- 日志文件轮转后服务不需要重启，仍能继续写入当前日志。
- 磁盘使用率纳入监控，备份目录和日志目录至少设置一个告警阈值。

## 上线验收

上线前必须留存验收记录，包括执行人、执行时间、环境标识、版本号、命令输出或截图、失败项处理结论。
任一 P0/P1 项未通过时不得对企业客户开放生产流量。

### P0 发布门禁

- 后端测试：`python -m pytest -q` 通过；前端：`npm run build` 通过。
- 依赖审计：`npm audit --omit=dev` 和 `pip-audit` 无高危生产阻断漏洞。
- 生产配置：`APP_ENV=production python scripts/production_check.py` 返回 `Production settings check passed.`。
- 数据库迁移：`APP_ENV=production python -m scripts.db_migrate` 或 `systemctl start zhishu-migrate` 在启动 API 副本前成功完成，且 `AUTO_RUN_MIGRATIONS=false`。
- 健康检查：`GET /health` 返回 `200`；`GET /ready` 返回 `200`，且 cache 为 Redis `ok`。
- Redis：`CACHE_TYPE=redis`，登录限流、租户限流、任务队列和任务状态均使用 Redis，不允许生产使用进程内存兜底。
- 密钥：`SECRET_KEY`、`SENSITIVE_CONFIG_ENCRYPTION_KEY`、数据库密码、Redis 密码、模型 API Key 均来自生产环境变量，且不是开发默认值。
- 敏感字段：管理员新建或更新数据源/大模型配置后，数据库中对应敏感字段以 `fernet:v1:` 开头。
- Nginx/TLS：外部只暴露 `80/443`，TLS 证书有效，HTTP 自动跳转 HTTPS，后端 API 副本只监听内网或受控网段。

### P0 数据与权限验收

- 两个测试租户分别创建用户、数据源、Data Skills、对话、看板和自定义 Agent；任一普通用户不能列出、读取、导出或执行另一租户资产。
- 普通用户不能看到未授权数据源、连接配置、其他用户任务、其他用户对话和其他租户用量。
- Smart Q&A、仪表盘加载/预览、分析助手、推荐问题、自定义 Agent 相关入口都必须先验证当前租户和数据源授权，再读取 schema、语义层、样例数据或执行 SQL。
- SQL 执行入口必须经过统一查询执行器或等效的 `check_sql_read`、数据源访问、表权限、列权限、行权限校验；不得从用户可达入口直接调用底层 `exec_sql`。
- 字段权限回归：给普通用户隐藏一个敏感字段后，历史 ChatBI 记录、实时图表刷新、仪表盘图表、分析助手查询和 Excel 导出都不得返回该字段或旧缓存数据。
- 表权限回归：移除用户对某张表的访问后，已保存 SQL、仪表盘图表、分享图表和历史对话都应返回权限错误，而不是继续展示缓存数据。
- 行权限回归：配置一条行级过滤规则后，Smart Q&A、仪表盘和分析助手返回行数必须与手工加过滤条件的 SQL 一致。
- SQL 安全回归：`INSERT/UPDATE/DELETE/DROP/ALTER/COPY/CALL/SET`、多语句写入、危险函数和无法解析表范围的 SQL 都必须被拒绝。

### P1 多租户商业化验收

- `GET /api/v1/system/tenant/usage` 由 SaaS 管理员或企业管理员访问时返回租户日用量记录，普通成员不能跨租户查看。
- 产生一次 ChatBI、分析助手和任务队列调用后，`sys_tenant_usage_daily` 中出现对应租户的日聚合记录。
- 将测试租户套餐限额调低后，超额请求返回 `quota_exceeded`；其他租户仍可正常使用。
- 单个租户超过 ChatBI/分析助手/推荐问题每分钟限额时被限流，其他租户仍可正常请求。
- SaaS 管理员把租户设置为 `suspended` 或 `cancelled` 后，高消耗能力被拦截；`past_due` 仅作为运营状态，不自动停服。
- 企业邮箱域从 `pending` 到 `verified` 后，同域邮箱用户登录会自动加入该租户；`disabled` 域不会自动归属。
- 租户 IP 白名单会阻止非白名单来源；强制 SSO 会阻止本地账号；SaaS 管理员支持流程不被阻断。
- 租户注销、数据导出、数据删除请求从提交到审核到完成均有审计记录，且完成后不会自动停用租户或自动删除业务表。

### P1 高可用与运维验收

- Nginx upstream 至少配置两个 backend，连续访问 `/ready` 可看到请求被健康副本承接。
- 停掉任意一个 backend 副本，Nginx 仍能把请求转到其他健康副本。
- `GET /api/v1/system/tasks/health` 由系统管理员访问时返回 pending/processing/registered tasks。
- 创建一个 `system.ping` 任务，worker 能消费并返回 `succeeded`。
- 停掉一个 worker 后，超时任务能恢复到 pending 或最终 failed。
- 配置 `TASK_QUEUE_MAX_PENDING_PER_TENANT` 和 `TASK_QUEUE_MAX_PROCESSING_PER_TENANT`，验证单个租户不能占满队列或 worker。
- PostgreSQL 备份文件实际生成，`.sha256` 校验通过，并恢复到非生产库成功。
- `logrotate -d /etc/logrotate.d/zhishu` 通过，日志和备份目录有磁盘使用率告警。
- 应用、Nginx、Redis、PostgreSQL、worker 的日志纳入采集；至少配置 5xx、登录失败激增、Redis 不可用、worker 积压、磁盘空间、备份失败告警。

### P2 体验与限制验收

- 前端静态资源走生产 Nginx 路径，刷新深链页面不 404，上传/下载/导出路径可用。
- 大文件上传超过限制时返回明确错误，合法 Excel/CSV 导入文件按租户目录隔离。
- 当前暂不承诺跨 Region 主备、多活、Kubernetes、Helm、对象存储和多机器共享文件目录；如生产部署跨机器，必须先补共享存储或对象存储方案。

## 暂不纳入

- 跨 Region 主备、多活和自动故障转移编排。
- 对象存储。当前单机多副本仍共享本地 `file/excel/images` 目录，多机器生产前必须切换到共享存储或对象存储。
- 数据库上云。
- Kubernetes / Helm。
