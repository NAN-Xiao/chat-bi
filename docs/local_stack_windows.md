# Windows 本地一键编排说明

`tools/stack-local.ps1` 用来把本地开发环境的核心服务串起来：

- PostgreSQL：默认检查 `127.0.0.1:15433`。
- Redis：默认检查 `127.0.0.1:6379`。
- backend：默认单副本 `8010`。
- Nginx：默认监听 `8081`。
- worker：默认启动 1 个，用于消费 Redis 任务队列。

脚本会优先探测端口。PostgreSQL 和 Redis 如果已经在运行，就不会重复启动；如果没运行，只有在你提供服务名或可执行文件路径时才会尝试拉起。

## 开发单副本

```powershell
.\tools\stack-local.ps1 -Action start
```

查看状态：

```powershell
.\tools\stack-local.ps1 -Action status
```

如果不想启动任务队列 worker：

```powershell
.\tools\stack-local.ps1 -Action start -SkipWorker
```

## 多副本压测/生产模拟

多副本会让 backend 本地脚本自动切到 Redis 缓存：

```powershell
.\tools\stack-local.ps1 -Action start -BackendPorts 8010,8012,8013 -StartWorker -Workers 2
```

Nginx 会把流量分发到这些 backend 端口：

```text
http://127.0.0.1:8081/
```

## 启动 PostgreSQL 或 Redis

如果 PostgreSQL / Redis 已经是 Windows 服务，可以传服务名：

```powershell
.\tools\stack-local.ps1 -Action start -PostgresServiceName "postgresql-x64-16" -RedisServiceName "Redis"
```

如果 Redis 不是服务，但 `redis-server` 在 PATH 里，脚本可直接启动。也可以显式传路径：

```powershell
.\tools\stack-local.ps1 -Action start -RedisServerPath "D:\tools\redis\redis-server.exe"
```

如果 PostgreSQL 是 zip/portable 方式，可以传 `pg_ctl.exe` 所在目录和数据目录：

```powershell
.\tools\stack-local.ps1 -Action start -PostgresBin "D:\tools\postgres\bin" -PostgresData "D:\data\postgres"
```

## 停止

```powershell
.\tools\stack-local.ps1 -Action stop
```

停止策略是保守的：

- backend、Nginx、worker 会通过本项目脚本停止。
- Redis 只有在由 `stack-local.ps1` 启动并写入 pid 文件，或传了 `-RedisServiceName` 时才会停止。
- PostgreSQL 只有在传了 `-PostgresServiceName` 或 `-PostgresBin/-PostgresData` 时才会停止。

这样可以避免误停开发机上其他项目正在使用的数据库或缓存服务。
