param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start",
    [int]$Workers = 1,
    [string]$PostgresHost = "10.1.5.193",
    [int]$PostgresPort = 5432,
    [string]$PostgresDatabase = "zhishu_bi_single_ha",
    [string]$PostgresUser = "root",
    [string]$PostgresPassword = "Password123@pg",
    [string]$RedisHost = "127.0.0.1",
    [int]$RedisPort = 6379,
    [string]$QueueName = "default"
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $workspaceRoot "backend"
$runtimeRoot = Join-Path $workspaceRoot ".codex-runtime"
$workerRuntime = Join-Path $runtimeRoot "task-workers"
$pythonExe = Join-Path $backendRoot ".venv\Scripts\python.exe"
$runtimeRootForEnv = ($runtimeRoot -replace "\\", "/")
$localSecretKey = "chat-bi-local-dev-secret-key-keep-stable-20260620"
$localSensitiveConfigKey = "chat-bi-local-sensitive-config-key-keep-stable-20260620"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Cannot find backend Python interpreter: $pythonExe"
}

New-Item -ItemType Directory -Force -Path $workerRuntime | Out-Null

function Get-PidFile([int]$Index) {
    return Join-Path $workerRuntime "worker-$Index.pid"
}

function Set-WorkerEnvironment {
    $env:SECRET_KEY = $localSecretKey
    $env:SENSITIVE_CONFIG_ENCRYPTION_KEY = $localSensitiveConfigKey

    $env:POSTGRES_SERVER = $PostgresHost
    $env:POSTGRES_PORT = [string]$PostgresPort
    $env:POSTGRES_DB = $PostgresDatabase
    $env:POSTGRES_USER = $PostgresUser
    $env:POSTGRES_PASSWORD = $PostgresPassword

    $env:CACHE_TYPE = "redis"
    $env:REDIS_HOST = $RedisHost
    $env:REDIS_PORT = [string]$RedisPort
    $env:TASK_QUEUE_NAME = $QueueName

    $env:BASE_DIR = "$runtimeRootForEnv/zhishu"
    $env:UPLOAD_DIR = "$runtimeRootForEnv/file"
    $env:MCP_IMAGE_PATH = "$runtimeRootForEnv/images"
    $env:EXCEL_PATH = "$runtimeRootForEnv/excel"
    $env:LOCAL_MODEL_PATH = "$runtimeRootForEnv/models"
    $env:MCP_IMAGE_HOST = "http://localhost:3001"
    $env:MCP_ENABLED = "false"
    $env:EMBEDDING_BATCH_SIZE = "10"
}

function Get-WorkerProcess([int]$Index) {
    $pidFile = Get-PidFile -Index $Index
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return $null
    }
    $pidValue = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pidValue) {
        return $null
    }
    return Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
}

function Start-Worker([int]$Index) {
    $existing = Get-WorkerProcess -Index $Index
    if ($existing) {
        Write-Host "worker $Index already running pid=$($existing.Id)"
        return
    }

    Set-WorkerEnvironment

    $stdout = Join-Path $workerRuntime "worker-$Index.out.log"
    $stderr = Join-Path $workerRuntime "worker-$Index.err.log"
    Remove-Item -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue

    $process = Start-Process `
        -FilePath $pythonExe `
        -WorkingDirectory $backendRoot `
        -ArgumentList "-m", "scripts.task_worker" `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -LiteralPath (Get-PidFile -Index $Index) -Value $process.Id -Encoding ASCII
    Write-Host "worker $Index started pid=$($process.Id)"
}

function Stop-Worker([int]$Index) {
    $process = Get-WorkerProcess -Index $Index
    if ($process) {
        Stop-Process -Id $process.Id -Force
        $process.WaitForExit(5000)
        Write-Host "worker $Index stopped pid=$($process.Id)"
    }
    Remove-Item -LiteralPath (Get-PidFile -Index $Index) -ErrorAction SilentlyContinue
}

function Show-Status {
    foreach ($i in 1..$Workers) {
        $process = Get-WorkerProcess -Index $i
        [pscustomobject]@{
            Worker = $i
            Running = [bool]$process
            Pid = if ($process) { $process.Id } else { $null }
            PidFile = Get-PidFile -Index $i
        }
    }
}

if ($Action -eq "status") {
    Show-Status | Format-Table -AutoSize
    exit 0
}

if ($Action -eq "stop" -or $Action -eq "restart") {
    foreach ($i in 1..$Workers) {
        Stop-Worker -Index $i
    }
}

if ($Action -eq "stop") {
    exit 0
}

foreach ($i in 1..$Workers) {
    Start-Worker -Index $i
}

Show-Status | Format-Table -AutoSize
