# Windows 本地 PostgreSQL 备份与恢复

本地开发使用远程核心数据库，所以至少要有可重复的备份和恢复演练。脚本默认操作星通数智系统库：

```text
10.1.5.28:5432 / zhishu_bi_2.0.0 / root
```

备份文件默认放在：

```text
.codex-runtime/pg-backups/
```

这个目录被 Git 忽略，不会进入提交。

## 备份

```powershell
.\tools\postgres-backup-local.ps1 -Action backup
```

如果 PostgreSQL 的 `bin` 目录不在 PATH：

```powershell
.\tools\postgres-backup-local.ps1 -Action backup -PostgresBin "D:\tools\postgres\bin"
```

查看已有备份：

```powershell
.\tools\postgres-backup-local.ps1 -Action list
```

## 恢复

恢复可能覆盖本地数据，所以必须显式加 `-Force`：

```powershell
.\tools\postgres-backup-local.ps1 -Action restore -File ".codex-runtime\pg-backups\zhishu_bi_2.0.0-20260618_120000.dump" -Force
```

如果要先清理同名对象再恢复：

```powershell
.\tools\postgres-backup-local.ps1 -Action restore -File ".codex-runtime\pg-backups\zhishu_bi_2.0.0-20260618_120000.dump" -Clean -Force
```

## 纯 SQL 格式

默认使用 PostgreSQL custom dump，适合 `pg_restore`。如果需要纯 SQL：

```powershell
.\tools\postgres-backup-local.ps1 -Action backup -PlainSql
.\tools\postgres-backup-local.ps1 -Action restore -PlainSql -File ".codex-runtime\pg-backups\zhishu_bi_2.0.0-20260618_120000.sql" -Force
```

## 建议频率

- 每次做数据库结构调整前手动备份一次。
- 每次上线前演练一次恢复。
- 如果开始多人联调，可以加 Windows 计划任务做每日备份。
