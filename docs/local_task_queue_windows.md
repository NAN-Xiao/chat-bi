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

当前注册了一个测试任务：

```text
system.ping
```

管理员可调用：

```text
POST /api/v1/system/tasks/ping
GET  /api/v1/system/tasks/{task_id}
GET  /api/v1/system/tasks/health
```

后续 Excel/CSV 导入、数据源探查、字段同步、embedding 刷新会逐步迁到同一套队列。
