param(
    [ValidateSet("preview", "register", "unregister", "status", "run")]
    [string]$Action = "preview",
    [string]$TaskName = "ZhishuBI-Postgres-Backup",
    [string]$At = "02:30",
    [string]$HostAddress = "10.1.5.28",
    [int]$Port = 5432,
    [string]$Database = "zhishu_bi_2.0.0",
    [string]$User = "root",
    [string]$Password = "Password123@pg",
    [string]$BackupDir = "",
    [string]$BackupScript = "",
    [string]$PostgresBin = "",
    [int]$RetentionDays = 14,
    [switch]$PlainSql,
    [switch]$NoOwner
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
if (-not $BackupScript) {
    $BackupScript = Join-Path $PSScriptRoot "postgres-backup-local.ps1"
}
if (-not $BackupDir) {
    $BackupDir = Join-Path $workspaceRoot ".codex-runtime\pg-backups"
}
$logDir = Join-Path $workspaceRoot ".codex-runtime\pg-backups\logs"

function Assert-TimeValue([string]$Value) {
    if ($Value -notmatch "^(?<hour>[01]\d|2[0-3]):(?<minute>[0-5]\d)$") {
        throw "Invalid -At value: $Value. Use 24-hour HH:mm, for example 02:30."
    }
}

function ConvertTo-CommandArgument([string]$Value) {
    if ($null -eq $Value) {
        return '""'
    }
    if ($Value -match '^[A-Za-z0-9_\-.:\\/@]+$') {
        return $Value
    }
    return '"' + ($Value -replace '"', '\"') + '"'
}

function New-TaskArguments {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (ConvertTo-CommandArgument -Value $PSCommandPath),
        "-Action", "run",
        "-TaskName", (ConvertTo-CommandArgument -Value $TaskName),
        "-HostAddress", (ConvertTo-CommandArgument -Value $HostAddress),
        "-Port", ([string]$Port),
        "-Database", (ConvertTo-CommandArgument -Value $Database),
        "-User", (ConvertTo-CommandArgument -Value $User),
        "-BackupDir", (ConvertTo-CommandArgument -Value $BackupDir),
        "-BackupScript", (ConvertTo-CommandArgument -Value $BackupScript),
        "-RetentionDays", ([string]$RetentionDays)
    )
    if ($PostgresBin) {
        $arguments += "-PostgresBin"
        $arguments += (ConvertTo-CommandArgument -Value $PostgresBin)
    }
    if ($PlainSql) {
        $arguments += "-PlainSql"
    }
    if ($NoOwner) {
        $arguments += "-NoOwner"
    }
    return ($arguments -join " ")
}

function Get-Preview {
    Assert-TimeValue -Value $At
    [pscustomobject]@{
        task_name = $TaskName
        task_script = (Resolve-Path -LiteralPath $PSCommandPath).Path
        backup_script = (Resolve-Path -LiteralPath $BackupScript).Path
        task_arguments = New-TaskArguments
        trigger = "Daily $At"
        host = $HostAddress
        port = $Port
        database = $Database
        user = $User
        backup_dir = $BackupDir
        retention_days = $RetentionDays
        log_dir = $logDir
    }
}

function Write-BackupLog([string]$Message) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $logFile = Join-Path $logDir ("zhishu-bi-backup-" + (Get-Date -Format "yyyyMMdd") + ".log")
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Remove-ExpiredBackups {
    if ($RetentionDays -le 0) {
        Write-BackupLog "Retention cleanup skipped because RetentionDays=$RetentionDays."
        return
    }
    if (-not (Test-Path -LiteralPath $BackupDir)) {
        return
    }
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $removed = 0
    Get-ChildItem -LiteralPath $BackupDir -File |
        Where-Object {
            $_.LastWriteTime -lt $cutoff -and
            $_.Name -like "$Database-*" -and
            $_.Extension -in ".dump", ".sql"
        } |
        ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            $removed += 1
            Write-BackupLog "Removed expired backup: $($_.FullName)"
        }
    Write-BackupLog "Retention cleanup finished. removed=$removed retention_days=$RetentionDays."
}

function Invoke-ZhishuBiBackup {
    if (-not (Test-Path -LiteralPath $BackupScript)) {
        throw "Backup script not found: $BackupScript"
    }
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    Write-BackupLog "Starting backup for ${HostAddress}:$Port/$Database into $BackupDir."

    $backupArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $BackupScript,
        "-Action", "backup",
        "-HostAddress", $HostAddress,
        "-Port", ([string]$Port),
        "-Database", $Database,
        "-User", $User,
        "-Password", $Password,
        "-BackupDir", $BackupDir
    )
    if ($PostgresBin) {
        $backupArgs += "-PostgresBin"
        $backupArgs += $PostgresBin
    }
    if ($PlainSql) {
        $backupArgs += "-PlainSql"
    }
    if ($NoOwner) {
        $backupArgs += "-NoOwner"
    }

    & powershell.exe @backupArgs
    if ($LASTEXITCODE -ne 0) {
        throw "postgres-backup-local.ps1 failed with exit code $LASTEXITCODE"
    }
    Write-BackupLog "Backup command finished."
    Remove-ExpiredBackups
}

function Register-BackupTask {
    Assert-TimeValue -Value $At
    $startAt = [datetime]::ParseExact($At, "HH:mm", [System.Globalization.CultureInfo]::InvariantCulture)
    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument (New-TaskArguments) -WorkingDirectory $workspaceRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $startAt
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings -Description "Scheduled backup for zhishu_bi_2.0.0 PostgreSQL database into .codex-runtime\pg-backups." -Force | Out-Null
    Write-Host "Scheduled task registered: $TaskName at $At"
}

function Show-TaskStatus {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Host "Scheduled task not found: $TaskName"
        return
    }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    [pscustomobject]@{
        TaskName = $task.TaskName
        State = $task.State
        LastRunTime = $info.LastRunTime
        LastTaskResult = $info.LastTaskResult
        NextRunTime = $info.NextRunTime
    } | Format-Table -AutoSize
}

if ($Action -eq "preview") {
    Get-Preview | ConvertTo-Json -Depth 4
    exit 0
}

if ($Action -eq "register") {
    Register-BackupTask
    exit 0
}

if ($Action -eq "unregister") {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Scheduled task unregistered: $TaskName"
    exit 0
}

if ($Action -eq "status") {
    Show-TaskStatus
    exit 0
}

Invoke-ZhishuBiBackup
