param(
    [ValidateSet("backup", "restore", "list")]
    [string]$Action = "backup",
    [string]$HostAddress = "10.1.5.193",
    [int]$Port = 5432,
    [string]$Database = "zhishu_bi_single_ha",
    [string]$User = "root",
    [string]$Password = "Password123@pg",
    [string]$BackupDir = "",
    [string]$File = "",
    [string]$PostgresBin = "",
    [switch]$PlainSql,
    [switch]$Clean,
    [switch]$NoOwner,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
if (-not $BackupDir) {
    $BackupDir = Join-Path $workspaceRoot ".codex-runtime\pg-backups"
}

function Resolve-PgTool([string]$Name) {
    if ($PostgresBin) {
        $candidate = Join-Path $PostgresBin "$Name.exe"
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Cannot find $Name. Add PostgreSQL bin to PATH or pass -PostgresBin."
}

function Invoke-WithPgPassword([scriptblock]$ScriptBlock) {
    $oldPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $Password
        & $ScriptBlock
    } finally {
        if ($null -eq $oldPassword) {
            Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
        } else {
            $env:PGPASSWORD = $oldPassword
        }
    }
}

function Invoke-PgTool([string]$Tool, [string[]]$Arguments) {
    Invoke-WithPgPassword {
        & $Tool @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$([System.IO.Path]::GetFileName($Tool)) failed with exit code $LASTEXITCODE"
        }
    }
}

function New-Backup {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $pgDump = Resolve-PgTool -Name "pg_dump"
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $extension = if ($PlainSql) { "sql" } else { "dump" }
    $target = if ($File) { $File } else { Join-Path $BackupDir "$Database-$timestamp.$extension" }
    $format = if ($PlainSql) { "p" } else { "c" }

    $arguments = @(
        "-h", $HostAddress,
        "-p", ([string]$Port),
        "-U", $User,
        "-d", $Database,
        "-F", $format,
        "-f", $target
    )
    if ($NoOwner) {
        $arguments += "--no-owner"
    }

    Invoke-PgTool -Tool $pgDump -Arguments $arguments
    Write-Host "Backup created: $target"
}

function Restore-Backup {
    if (-not $Force) {
        throw "Restore can overwrite local data. Re-run with -Force after confirming the target database is correct."
    }
    if (-not $File) {
        throw "Restore requires -File."
    }
    if (-not (Test-Path -LiteralPath $File)) {
        throw "Backup file not found: $File"
    }

    $extension = [System.IO.Path]::GetExtension($File).ToLowerInvariant()
    if ($PlainSql -or $extension -eq ".sql") {
        $psql = Resolve-PgTool -Name "psql"
        $arguments = @(
            "-h", $HostAddress,
            "-p", ([string]$Port),
            "-U", $User,
            "-d", $Database,
            "-f", $File
        )
        Invoke-PgTool -Tool $psql -Arguments $arguments
        Write-Host "Plain SQL restored into database: $Database"
        return
    }

    $pgRestore = Resolve-PgTool -Name "pg_restore"
    $arguments = @(
        "-h", $HostAddress,
        "-p", ([string]$Port),
        "-U", $User,
        "-d", $Database
    )
    if ($Clean) {
        $arguments += "--clean"
        $arguments += "--if-exists"
    }
    if ($NoOwner) {
        $arguments += "--no-owner"
    }
    $arguments += $File

    Invoke-PgTool -Tool $pgRestore -Arguments $arguments
    Write-Host "Custom dump restored into database: $Database"
}

function Show-Backups {
    if (-not (Test-Path -LiteralPath $BackupDir)) {
        Write-Host "Backup directory does not exist: $BackupDir"
        return
    }
    Get-ChildItem -LiteralPath $BackupDir -File |
        Where-Object { $_.Extension -in ".dump", ".sql" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object LastWriteTime, Length, FullName |
        Format-Table -AutoSize
}

if ($Action -eq "list") {
    Show-Backups
    exit 0
}

if ($Action -eq "backup") {
    New-Backup
    exit 0
}

Restore-Backup
