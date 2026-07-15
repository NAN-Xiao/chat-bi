# zhishu_bi systemd 定时备份设计

## 目标

在 `10.1.5.28` 上为 PostgreSQL 数据库 `zhishu_bi` 部署自动备份。备份每天按服务器 `CST` 时区的 `12:00` 精确执行，保留 14 天，并提供可追踪的运行状态、日志和完整性校验。

## 范围

- 复用并完善仓库中的 `deploy/scripts/shuzhi-postgres-backup.sh`。
- 使用 systemd oneshot service 执行备份脚本。
- 使用 systemd timer 每天触发一次备份。
- 在目标服务器完成首次手动备份和只读验收。
- 不执行生产库恢复，不修改数据库结构或业务数据。

## 连接与凭据

- 数据库主机：`127.0.0.1`
- 数据库端口：`5432`
- 数据库名称：`zhishu_bi`
- 数据库用户：`root`
- 数据库密码只保存到目标服务器的独立环境文件中，不写入 Git、Shell 脚本、systemd 单元或日志。
- 环境文件由 `root` 所有，权限设置为 `0600`，由 systemd 在启动服务时读取。

## 组件设计

### 备份脚本

备份脚本使用 `pg_dump --format=custom` 生成可由 `pg_restore` 读取的自定义格式备份，并启用 `--no-owner` 和 `--no-acl`，降低恢复到隔离演练库时的角色依赖。

脚本先写入同一备份目录下的临时文件。只有 `pg_dump` 成功且文件非空后，才将临时文件原子重命名为正式 `.dump` 文件。失败时通过退出陷阱删除未完成文件，避免残缺备份被误认为可用备份。

正式备份生成后计算 SHA-256 校验文件，并更新 `zhishu_bi-latest.dump` 及其校验文件软链接。脚本仅清理当前数据库命名空间内超过 14 天的 `.dump` 和 `.sha256` 文件，不删除其他文件。

### systemd service

service 类型为 `oneshot`，每次触发只运行一次备份脚本。服务使用无登录权限的独立系统账号运行，备份目录仅允许该账号和 `root` 访问。运行日志由 systemd journal 收集，服务失败时保留非零退出状态，便于运维检查和告警接入。

### systemd timer

timer 使用 `OnCalendar=*-*-* 12:00:00`，按目标服务器当前时区每天中午 12 点执行。配置 `Persistent=true`，服务器停机错过计划时间时，在恢复运行后补执行一次。为满足精确 12 点执行的要求，不配置随机延迟。

## 目录与命名

- 脚本：`/opt/shuzhi/deploy/scripts/shuzhi-postgres-backup.sh`
- 环境文件：`/etc/shuzhi/shuzhi-backup.env`
- service：`/etc/systemd/system/shuzhi-postgres-backup.service`
- timer：`/etc/systemd/system/shuzhi-postgres-backup.timer`
- 备份目录：`/var/backups/shuzhi/postgres`
- 备份文件：`zhishu_bi-<UTC时间戳>.dump`
- 校验文件：`zhishu_bi-<UTC时间戳>.dump.sha256`

## 错误处理

- 缺少连接参数、`pg_dump` 不存在或保留天数非法时立即退出。
- 数据库连接或导出失败时返回非零状态，并删除临时文件。
- 备份为空时拒绝发布为正式备份。
- 仅在备份成功后生成校验文件、更新软链接和清理过期备份。
- systemd journal 记录每次执行结果，不把数据库密码写入输出。

## 验收

部署后先手动启动一次 service，再执行以下只读验证：

1. service 以成功状态退出，journal 中没有错误或密码内容。
2. 备份目录中存在非空 `.dump` 文件和对应的 SHA-256 文件。
3. `sha256sum --check` 校验通过。
4. `pg_restore --list` 能读取归档目录。
5. timer 已启用且下次触发时间为服务器时区的次日 `12:00`。
6. 备份目录和环境文件权限符合设计要求。

验收过程不向 `zhishu_bi` 或任何其他数据库执行恢复。

## 回滚

出现问题时停止并禁用 timer，删除本次安装的 service、timer 和脚本后执行 `systemctl daemon-reload`。环境文件与已生成备份默认保留，只有在明确确认不再需要时才单独删除。
