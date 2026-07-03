# SLG BI Mock 独立定时造数镜像开发文档

记录日期：2026-07-03

## 背景

`SLG BI Mock` 当前用于演示通用 BI / ChatBI 的明细级数据分析能力。现有基础脚本 `tools/create_slg_bi_mock_db_prod.py` 适合一次性初始化或重建 `slg_bi_mock_test` 数据库，但不适合作为长期运行的定时追加任务。

新需求调整为：

- 定时向 `slg_bi_mock_test` 追加数据。
- 每小时检查当前业务日前 N 天、当天、后 M 天的整天业务数据是否已生成。
- N 和 M 支持独立配置：`TARGET_PAST_DAYS=N`、`TARGET_FUTURE_DAYS=M`，默认 `N=7`、`M=7`。
- 每个目标业务日的锚点时间为该日 `00:00:00`。
- 缺失哪一天就补充哪一天；已成功生成的日期不重复追加。
- 数据保留两个月，清理逻辑按 `auto_gen_time` 执行，不按业务时间字段执行。
- 造数器独立打包、独立部署、独立运行，不影响现有应用镜像发布。

## 核心口径

假设当前时间为 `2026-07-03 10:25:00 Asia/Shanghai`：

```text
target_business_dates = [
  2026-06-26,
  2026-06-27,
  2026-06-28,
  2026-06-29,
  2026-06-30,
  2026-07-01,
  2026-07-02,
  2026-07-03,
  2026-07-04,
  2026-07-05,
  2026-07-06,
  2026-07-07,
  2026-07-08,
  2026-07-09,
  2026-07-10,
]
```

默认配置 `TARGET_PAST_DAYS=7`、`TARGET_FUTURE_DAYS=7` 下，造数器每小时醒来后检查这 15 个目标业务日是否已经成功生成。如果 `2026-07-05` 缺失，则只追加 `2026-07-05 00:00:00 <= 业务时间 < 2026-07-06 00:00:00` 的一天明细数据。

默认窗口包含明天的数据。例如当前业务日是 `2026-07-03` 时，`2026-07-04` 会被纳入检查；如果状态表中没有 `2026-07-04` 的成功记录，就会生成并记录这一天。

到了第二天 `2026-07-04`，检查窗口自然滚动为：

```text
target_business_dates = [
  2026-06-27,
  2026-06-28,
  2026-06-29,
  2026-06-30,
  2026-07-01,
  2026-07-02,
  2026-07-03,
  2026-07-04,
  2026-07-05,
  2026-07-06,
  2026-07-07,
  2026-07-08,
  2026-07-09,
  2026-07-10,
  2026-07-11,
]
```

如果窗口内大部分日期已生成，只追加缺失日期；如果 `2026-07-05` 缺失而其他日期已成功生成，则只补 `2026-07-05`。到了 `2026-07-04`，新进入窗口的 `2026-07-11` 如果缺失也会被补齐。

这里有两类时间，必须严格区分：

- 业务时间：写入 `install_date`、`register_time`、`session_start`、`event_time`、`event_date`、`payment.event_time` 等字段，落在对应目标业务日内。
- 生成时间：写入 `auto_gen_time`，值为脚本实际生成数据时的 Unix 秒级时间戳，用于自动清理，与业务分析无关。

## 总体设计

新增独立发布物：

```text
Dockerfile                         # 现有应用镜像，保持不变
Dockerfile.slg-mock-generator      # 新增：SLG mock 定时造数镜像
tools/slg_bi_mock_scheduled_generator.py
```

镜像命名与现有应用镜像分离：

```text
主应用镜像：chat-bi-app:<git-sha> 或 shuzhi:<version>
造数镜像：chat-bi-slg-mock-generator:<git-sha>
```

两者不共用镜像名、入口命令和服务端口。造数镜像只连接目标 PostgreSQL，不暴露 HTTP 服务，不启动后端 API，不启动前端，不启动 MCP，不启动任务 worker。

## 与现有打包发布的关系

该方案不会和当前发布冲突：

- 现有 `Dockerfile` 不需要改动。
- 现有应用镜像仍按原流程构建。
- 新镜像使用独立 `Dockerfile.slg-mock-generator`。
- 新容器只运行数据生成入口，不占用 `8000`、`8001`、`5173`、`5432` 等应用端口。
- CI/CD 可拆成两个 job：应用镜像构建和 mock 造数镜像构建。
- 主应用升级不必重启造数器；造数器升级也不影响 API、前端和 MCP。

推荐在 compose 中使用可选 profile：

```yaml
services:
  slg-mock-generator:
    image: chat-bi-slg-mock-generator:latest
    profiles: ["mock-data"]
    restart: always
    volumes:
      - ./deploy/slg_mock_generator.yaml:/app/config/slg_mock_generator.yaml:ro
    environment:
      CONFIG_FILE: /app/config/slg_mock_generator.yaml
      DB_HOST: 127.0.0.1
      DB_PORT: "5432"
      DB_NAME: slg_bi_mock_test
      DB_USER: postgres
      DB_PASSWORD: "111111"
      CHECK_INTERVAL_SECONDS: "3600"
      TARGET_PAST_DAYS: "7"
      TARGET_FUTURE_DAYS: "7"
      RETENTION_DAYS: "60"
      TIMEZONE: Asia/Shanghai
```

启动时显式启用：

```bash
docker compose --profile mock-data up -d slg-mock-generator
```

不带 `mock-data` profile 时，造数器不会随主应用启动。

## 运行模式

造数器应支持两种运行模式：

```bash
# 常驻模式：容器内每小时检查一次目标业务日是否已生成
python tools/slg_bi_mock_scheduled_generator.py

# 单次模式：执行一次检查、必要时生成、清理，然后退出，便于 CronJob 使用
python tools/slg_bi_mock_scheduled_generator.py --run-once
```

推荐第一版实现“常驻循环 + `--run-once`”。本地和 docker compose 可以常驻运行，后续迁移到 Kubernetes CronJob 或宿主机 cron 时不需要重写生成逻辑。

常驻循环流程：

```text
启动
连接 PostgreSQL
确保基础 schema、状态表、auto_gen_time 字段和索引存在
按当前时间和配置项 TARGET_PAST_DAYS / TARGET_FUTURE_DAYS 计算目标业务日集合
逐日检查目标业务日是否已成功生成
如果某日已生成：跳过该日
如果某日未生成：生成该目标业务日整天明细数据
该日明细数据入库成功后，再记录该业务日期已生成
按 auto_gen_time 清理超过 RETENTION_DAYS 的自动生成数据
睡眠 CHECK_INTERVAL_SECONDS
```

## 目标业务日集合计算

默认配置：

```text
TIMEZONE=Asia/Shanghai
TARGET_PAST_DAYS=7
TARGET_FUTURE_DAYS=7
```

计算规则：

```python
now = datetime.now(ZoneInfo(TIMEZONE))
today = now.date()
target_business_dates = [
    today + timedelta(days=offset)
    for offset in range(-TARGET_PAST_DAYS, TARGET_FUTURE_DAYS + 1)
]
```

目标业务日集合按本地业务时区计算，不按 UTC 日期计算。`TARGET_PAST_DAYS=N`、`TARGET_FUTURE_DAYS=M` 表示检查 `D-N` 到 `D+M`，包含当天 `D+0`，总天数为 `N + 1 + M`。默认 `N=7`、`M=7`，即检查 `D-7` 到 `D+7`，共 15 天。如果不希望补当天数据，可以把当天排除逻辑做成独立配置，但默认规则包含当天。

每个目标业务日独立计算：

```python
target_day_start = datetime.combine(target_business_date, time(0, 0, 0), tzinfo=ZoneInfo(TIMEZONE))
target_day_end = target_day_start + timedelta(days=1)
```

每一天生成的数据要求：

- `dim_player.install_date = target_business_date`。
- `register_time` 落在目标日内。
- `fact_sessions.session_start/session_end` 落在目标日内，跨日会话应截断到 `target_day_end - 1 秒`。
- `fact_events.event_time` 落在目标日内，`event_date = target_business_date`。
- `fact_payments.event_time` 落在目标日内，`event_date = target_business_date`。
- 战斗、资源、建筑、研究、练兵等事实表的业务时间也应落在目标日内。

## 生成日期记录表

新增生成日期记录表用于记录每个目标业务日是否已经成功入库，避免每小时重复追加同一天数据。

重要顺序：

```text
先按业务日生成并写入明细数据
明细数据入库成功
再写入 mock_generation_state 记录该 business_date 已生成
```

不要在明细数据入库前预先记录该业务日期。生成失败或事务回滚时，`mock_generation_state` 中不应留下该日期的成功记录，下一轮检查会继续补这一天。

```sql
create table if not exists mock_generation_state (
    generator_id varchar(64) not null,
    business_date date not null,
    business_day_start timestamptz not null,
    status text not null default 'success' check (status = 'success'),
    primary key (generator_id, business_date)
);
```

固定生成器 ID：

```text
generator_id = 'slg_bi_mock_scheduled_generator'
```

字段含义：

- `generator_id`：生成器标识，固定使用 `slg_bi_mock_scheduled_generator`，类型为 `varchar(64)`，不是自增数值 ID。
- `business_date`：目标业务日期，例如 `2026-07-06`。
- `business_day_start`：目标业务日零点，例如 `2026-07-06 00:00:00+08`。
- `status`：生成完成标记，固定为 `success`。该表只记录已经成功入库的业务日期。

状态表不再存储 `auto_gen_time`、`generated_at`、`row_counts`、`updated_at`。这些字段不参与幂等判断，行数和生成时间保留在运行日志中即可。

每小时检测逻辑需要对目标日期集合逐日执行：

```sql
select status
from mock_generation_state
where generator_id = 'slg_bi_mock_scheduled_generator'
  and business_date = :business_date;
```

判断规则：

- 记录存在且 `status = 'success'`：跳过生成。
- 记录不存在：生成该业务日整天数据。
- 生成和入库成功后：再插入或更新该日期的 `success` 记录。
- 生成失败或入库失败：事务回滚，不记录该业务日期，下次检查继续补数。

## 并发控制

默认只部署一个造数器副本。如果部署了多个副本，必须避免并发生成同一天数据。

推荐按业务日期使用 PostgreSQL advisory lock。由于当前生成函数会独立打开数据库连接，锁需要覆盖“检查状态、生成数据、写入成功记录”的完整过程，第一版使用会话级 advisory lock，并在该业务日处理结束后显式释放：

```sql
select pg_advisory_lock(hashtext('slg_bi_mock_scheduled_generator:' || :business_date::text));
-- 生成或跳过逻辑结束后
select pg_advisory_unlock(hashtext('slg_bi_mock_scheduled_generator:' || :business_date::text));
```

建议对每个缺失的业务日分别开启事务，避免某一天失败影响其他日期补数：

```text
for business_date in target_business_dates:
  begin
  计算 business_day_start / business_day_end
  获取该 business_date 的 advisory lock
  查询 mock_generation_state
  如果 status = success：commit 当前事务并继续下一日期
  否则生成该 business_date 整天明细数据
  写入该业务日的所有明细数据，并显式写入 auto_gen_time
  明细数据写入成功后，再插入 mock_generation_state 成功记录
  commit
  释放该 business_date 的 advisory lock

执行一次过期清理
```

如果生成失败：

```text
rollback 当前数据插入
不写入 mock_generation_state 成功记录
记录错误日志，等待下一轮检查重试该业务日期
释放该 business_date 的 advisory lock
```

这样下一次定时检查可以继续重试该日期，其他日期不受影响。

## auto_gen_time 字段规范

所有由自动生成器写入并需要自动清理的表，都应包含：

```sql
auto_gen_time bigint not null default 0
```

字段注释必须为：

```sql
comment on column <table_name>.auto_gen_time is
'数据自动生成时间 用于自动清理数据 和业务逻辑无关 不用于数据分析';
```

字段含义：

- 类型为 Unix 秒级时间戳。
- 自动生成脚本写入数据时必须显式传入 `int(time.time())`。
- 同一目标业务日的一批数据应使用同一个 `auto_gen_time`。
- 默认值 `0` 表示历史数据、手工数据或未标记来源的数据。
- 清理逻辑只处理 `auto_gen_time > 0` 的数据。
- 业务 SQL、Data Skills、看板 SQL、分析口径不得使用该字段。

当前基础生成脚本已在 `tools/create_slg_bi_mock_db_prod.py` 中按该规范添加 `auto_gen_time`，并提供 `cleanup_expired_auto_generated_rows(conn, retention_days=60)` 作为清理逻辑参考。

## 需要覆盖的表

基础 SLG mock 生成表：

```text
dim_server
dim_alliance
dim_product
dim_event_name
dim_player
fact_sessions
fact_events
fact_payments
fact_battles
fact_resource_transactions
fact_building_upgrades
fact_research
fact_army_training
```

如果定时造数器会写入看板扩展表，也必须同步添加 `auto_gen_time`：

```text
dim_hero
fact_expeditions
```

原则：只要是造数器写入、并需要自动清理的表，都必须有 `auto_gen_time`。系统配置表、Data Skills、看板配置、元数据说明表不按该字段清理。

## 清理策略

清理窗口以 `auto_gen_time` 为唯一判断依据，不使用业务时间字段，例如 `event_date`、`session_start`、`install_date`。

原因：

- 新需求会生成当前业务日前后窗口内的业务日期；如果按业务时间清理，未来日期天然不会过期，过去日期也可能因为补数时间较晚而被误删。
- 业务时间是给 BI 分析使用的模拟时间，不等于数据写入时间。
- `auto_gen_time` 与业务逻辑无关，只服务于自动清理。

过期条件：

```sql
auto_gen_time > 0
and auto_gen_time < extract(epoch from now() - (:retention_days * interval '1 day'))::bigint
```

默认：

```text
retention_days = 60
```

删除顺序必须遵守外键依赖，从事实表到维表：

```text
fact_payments
fact_resource_transactions
fact_battles
fact_building_upgrades
fact_research
fact_army_training
fact_events
fact_sessions
dim_player
dim_product
dim_event_name
dim_alliance
dim_server
```

维表不能只看 `auto_gen_time` 直接删除，必须确认没有事实表或其他维表引用。

事实表示例：

```sql
delete from fact_events
where auto_gen_time > 0
  and auto_gen_time < extract(epoch from now() - (60 * interval '1 day'))::bigint;
```

玩家维表示例：

```sql
delete from dim_player p
where p.auto_gen_time > 0
  and p.auto_gen_time < extract(epoch from now() - (60 * interval '1 day'))::bigint
  and not exists (select 1 from fact_sessions s where s.player_id = p.player_id)
  and not exists (select 1 from fact_events e where e.player_id = p.player_id)
  and not exists (select 1 from fact_payments py where py.player_id = p.player_id)
  and not exists (select 1 from fact_battles b where b.player_id = p.player_id or b.target_player_id = p.player_id)
  and not exists (select 1 from fact_resource_transactions r where r.player_id = p.player_id)
  and not exists (select 1 from fact_building_upgrades bu where bu.player_id = p.player_id)
  and not exists (select 1 from fact_research rs where rs.player_id = p.player_id)
  and not exists (select 1 from fact_army_training at where at.player_id = p.player_id);
```

`mock_generation_state` 不包含 `auto_gen_time`，不参与按生成时间的自动清理。它只作为业务日期幂等标记，避免明细数据清理后又被同一个滚动窗口误补。

## 索引建议

所有会按 `auto_gen_time` 清理的表都应添加索引：

```sql
create index if not exists idx_fact_events_auto_gen_time
on fact_events(auto_gen_time);
```

命名规则：

```text
idx_<table_name>_auto_gen_time
```

状态表不需要 `auto_gen_time` 索引。基础生成脚本中已经为基础表添加了该类索引，后续扩展表需要跟随补齐。

## 镜像设计

建议使用轻量 Python 镜像：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg[binary] PyYAML

COPY tools/create_slg_bi_mock_db_prod.py /app/tools/create_slg_bi_mock_db_prod.py
COPY tools/slg_bi_mock_scheduled_generator.py /app/tools/slg_bi_mock_scheduled_generator.py

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "/app/tools/slg_bi_mock_scheduled_generator.py"]
```

构建命令：

```bash
docker build -f Dockerfile.slg-mock-generator -t chat-bi-slg-mock-generator:latest .
```

如果在 CI 中构建，推荐使用同一个 commit SHA 打 tag：

```bash
docker build -f Dockerfile.slg-mock-generator -t chat-bi-slg-mock-generator:${GIT_SHA} .
```

## 配置文件与环境变量

检查窗口必须作为配置文件项支持，表达为当前业务日前 N 天、当天、后 M 天。配置文件是造数器的主配置来源，环境变量可用于覆盖配置或注入敏感信息。

推荐默认配置路径：

```text
/app/config/slg_mock_generator.yaml
```

配置文件示例：

```yaml
database:
  host: 127.0.0.1
  port: 5432
  name: slg_bi_mock_test
  user: postgres
  password: "111111"
  schema: public

generator:
  timezone: Asia/Shanghai
  target_past_days: 7
  target_future_days: 7
  check_interval_seconds: 3600
  retention_days: 60
  run_once: false
  log_level: INFO
```

字段说明：

- `generator.target_past_days`：向过去检查的窗口天数，即 N。默认 `7` 表示检查 `D-7` 到 `D-1`。
- `generator.target_future_days`：向未来检查的窗口天数，即 M。默认 `7` 表示检查 `D+1` 到 `D+7`。
- 当天 `D+0` 默认包含在检查窗口内。
- `generator.check_interval_seconds`：常驻模式下两次检查的间隔，默认一小时。
- `generator.retention_days`：按 `auto_gen_time` 清理自动生成数据的保留天数，默认 60 天。
- `generator.timezone`：目标业务日计算使用的业务时区。

建议同时支持以下环境变量覆盖配置文件：

```text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
DB_SCHEMA=public
TIMEZONE=Asia/Shanghai
TARGET_PAST_DAYS=7
TARGET_FUTURE_DAYS=7
CHECK_INTERVAL_SECONDS=3600
RETENTION_DAYS=60
RUN_ONCE=false
LOG_LEVEL=INFO
CONFIG_FILE=/app/config/slg_mock_generator.yaml
```

注意：

- 不要把数据库密码写死在镜像里。
- `slg_bi_mock_test` 是 BI demo 明细库，不是星通数智系统库 `zhishu_bi`。
- 生产或演示环境里应通过 Secret、环境变量或部署平台注入连接信息。
- 环境变量优先级应高于配置文件，便于容器部署时覆盖敏感项或临时调整窗口。
- `TARGET_PAST_DAYS` 在配置文件中的字段名为 `generator.target_past_days`，环境变量仅作为覆盖入口。
- `TARGET_FUTURE_DAYS` 在配置文件中的字段名为 `generator.target_future_days`，环境变量仅作为覆盖入口。

## 数据生成要求

定时造数器不应调用 `--recreate` 重建整库。

推荐拆成四类能力：

```text
load_config(config_file)
ensure_schema()
resolve_target_business_dates(now, target_past_days, target_future_days)
generate_and_record_business_day(target_day_start, target_day_end)
cleanup_expired_auto_generated_rows(retention_days)
```

其中：

- `load_config(...)` 读取 `CONFIG_FILE` 指向的 YAML 配置，并用环境变量覆盖同名部署参数。
- `ensure_schema()` 只做缺失表、缺失字段、缺失索引、状态表补齐。
- `resolve_target_business_dates(...)` 按业务时区和 `TARGET_PAST_DAYS`、`TARGET_FUTURE_DAYS` 计算目标业务日集合。
- `generate_and_record_business_day(...)` 每次只生成一个目标业务日整天的明细数据，并在该日明细数据写入成功后、最终提交前写入 `mock_generation_state` 成功记录。
- `cleanup_expired_auto_generated_rows(...)` 只按 `auto_gen_time` 清理过期自动生成数据。

每次生成的数据仍应满足：

- `fact_*` 表代表事件级或领域明细记录。
- 每条事实尽量可追溯到 `player_id`、`session_id`、业务事件时间。
- 指标如 DAU、留存、ARPU、ARPPU、付费率、LTV 在查询时计算。
- 不创建持久化聚合 KPI 表、日报表、玩家快照表或分析视图。

## 日志与可观测性

每轮检查应输出结构化日志：

```json
{
  "checked_business_dates": [
    "2026-06-26",
    "2026-06-27",
    "2026-06-28",
    "2026-06-29",
    "2026-06-30",
    "2026-07-01",
    "2026-07-02",
    "2026-07-03",
    "2026-07-04",
    "2026-07-05",
    "2026-07-06",
    "2026-07-07",
    "2026-07-08",
    "2026-07-09",
    "2026-07-10"
  ],
  "generated_dates": [
    {
      "business_date": "2026-07-05",
      "business_day_start": "2026-07-05T00:00:00+08:00",
      "auto_gen_time": 1783261500,
      "row_counts": {
        "dim_player": 120,
        "fact_sessions": 360,
        "fact_events": 4200,
        "fact_payments": 18
      }
    }
  ],
  "skipped_dates": [
    {"business_date": "2026-06-26", "reason": "already_generated"},
    {"business_date": "2026-07-10", "reason": "already_generated"}
  ],
  "cleanup": {
    "fact_events": 9000,
    "fact_sessions": 700
  }
}
```

如果当前检查窗口内的目标业务日都已生成：

```json
{
  "checked_business_dates": [
    "2026-06-26",
    "2026-06-27",
    "2026-06-28",
    "2026-06-29",
    "2026-06-30",
    "2026-07-01",
    "2026-07-02",
    "2026-07-03",
    "2026-07-04",
    "2026-07-05",
    "2026-07-06",
    "2026-07-07",
    "2026-07-08",
    "2026-07-09",
    "2026-07-10"
  ],
  "generated_dates": [],
  "skipped_dates": [
    {"business_date": "2026-06-26", "reason": "already_generated"},
    {"business_date": "2026-06-27", "reason": "already_generated"},
    {"business_date": "2026-06-28", "reason": "already_generated"},
    {"business_date": "2026-06-29", "reason": "already_generated"},
    {"business_date": "2026-06-30", "reason": "already_generated"},
    {"business_date": "2026-07-01", "reason": "already_generated"},
    {"business_date": "2026-07-02", "reason": "already_generated"},
    {"business_date": "2026-07-03", "reason": "already_generated"},
    {"business_date": "2026-07-04", "reason": "already_generated"},
    {"business_date": "2026-07-05", "reason": "already_generated"},
    {"business_date": "2026-07-06", "reason": "already_generated"},
    {"business_date": "2026-07-07", "reason": "already_generated"},
    {"business_date": "2026-07-08", "reason": "already_generated"},
    {"business_date": "2026-07-09", "reason": "already_generated"},
    {"business_date": "2026-07-10", "reason": "already_generated"}
  ]
}
```

异常处理：

- 数据库连接失败：记录错误，按退避策略重试。
- 单日生成失败：事务回滚，不记录该业务日期为已生成，下一轮继续补数。
- 清理失败：记录失败并退出或回滚，避免生成状态与实际数据不一致。

## 测试要求

至少增加以下测试：

- 目标日期集合测试：给定 `2026-07-03` 且默认 `N=7`、`M=7`，目标业务日集合应覆盖 `2026-06-26` 到 `2026-07-10`，且每个 `business_day_start` 为该日 `00:00:00`。
- 滚动窗口测试：给定 `2026-07-04` 且默认 `N=7`、`M=7`，目标业务日集合应覆盖 `2026-06-27` 到 `2026-07-11`。
- 配置测试：当 `generator.target_past_days=3`、`generator.target_future_days=5` 时，目标业务日集合应覆盖 `D-3` 到 `D+5`。
- 覆盖测试：当配置文件和环境变量同时设置窗口天数时，以环境变量 `TARGET_PAST_DAYS`、`TARGET_FUTURE_DAYS` 为准。
- 缺失补数测试：如果 `2026-07-05` 缺失而窗口内其他日期已成功生成，只生成 `2026-07-05`。
- 幂等测试：`mock_generation_state` 中某日期为 `success` 时不重复生成该日期。
- 重试测试：目标日没有成功记录时会尝试生成。
- 状态写入顺序测试：某业务日明细数据全部入库成功后，才写入 `mock_generation_state` 的成功记录。
- 失败不记录测试：某业务日生成或入库失败时，不写入该业务日期的成功记录，下一轮仍会补数。
- 状态表测试：`mock_generation_state.generator_id` 为 `varchar(64)`，状态表不包含 `auto_gen_time`、`generated_at`、`row_counts`、`updated_at`。
- 明天窗口测试：默认 `TARGET_FUTURE_DAYS=7` 时，当前业务日次日必须被纳入检查窗口。
- schema 测试：所有自动生成表都有 `auto_gen_time bigint not null default 0`。
- 注释测试：所有自动生成表的 `auto_gen_time` COMMENT 一致。
- 插入测试：定时造数写入的每张表都显式写入 `auto_gen_time > 0`。
- 清理测试：`auto_gen_time = 0` 的数据不被删除。
- 清理测试：`auto_gen_time` 超过保留期且无引用的数据会被删除。
- 引用保护测试：仍被事实表引用的维表数据不会被误删。
- 打包测试：`Dockerfile.slg-mock-generator` 可以独立构建。

当前已有回归测试：

```text
tests/test_slg_mock_auto_gen_time.py
```

该测试覆盖基础生成脚本中的字段、注释、索引、插入列和清理函数。

## 后续实施清单

1. 新增 `tools/slg_bi_mock_scheduled_generator.py`。
2. 新增 `Dockerfile.slg-mock-generator`。
3. 从 `create_slg_bi_mock_db_prod.py` 复用或抽取 schema、字典、清理函数。
4. 实现 `mock_generation_state` 状态表。
5. 实现可配置的 `D-TARGET_PAST_DAYS` 到 `D+TARGET_FUTURE_DAYS` 目标业务日集合计算，即当前业务日前 N 天、当天、后 M 天，默认 `N=7`、`M=7`。
6. 实现逐日幂等检测：已成功生成则跳过，没有成功记录则生成。
7. 实现缺失目标业务日的整天数据追加，不使用 `--recreate`。
8. 所有自动生成行写入统一的 `auto_gen_time`。
9. 明细数据入库成功后，再写入该业务日的成功生成记录。
10. 每轮结束按 `auto_gen_time` 清理超过 60 天的数据。
11. 可选：给 `docker-compose.yaml` 增加 `mock-data` profile 服务。
12. 新增 CI 独立构建 job，不影响主应用镜像构建。
13. 增加测试并运行 `pytest`、`ruff` 和镜像构建验证。

## 不做事项

- 不把造数器并入主应用镜像。
- 不让造数器启动 API、前端、MCP 或 worker。
- 不用 `event_date`、`install_date`、`session_start` 作为自动清理依据。
- 不清理 `auto_gen_time = 0` 的历史或手工数据。
- 不对已经 `success` 的业务日重复追加数据。
- 不只检查未来三天；必须覆盖当前业务日前 N 天、当天、后 M 天的滚动窗口，默认覆盖 `D-7` 到 `D+7`。
- 不创建持久聚合 KPI 表、快照表或分析视图。
- 不把 SLG 业务口径写入平台通用运行逻辑。
