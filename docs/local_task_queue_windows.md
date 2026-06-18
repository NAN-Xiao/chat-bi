# Windows 本地任务队列运行说明

第一版任务队列使用 Redis 存储队列和任务状态。

## 启动 worker

先确认 Redis `127.0.0.1:6379` 已启动。

启动 1 个 worker：

```powershell
.\tools\worker-local.ps1 -Action start -Workers 1
```

启动多个 worker：

```powershell
.\tools\worker-local.ps1 -Action start -Workers 2
```

查看状态：

```powershell
.\tools\worker-local.ps1 -Action status -Workers 2
```

停止：

```powershell
.\tools\worker-local.ps1 -Action stop -Workers 2
```

日志在：

```text
.codex-runtime/task-workers/
```

## API

当前注册的任务包括：

```text
system.ping
datasource.sync_fields
datasource.table_embedding
datasource.datasource_embedding
datasource.fill_empty_table_and_ds_embedding
terminology.embedding
terminology.fill_empty_embedding
data_training.embedding
data_training.fill_empty_embedding
```

管理员可调用：

```text
POST /api/v1/system/tasks/ping
GET  /api/v1/system/tasks/{task_id}
GET  /api/v1/system/tasks/health
```

后续 Excel/CSV 导入、数据源探查、字段同步、embedding 刷新会逐步迁到同一套队列。

当前已迁移：

- 单表字段同步：`/datasource/syncFields/{id}` 会返回任务信息，worker 后台执行。
- 表和数据源 embedding：字段同步、表备注、字段备注、数据源更新后投递到 Redis 队列。
- 术语和 SQL 示例 embedding：新增、更新、批量导入后投递到 Redis 队列。

本地一键启动默认会启动 1 个 worker：

```powershell
.\tools\stack-local.ps1 -Action start
```

只有不测试队列功能时才使用：

```powershell
.\tools\stack-local.ps1 -Action start -SkipWorker
```
