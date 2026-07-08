# SLG BI Mock Docker 构建发布手册

记录日期：2026-07-03

本文档基于 `docs/slg_bi_mock_hourly_generator.md` 整理，面向 `SLG BI Mock` 独立定时造数器的 Docker 构建、配置、发布、回滚与排障。造数器是演示数据的独立发布物，不属于主应用 API、前端、MCP 或 worker 发布链路。

## 一、发布物边界

| 文件 | 用途 |
| --- | --- |
| `Dockerfile.slg-mock-generator` | 独立造数器镜像构建入口 |
| `Jenkinsfile.slg-mock-generator` | 独立 Jenkins Pipeline，负责构建、可选推送和可选重启造数器容器 |
| `tools/slg_bi_mock_scheduled_generator.py` | 容器入口脚本，支持常驻模式和 `--run-once` |
| `tools/create_slg_bi_mock_db_prod.py` | 复用基础 schema、字典和清理逻辑 |
| `deploy/slg_mock_generator.yaml` | 默认运行配置 |
| `docker-compose.yaml` | 本地可选 `mock-data` profile 示例 |

镜像命名建议：

```text
主应用镜像：shuzhi:<tag>
造数器镜像：chat-bi-slg-mock-generator:<tag>
```

两者必须保持独立镜像名、独立入口命令和独立发布节奏。造数器只连接目标 PostgreSQL，不暴露 HTTP 端口，不启动 API、前端、MCP、G2 SSR 或任务 worker。

## 二、构建命令

本地构建：

```bash
docker build \
  -f Dockerfile.slg-mock-generator \
  -t chat-bi-slg-mock-generator:local \
  .
```

按提交短哈希打版本标签：

```bash
GIT_SHA="$(git rev-parse --short HEAD)"

docker build \
  -f Dockerfile.slg-mock-generator \
  -t "chat-bi-slg-mock-generator:${GIT_SHA}" \
  .
```

推送到镜像仓库：

```bash
REGISTRY="registry.example.com/chat-bi"
GIT_SHA="$(git rev-parse --short HEAD)"

docker tag \
  "chat-bi-slg-mock-generator:${GIT_SHA}" \
  "${REGISTRY}/chat-bi-slg-mock-generator:${GIT_SHA}"

docker push "${REGISTRY}/chat-bi-slg-mock-generator:${GIT_SHA}"
```

不建议长期只发布 `latest`。可以额外维护 `latest` 方便演示，但生产或共享演示环境应记录并部署不可变 tag。

## 三、配置来源

默认配置文件路径：

```text
/app/config/slg_mock_generator.yaml
```

推荐运行时挂载仓库配置：

```bash
-v "$PWD/deploy/slg_mock_generator.yaml:/app/config/slg_mock_generator.yaml:ro"
```

环境变量优先级高于配置文件，适合注入敏感信息或临时调整窗口：

| 环境变量 | 配置文件字段 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `CONFIG_FILE` | 无 | `/app/config/slg_mock_generator.yaml` | 配置文件路径 |
| `DB_HOST` | `database.host` | `127.0.0.1` | 目标 BI demo PostgreSQL 地址 |
| `DB_PORT` | `database.port` | `5432` | 目标数据库端口 |
| `DB_NAME` | `database.name` | `slg_bi_mock_test` | 目标业务库 |
| `DB_USER` | `database.user` | `postgres` | 数据库用户 |
| `DB_PASSWORD` | `database.password` | `111111` | 数据库密码 |
| `DB_SCHEMA` | `database.schema` | `public` | schema |
| `TIMEZONE` | `generator.timezone` | `Asia/Shanghai` | 业务日期计算时区 |
| `TARGET_PAST_DAYS` | `generator.target_past_days` | `7` | 检查当前业务日前 N 天 |
| `TARGET_FUTURE_DAYS` | `generator.target_future_days` | `7` | 检查当前业务日后 M 天 |
| `NEW_USER_BEHAVIOR_DAYS` | `generator.new_user_behavior_days` | `7` | 补充近 N 天新增用户的老用户行为 |
| `DAILY_PLAYERS` | `generator.daily_players` | `3000` | 每日新增玩家数 |
| `CHECK_INTERVAL_SECONDS` | `generator.check_interval_seconds` | `3600` | 常驻模式检查间隔 |
| `RETENTION_DAYS` | `generator.retention_days` | `60` | 按 `auto_gen_time` 保留天数 |
| `RUN_ONCE` | `generator.run_once` | `false` | 是否单次运行后退出 |
| `LOG_LEVEL` | `generator.log_level` | `INFO` | 日志级别 |
| `SEED_BASE` | `generator.seed_base` | `20260613` | 确定性随机种子基准 |

注意：`slg_bi_mock_test` 是 BI demo 明细库，不是星通数智系统库 `zhishu_bi`。不要把 `SHUZHI_DB_*` 系统库配置直接套给造数器，除非明确要连接同一个 PostgreSQL 实例下的 demo 数据库。

## 四、本地运行

单次补数验证：

```bash
docker run --rm \
  --name slg-mock-generator-once \
  -v "$PWD/deploy/slg_mock_generator.yaml:/app/config/slg_mock_generator.yaml:ro" \
  -e CONFIG_FILE=/app/config/slg_mock_generator.yaml \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=5432 \
  -e DB_NAME=slg_bi_mock_test \
  -e DB_USER=postgres \
  -e DB_PASSWORD=111111 \
  -e RUN_ONCE=true \
  chat-bi-slg-mock-generator:local
```

常驻模式：

```bash
docker run -d \
  --name slg-mock-generator \
  --restart unless-stopped \
  -v "$PWD/deploy/slg_mock_generator.yaml:/app/config/slg_mock_generator.yaml:ro" \
  -e CONFIG_FILE=/app/config/slg_mock_generator.yaml \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=5432 \
  -e DB_NAME=slg_bi_mock_test \
  -e DB_USER=postgres \
  -e DB_PASSWORD=111111 \
  chat-bi-slg-mock-generator:local
```

如果在 Linux Docker 中连接宿主机 PostgreSQL，建议给容器增加：

```bash
--add-host=host.docker.internal:host-gateway
```

如果连接远端 PostgreSQL，直接把 `DB_HOST` 设置为远端地址。不要在容器里使用 `127.0.0.1` 连接宿主机数据库；容器内的 `127.0.0.1` 指向容器自身。

## 五、Compose 启停

本仓库 `docker-compose.yaml` 已把造数器放到可选 profile 中：

```bash
docker compose --profile mock-data up -d --build slg-mock-generator
```

查看日志：

```bash
docker compose logs -f slg-mock-generator
```

停止造数器但不影响主应用：

```bash
docker compose stop slg-mock-generator
```

移除造数器容器：

```bash
docker compose rm -f slg-mock-generator
```

不带 `--profile mock-data` 时，造数器不会随主应用启动。

## 六、CI 发布建议

推荐把造数器拆成独立 job，避免和主应用镜像相互阻塞：

```text
拉取代码
  -> 生成 GIT_SHA tag
  -> docker build -f Dockerfile.slg-mock-generator
  -> 镜像入口 smoke test
  -> 可选 docker push chat-bi-slg-mock-generator:<tag>
  -> 可选重启 slg-mock-generator 容器
```

仓库已提供独立 Pipeline：

```text
Jenkinsfile.slg-mock-generator
```

关键参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `BRANCH_NAME` | `release_ha` | 构建分支 |
| `IMAGE_TAG` | 空 | 空值时使用 `BUILD_NUMBER-git短哈希` |
| `IMAGE_REGISTRY` | 空 | 为空时只构建本地镜像；填写后推送到该仓库前缀 |
| `PUBLISH_LATEST` | `false` | 是否额外推送 `latest` |
| `DEPLOY_CONTAINER` | `false` | 是否重启本机 `slg-mock-generator` 容器 |
| `CLEAN_OLD_IMAGES` | `false` | 是否清理旧版本造数器镜像 |

部署容器时，Jenkins 节点需要预先准备：

```text
/home/chat-bi/slg-mock-generator.env
/home/chat-bi/slg_mock_generator.yaml
```

其中 `slg-mock-generator.env` 用于维护 `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD` 等敏感或环境相关配置。`DEPLOY_CONTAINER=false` 时不要求这些文件存在。

如果 CI 环境可访问测试 PostgreSQL，推荐执行一次真实 `RUN_ONCE=true`，并在日志中确认：

```text
checked_business_dates 非空
generated_dates 或 skipped_dates 正常输出
cleanup 正常结束或明确跳过
```

## 七、发布前检查

发布前确认：

```bash
docker images chat-bi-slg-mock-generator
docker inspect chat-bi-slg-mock-generator:<tag> --format '{{.Config.Entrypoint}}'
```

确认目标数据库不是系统库：

```bash
echo "$DB_HOST $DB_PORT $DB_NAME"
```

确认配置窗口：

```text
TARGET_PAST_DAYS=7
TARGET_FUTURE_DAYS=7
NEW_USER_BEHAVIOR_DAYS=7
RETENTION_DAYS=60
```

确认只部署一个常驻副本。若必须多副本，必须依赖脚本中的 PostgreSQL advisory lock 覆盖“检查状态、生成数据、写入状态”的完整过程。

## 八、回滚方案

造数器回滚只需要回退镜像 tag，不需要回退主应用：

```bash
docker stop slg-mock-generator
docker rm slg-mock-generator

docker run -d \
  --name slg-mock-generator \
  --restart unless-stopped \
  --env-file /path/to/slg-mock-generator.env \
  -v /path/to/slg_mock_generator.yaml:/app/config/slg_mock_generator.yaml:ro \
  chat-bi-slg-mock-generator:<previous-tag>
```

如果使用 systemd 管理，修改 unit 或环境文件里的镜像 tag 后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart slg-mock-generator.service
```

数据层回滚要谨慎处理。造数器按 `mock_generation_state` 做幂等控制，并按 `auto_gen_time` 清理自动生成数据；不要手工删除状态表记录来“触发重跑”，除非已经确认对应业务日的自动生成明细也需要重建。

## 九、常见排障

### 9.1 容器连接不上数据库

检查 `DB_HOST` 是否指向容器可访问的地址：

```bash
docker exec -it slg-mock-generator python - <<'PY'
import socket, os
host = os.getenv("DB_HOST", "127.0.0.1")
port = int(os.getenv("DB_PORT", "5432"))
socket.create_connection((host, port), timeout=5).close()
print("database tcp reachable")
PY
```

容器内 `127.0.0.1` 不是宿主机。Docker Desktop 可用 `host.docker.internal`；Linux Docker 可配 `--add-host=host.docker.internal:host-gateway`；生产环境优先使用真实数据库地址。

### 9.2 每小时重复生成同一天

优先检查 `mock_generation_state`：

```sql
select generator_id, state_type, cohort_date, business_date, status
from mock_generation_state
order by business_date desc, state_type, cohort_date
limit 50;
```

如果明细入库成功但状态记录缺失，说明生成过程可能在写状态前失败。应先排查当轮日志，不要直接补写状态。

### 9.3 数据没有按预期过期清理

清理只看 `auto_gen_time`，不看 `event_date`、`install_date`、`session_start` 等业务字段。确认待清理数据满足：

```sql
auto_gen_time > 0
and auto_gen_time < extract(epoch from now() - (60 * interval '1 day'))::bigint
```

`auto_gen_time = 0` 表示历史数据、手工数据或未标记来源的数据，不能被自动清理。

### 9.4 发布后主应用异常

造数器镜像不应该影响主应用容器。先确认是否误用了主应用镜像名、系统库配置或主应用容器名：

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
```

正常情况下，造数器容器没有端口映射，镜像名应为 `chat-bi-slg-mock-generator:<tag>`。

## 十、不做事项

- 不把造数器并入 `Dockerfile` 主应用镜像。
- 不让造数器容器暴露 `8000`、`8001`、`5173` 或 `5432`。
- 不用系统库 `zhishu_bi` 作为 demo 造数目标。
- 不把数据库密码写入镜像。
- 不用业务时间字段做自动清理条件。
- 不手工清理 `auto_gen_time = 0` 的数据。
- 不通过删除状态表记录来规避幂等逻辑。
