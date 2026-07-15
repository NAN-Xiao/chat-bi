# zhishu_bi systemd 定时备份实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在 `10.1.5.28` 上部署每天 `CST 12:00` 执行、保留 14 天且可校验的 `zhishu_bi` PostgreSQL 自动备份。

**架构：** 使用 Bash 脚本调用 `pg_dump -Fc`，先写临时文件并在成功后原子发布，再生成 SHA-256 校验文件和 `latest` 软链接。systemd oneshot service 使用独立系统账号运行脚本，systemd timer 负责精确调度和停机补跑；首次手动备份通过完整性验收后才启用 timer。

**技术栈：** Bash 5、PostgreSQL 17 客户端、systemd 252、Python 3/pytest、PowerShell OpenSSH 客户端。

## 全局约束

- 数据库连接必须使用 `10.1.5.28:5432`、数据库 `zhishu_bi`、用户 `root`。
- 数据库密码只能写入远端 `/etc/shuzhi/shuzhi-backup.env`，不得写入 Git、命令输出、systemd 单元或 journal。
- 备份按服务器 `CST` 时区每天 `12:00` 执行，不配置随机延迟。
- 备份目录固定为 `/var/backups/shuzhi/postgres`，保留 14 天。
- 仅执行逻辑备份和只读归档检查，不向生产库或其他数据库执行恢复。
- 保留当前工作区中与本任务无关的未提交修改，不纳入本任务提交。

## 文件结构

- 创建 `tests/shell/test_shuzhi_postgres_backup.sh`：覆盖备份成功、失败残留清理和保留期清理的真实 Shell 行为。
- 修改 `deploy/scripts/shuzhi-postgres-backup.sh`：使用临时文件、退出陷阱和原子重命名发布备份。
- 修改 `tests/test_production_readiness.py`：锁定专用账号、独立环境文件和精确 12 点 timer 配置。
- 修改 `deploy/systemd/shuzhi-postgres-backup.service`：使用 `shuzhi-backup` 账号和独立环境文件。
- 修改 `deploy/systemd/shuzhi-postgres-backup.timer`：改为 `12:00`，移除随机延迟并设置秒级精度。
- 修改 `docs/single_tenant_production_readiness.md`：同步部署账号、环境文件、目录权限和执行时间。
- 部署远端文件到设计规格中约定的 `/opt`、`/etc` 和 `/var/backups` 路径。

---

### Task 1：确保备份原子落盘并清理失败残留

**文件：**
- 创建：`tests/shell/test_shuzhi_postgres_backup.sh`
- 修改：`deploy/scripts/shuzhi-postgres-backup.sh`

**接口：**
- 输入：`POSTGRES_SERVER`、`POSTGRES_PORT`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`BACKUP_DIR`、`BACKUP_RETENTION_DAYS`、`PG_DUMP_BIN`。
- 输出：`zhishu_bi-<UTC时间戳>.dump`、对应 `.sha256` 文件，以及两个 `latest` 软链接。
- 失败契约：`pg_dump` 非零退出或输出为空时，脚本非零退出且不留下 `.partial` 或正式 `.dump` 文件。

- [ ] **步骤 1：写入会失败的真实 Shell 测试**

创建 `tests/shell/test_shuzhi_postgres_backup.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT="${1:-deploy/scripts/shuzhi-postgres-backup.sh}"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

FAKE_PG_DUMP="$TEST_ROOT/fake-pg-dump"
cat > "$FAKE_PG_DUMP" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
output=""
for argument in "$@"; do
  case "$argument" in
    --file=*) output="${argument#*=}" ;;
  esac
done
[[ -n "$output" ]] || exit 3
printf 'partial archive\n' > "$output"
if [[ "${FAKE_PG_DUMP_FAIL:-0}" == "1" ]]; then
  exit 9
fi
printf 'complete archive\n' >> "$output"
EOF
chmod 0755 "$FAKE_PG_DUMP"

run_backup() {
  local backup_dir="$1"
  local fail_dump="${2:-0}"
  env \
    ENV_FILE="$TEST_ROOT/missing.env" \
    POSTGRES_SERVER="10.1.5.28" \
    POSTGRES_PORT="5432" \
    POSTGRES_DB="zhishu_bi" \
    POSTGRES_USER="root" \
    POSTGRES_PASSWORD="test-only" \
    BACKUP_DIR="$backup_dir" \
    BACKUP_RETENTION_DAYS="14" \
    PG_DUMP_BIN="$FAKE_PG_DUMP" \
    FAKE_PG_DUMP_FAIL="$fail_dump" \
    bash "$SCRIPT"
}

failure_dir="$TEST_ROOT/failure"
if run_backup "$failure_dir" 1; then
  fail "pg_dump 失败时脚本仍返回成功"
fi
if find "$failure_dir" -maxdepth 1 -type f \( -name '*.partial' -o -name '*.dump' \) | grep -q .; then
  fail "pg_dump 失败后残留了备份文件"
fi

success_dir="$TEST_ROOT/success"
run_backup "$success_dir"
backup_file="$(find "$success_dir" -maxdepth 1 -type f -name 'zhishu_bi-*.dump' | head -n 1)"
[[ -n "$backup_file" && -s "$backup_file" ]] || fail "没有生成非空正式备份"
[[ -s "$backup_file.sha256" ]] || fail "没有生成校验文件"
[[ -L "$success_dir/zhishu_bi-latest.dump" ]] || fail "没有生成 latest 备份链接"
[[ -L "$success_dir/zhishu_bi-latest.dump.sha256" ]] || fail "没有生成 latest 校验链接"
if find "$success_dir" -maxdepth 1 -type f -name '*.partial' | grep -q .; then
  fail "成功后仍残留临时文件"
fi

expired_dir="$TEST_ROOT/expired"
mkdir -p "$expired_dir"
printf 'old archive\n' > "$expired_dir/zhishu_bi-20000101T000000Z.dump"
printf 'old checksum\n' > "$expired_dir/zhishu_bi-20000101T000000Z.dump.sha256"
touch -d '20 days ago' "$expired_dir"/zhishu_bi-20000101T000000Z.dump*
run_backup "$expired_dir"
[[ ! -e "$expired_dir/zhishu_bi-20000101T000000Z.dump" ]] || fail "过期备份未删除"
[[ ! -e "$expired_dir/zhishu_bi-20000101T000000Z.dump.sha256" ]] || fail "过期校验文件未删除"

echo "PASS: PostgreSQL backup shell behavior"
```

- [ ] **步骤 2：运行测试并确认失败原因正确**

运行：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' tests/shell/test_shuzhi_postgres_backup.sh
```

预期：退出码非零，输出包含 `pg_dump 失败后残留了备份文件`；失败原因是当前脚本直接写正式 `.dump` 文件。

- [ ] **步骤 3：实现临时文件、退出清理和原子发布**

将 `deploy/scripts/shuzhi-postgres-backup.sh` 的备份文件生成和发布部分实现为：

```bash
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
safe_db_name="${POSTGRES_DB//[^A-Za-z0-9_.-]/_}"
backup_file="$BACKUP_DIR/${safe_db_name}-${timestamp}.dump"
partial_file="$backup_file.partial"
checksum_file="$backup_file.sha256"

cleanup() {
  rm -f -- "$partial_file"
}
trap cleanup EXIT

export PGPASSWORD="$POSTGRES_PASSWORD"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"
export PGSSLMODE="${PGSSLMODE:-prefer}"

"$PG_DUMP_BIN" \
  --host="$POSTGRES_SERVER" \
  --port="$POSTGRES_PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="$partial_file"

unset PGPASSWORD

if [[ ! -s "$partial_file" ]]; then
  echo "Backup file is empty: $partial_file" >&2
  exit 1
fi

mv -- "$partial_file" "$backup_file"
```

保留现有 SHA-256、`latest` 软链接和 14 天清理逻辑，使其只在 `mv` 成功后执行。

- [ ] **步骤 4：运行行为测试和语法检查**

运行：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n deploy/scripts/shuzhi-postgres-backup.sh
& 'C:\Program Files\Git\bin\bash.exe' tests/shell/test_shuzhi_postgres_backup.sh
```

预期：两个命令均退出码 `0`，行为测试输出 `PASS: PostgreSQL backup shell behavior`。

- [ ] **步骤 5：提交任务 1**

```powershell
git add deploy/scripts/shuzhi-postgres-backup.sh tests/shell/test_shuzhi_postgres_backup.sh
git commit -m "修复：保证数据库备份原子落盘"
```

---

### Task 2：配置独立账号和每日 12 点 systemd timer

**文件：**
- 修改：`tests/test_production_readiness.py:139`
- 修改：`deploy/systemd/shuzhi-postgres-backup.service`
- 修改：`deploy/systemd/shuzhi-postgres-backup.timer`
- 修改：`docs/single_tenant_production_readiness.md:103`

**接口：**
- service 读取 `/etc/shuzhi/shuzhi-backup.env`，以 `shuzhi-backup` 用户和用户组执行脚本。
- timer 通过 `Unit=shuzhi-postgres-backup.service` 触发 service，调度表达式固定为 `*-*-* 12:00:00`。

- [ ] **步骤 1：先更新部署资产测试**

在 `test_production_postgres_backup_deployment_artifacts_are_present` 中增加或替换为以下断言：

```python
assert 'partial_file="$backup_file.partial"' in script
assert "trap cleanup EXIT" in script
assert 'mv -- "$partial_file" "$backup_file"' in script

assert "EnvironmentFile=/etc/shuzhi/shuzhi-backup.env" in service
assert "ExecStart=/opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh" in service
assert "User=shuzhi-backup" in service
assert "Group=shuzhi-backup" in service
assert "NoNewPrivileges=true" in service

assert "OnCalendar=*-*-* 12:00:00" in timer
assert "AccuracySec=1s" in timer
assert "RandomizedDelaySec" not in timer
assert "Persistent=true" in timer
assert "WantedBy=timers.target" in timer

assert "/etc/shuzhi/shuzhi-backup.env" in readiness_doc
assert "12:00" in readiness_doc
assert "shuzhi-backup" in readiness_doc
```

- [ ] **步骤 2：运行定向测试并确认失败**

运行：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_production_readiness.py::test_production_postgres_backup_deployment_artifacts_are_present -q
```

预期：测试失败，首先报告当前 service 仍使用 `/etc/shuzhi/shuzhi.env` 或当前 timer 仍为 `02:30`。

- [ ] **步骤 3：更新 systemd service**

将 `deploy/systemd/shuzhi-postgres-backup.service` 更新为：

```ini
[Unit]
Description=星通数智 PostgreSQL backup
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=shuzhi-backup
Group=shuzhi-backup
EnvironmentFile=/etc/shuzhi/shuzhi-backup.env
ExecStart=/opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

- [ ] **步骤 4：更新 systemd timer**

将 `deploy/systemd/shuzhi-postgres-backup.timer` 更新为：

```ini
[Unit]
Description=Run 星通数智 PostgreSQL backup daily at 12:00

[Timer]
OnCalendar=*-*-* 12:00:00
AccuracySec=1s
Persistent=true
Unit=shuzhi-postgres-backup.service

[Install]
WantedBy=timers.target
```

- [ ] **步骤 5：同步生产就绪文档**

在 `docs/single_tenant_production_readiness.md` 的“备份恢复”章节明确写入：

```markdown
备份 service 使用独立的 `shuzhi-backup` 系统账号，并从权限为 `0600` 的
`/etc/shuzhi/shuzhi-backup.env` 读取数据库连接参数。timer 按服务器时区每天
`12:00` 精确执行，备份默认保存到 `/var/backups/shuzhi/postgres` 并保留 14 天。
```

将安装命令中的目录所有者改为 `shuzhi-backup:shuzhi-backup`，并在安装前增加：

```bash
id -u shuzhi-backup >/dev/null 2>&1 || \
  useradd --system --home-dir /var/lib/shuzhi-backup --create-home --shell /sbin/nologin shuzhi-backup
install -o root -g root -m 0600 /dev/null /etc/shuzhi/shuzhi-backup.env
```

- [ ] **步骤 6：运行定向测试和相关回归测试**

运行：

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_production_readiness.py::test_production_postgres_backup_deployment_artifacts_are_present tests/test_zhishu_bi_scheduled_backup_script.py -q
```

预期：全部通过，无失败和错误。

- [ ] **步骤 7：提交任务 2**

```powershell
git add tests/test_production_readiness.py deploy/systemd/shuzhi-postgres-backup.service deploy/systemd/shuzhi-postgres-backup.timer docs/single_tenant_production_readiness.md
git commit -m "运维：配置每日十二点数据库备份"
```

---

### Task 3：部署到 10.1.5.28 并完成首次备份验收

**文件：**
- 部署：`/opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh`
- 创建：`/etc/shuzhi/shuzhi-backup.env`
- 部署：`/etc/systemd/system/shuzhi-postgres-backup.service`
- 部署：`/etc/systemd/system/shuzhi-postgres-backup.timer`
- 创建目录：`/var/backups/shuzhi/postgres`

**接口：**
- SSH：`root@10.1.5.28`，使用已验证的密钥认证。
- 备份服务：`shuzhi-postgres-backup.service`。
- 定时器：`shuzhi-postgres-backup.timer`。

- [ ] **步骤 1：执行远端只读预检**

```powershell
ssh -o BatchMode=yes root@10.1.5.28 'date "+%F %T %Z"; pg_dump --version; pg_restore --version; df -h /; systemctl is-active crond || true'
```

预期：时区为 `CST`，`pg_dump` 与 `pg_restore` 为 PostgreSQL 17，根分区空间充足。

- [ ] **步骤 2：创建独立账号和受限目录**

```powershell
ssh root@10.1.5.28 'id -u shuzhi-backup >/dev/null 2>&1 || useradd --system --home-dir /var/lib/shuzhi-backup --create-home --shell /sbin/nologin shuzhi-backup; install -o root -g root -m 0755 -d /opt/shuzhi/deploy/scripts /etc/shuzhi; install -o shuzhi-backup -g shuzhi-backup -m 0700 -d /var/backups/shuzhi/postgres'
```

预期：命令退出码 `0`，账号无登录 Shell，备份目录权限为 `0700`。

- [ ] **步骤 3：部署脚本和 systemd 单元**

```powershell
scp deploy/scripts/shuzhi-postgres-backup.sh root@10.1.5.28:/opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh
scp deploy/systemd/shuzhi-postgres-backup.service root@10.1.5.28:/etc/systemd/system/shuzhi-postgres-backup.service
scp deploy/systemd/shuzhi-postgres-backup.timer root@10.1.5.28:/etc/systemd/system/shuzhi-postgres-backup.timer
ssh root@10.1.5.28 'chown root:root /opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh /etc/systemd/system/shuzhi-postgres-backup.service /etc/systemd/system/shuzhi-postgres-backup.timer; chmod 0755 /opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh; chmod 0644 /etc/systemd/system/shuzhi-postgres-backup.service /etc/systemd/system/shuzhi-postgres-backup.timer; bash -n /opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh; systemd-analyze verify /etc/systemd/system/shuzhi-postgres-backup.service /etc/systemd/system/shuzhi-postgres-backup.timer'
```

预期：语法检查和 systemd 单元检查均通过。

- [ ] **步骤 4：通过标准输入安装凭据文件**

先把当前用户已提供的数据库密码放入当前 PowerShell 进程的 `SHUZHI_BACKUP_DB_PASSWORD` 环境变量，不打印其值。随后执行：

```powershell
if (-not $env:SHUZHI_BACKUP_DB_PASSWORD) { throw 'SHUZHI_BACKUP_DB_PASSWORD 未设置' }
$backupEnv = @(
  'POSTGRES_SERVER=10.1.5.28'
  'POSTGRES_PORT=5432'
  'POSTGRES_DB=zhishu_bi'
  'POSTGRES_USER=root'
  "POSTGRES_PASSWORD=$env:SHUZHI_BACKUP_DB_PASSWORD"
  'BACKUP_DIR=/var/backups/shuzhi/postgres'
  'BACKUP_RETENTION_DAYS=14'
  'PG_DUMP_BIN=/usr/bin/pg_dump'
  'PG_RESTORE_BIN=/usr/bin/pg_restore'
) -join "`n"
$backupEnv + "`n" | ssh root@10.1.5.28 'install -o root -g root -m 0600 /dev/stdin /etc/shuzhi/shuzhi-backup.env'
Remove-Item Env:SHUZHI_BACKUP_DB_PASSWORD
```

预期：`/etc/shuzhi/shuzhi-backup.env` 为 `root:root`、权限 `0600`；命令输出不包含密码。

- [ ] **步骤 5：重新加载并手动执行首次备份**

```powershell
ssh root@10.1.5.28 'systemctl daemon-reload; systemctl start shuzhi-postgres-backup.service; systemctl status shuzhi-postgres-backup.service --no-pager'
```

预期：service 状态包含 `status=0/SUCCESS`，且 timer 尚未启用。

- [ ] **步骤 6：校验备份归档、权限和日志**

```powershell
ssh root@10.1.5.28 'set -eu; latest=$(readlink -f /var/backups/shuzhi/postgres/zhishu_bi-latest.dump); test -n "$latest"; test -s "$latest"; sha256sum --check "$latest.sha256"; pg_restore --list "$latest" >/dev/null; stat -c "%A %U:%G %s %n" "$latest" "$latest.sha256" /etc/shuzhi/shuzhi-backup.env /var/backups/shuzhi/postgres; if find /var/backups/shuzhi/postgres -maxdepth 1 -type f -name "*.partial" | grep -q .; then exit 1; fi; journalctl -u shuzhi-postgres-backup.service -n 30 --no-pager'
```

预期：SHA-256 和 `pg_restore --list` 均通过，没有 `.partial` 文件；环境文件为 `0600 root:root`，备份目录为 `0700 shuzhi-backup:shuzhi-backup`，日志不包含数据库密码。

- [ ] **步骤 7：启用 timer 并验证下次执行时间**

```powershell
ssh root@10.1.5.28 'systemctl enable --now shuzhi-postgres-backup.timer; systemctl status shuzhi-postgres-backup.timer --no-pager; systemctl list-timers shuzhi-postgres-backup.timer --all --no-pager; systemctl show shuzhi-postgres-backup.timer -p TimersCalendar -p NextElapseUSecRealtime -p LastTriggerUSec'
```

预期：timer 为 `enabled` 且 `active (waiting)`，`TimersCalendar` 为 `*-*-* 12:00:00`，下次触发时间是服务器 `CST` 时区的下一个中午 12 点。

- [ ] **步骤 8：执行最终远端状态检查**

```powershell
ssh root@10.1.5.28 'systemctl is-enabled shuzhi-postgres-backup.timer; systemctl is-active shuzhi-postgres-backup.timer; systemctl show shuzhi-postgres-backup.service -p User -p Group -p EnvironmentFiles; find /var/backups/shuzhi/postgres -maxdepth 1 -type f -name "zhishu_bi-*.dump" -printf "%TY-%Tm-%Td %TH:%TM %s %p\n" | sort -r | head -n 3'
```

预期：依次输出 `enabled`、`active`，service 用户和用户组均为 `shuzhi-backup`，环境文件路径正确，并列出至少一个非空备份。
