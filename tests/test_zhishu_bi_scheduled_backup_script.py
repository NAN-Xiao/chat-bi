from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "zhishu-bi-scheduled-backup.ps1"


def run_preview(*args: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Action",
            "preview",
            *args,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_preview_defaults_to_authoritative_zhishu_bi_backup_target() -> None:
    preview = run_preview()

    assert preview["task_name"] == "ZhishuBI-Postgres-Backup"
    assert preview["host"] == "10.1.5.28"
    assert preview["port"] == 5432
    assert preview["database"] == "zhishu_bi_2.0.0"
    assert preview["user"] == "root"
    assert preview["backup_script"].endswith("tools\\postgres-backup-local.ps1")
    assert preview["task_script"].endswith("tools\\zhishu-bi-scheduled-backup.ps1")
    assert preview["trigger"] == "Daily 02:30"


def test_preview_allows_schedule_retention_and_backup_dir_overrides(tmp_path: Path) -> None:
    backup_dir = tmp_path / "pg backups"
    preview = run_preview(
        "-At",
        "03:15",
        "-RetentionDays",
        "21",
        "-BackupDir",
        str(backup_dir),
        "-TaskName",
        "custom-backup-task",
    )

    assert preview["task_name"] == "custom-backup-task"
    assert preview["trigger"] == "Daily 03:15"
    assert preview["retention_days"] == 21
    assert preview["backup_dir"] == str(backup_dir)
    assert str(backup_dir) in preview["task_arguments"]
    assert "-Action run" in preview["task_arguments"]


def test_run_keeps_control_after_backup_script_exit_and_cleans_expired_files(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    expired = backup_dir / "zhishu_bi_2.0.0-20000101_000000.dump"
    expired.write_text("old", encoding="utf-8")
    old_time = 946684800
    os.utime(expired, (old_time, old_time))

    fake_backup = tmp_path / "fake-backup.ps1"
    fake_backup.write_text(
        """
param(
    [string]$Action,
    [string]$HostAddress,
    [int]$Port,
    [string]$Database,
    [string]$User,
    [string]$Password,
    [string]$BackupDir
)
if ($Action -ne "backup") { throw "unexpected action $Action" }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
Set-Content -LiteralPath (Join-Path $BackupDir "zhishu_bi_2.0.0-new.dump") -Value "new" -Encoding ASCII
exit 0
""".strip(),
        encoding="utf-8",
    )

    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Action",
            "run",
            "-BackupScript",
            str(fake_backup),
            "-BackupDir",
            str(backup_dir),
            "-RetentionDays",
            "1",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert not expired.exists()
    assert (backup_dir / "zhishu_bi_2.0.0-new.dump").exists()
