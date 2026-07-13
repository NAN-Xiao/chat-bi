param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start",
    [int]$Workers = 1,
    [string]$RedisHost = "10.1.5.28",
    [int]$RedisPort = 6379,
    [string]$QueueName = ""
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $workspaceRoot "backend"
$runtimeRoot = Join-Path $workspaceRoot ".codex-runtime"
$workerRuntime = Join-Path $runtimeRoot "task-workers"
$pythonExe = Join-Path $backendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Cannot find backend Python interpreter: $pythonExe"
}

New-Item -ItemType Directory -Force -Path $workerRuntime | Out-Null

if (-not $QueueName) {
    $workspaceSlug = Split-Path -Leaf $workspaceRoot
    $computerSlug = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { "local" }
    $QueueName = "local-$computerSlug-$workspaceSlug" -replace "[^A-Za-z0-9_.-]", "-"
}
if ($QueueName -eq "default" -or -not $QueueName.StartsWith("local-")) {
    throw "Local worker queue must start with 'local-' and cannot be 'default': $QueueName"
}

function Get-PidFile([int]$Index) {
    return Join-Path $workerRuntime "worker-$Index.pid"
}

function Get-QueueFile([int]$Index) {
    return Join-Path $workerRuntime "worker-$Index.queue"
}

function Set-WorkerEnvironment {
    $runtimeRootForEnv = $runtimeRoot.Replace("\", "/")

    $env:POSTGRES_SERVER = "10.1.5.28"
    $env:POSTGRES_PORT = "5432"
    $env:POSTGRES_DB = "zhishu_bi"
    $env:POSTGRES_USER = "root"
    $env:POSTGRES_PASSWORD = "Password123@pg"
    $env:SHUZHI_DB_HOST = "10.1.5.28"
    $env:SHUZHI_DB_PORT = "5432"
    $env:SHUZHI_DB_DB = "zhishu_bi"
    $env:SHUZHI_DB_USER = "root"
    $env:SHUZHI_DB_PASSWORD = "Password123@pg"
    $env:SECRET_KEY = "y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s"

    $env:CACHE_TYPE = "redis"
    $env:REDIS_HOST = $RedisHost
    $env:REDIS_PORT = [string]$RedisPort
    $env:SHUZHI_REDIS_HOST = $RedisHost
    $env:SHUZHI_REDIS_PORT = [string]$RedisPort
    $env:AUTO_RUN_MIGRATIONS = "false"
    $env:TASK_QUEUE_NAME = $QueueName
    $env:LLM_REQUEST_TIMEOUT = "120"
    $env:LLM_TASK_MAX_WAIT_SECONDS = "900"
    $env:LLM_MAX_RETRIES = "1"

    $env:BASE_DIR = "$runtimeRootForEnv/shuzhi"
    $env:UPLOAD_DIR = "$runtimeRootForEnv/file"
    $env:MCP_IMAGE_PATH = "$runtimeRootForEnv/images"
    $env:EXCEL_PATH = "$runtimeRootForEnv/excel"
    $env:LOCAL_MODEL_PATH = "$runtimeRootForEnv/models"
    $env:MCP_ENABLED = "false"
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
    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -LiteralPath $pidFile, (Get-QueueFile -Index $Index) -ErrorAction SilentlyContinue
        return $null
    }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction SilentlyContinue
    $commandLine = if ($processInfo) { [string]$processInfo.CommandLine } else { "" }
    if (
        -not $processInfo -or
        -not $commandLine.Contains($pythonExe) -or
        -not $commandLine.Contains("scripts.task_worker")
    ) {
        Remove-Item -LiteralPath $pidFile, (Get-QueueFile -Index $Index) -ErrorAction SilentlyContinue
        return $null
    }
    return $process
}

function Start-Worker([int]$Index) {
    $existing = Get-WorkerProcess -Index $Index
    if ($existing) {
        $queueFile = Get-QueueFile -Index $Index
        $managedQueue = if (Test-Path -LiteralPath $queueFile) {
            Get-Content -LiteralPath $queueFile -ErrorAction SilentlyContinue | Select-Object -First 1
        } else { $null }
        if ([string]$managedQueue -ne $QueueName) {
            throw "Worker $Index is already running, but its local queue cannot be verified. Run with -Action restart."
        }
        Write-Host "worker $Index already running pid=$($existing.Id) queue=$managedQueue"
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

    $pidFile = Get-PidFile -Index $Index
    $queueFile = Get-QueueFile -Index $Index
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
    Set-Content -LiteralPath $queueFile -Value $QueueName -Encoding ASCII
    Start-Sleep -Milliseconds 1000
    $process.Refresh()
    if ($process.HasExited) {
        Remove-Item -LiteralPath $pidFile, $queueFile -ErrorAction SilentlyContinue
        throw "Worker $Index exited during startup with code $($process.ExitCode). Check $stderr"
    }
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
    Remove-Item -LiteralPath (Get-QueueFile -Index $Index) -ErrorAction SilentlyContinue
}

function Show-Status {
    foreach ($i in 1..$Workers) {
        $process = Get-WorkerProcess -Index $i
        $queueFile = Get-QueueFile -Index $i
        $managedQueue = if (Test-Path -LiteralPath $queueFile) {
            Get-Content -LiteralPath $queueFile -ErrorAction SilentlyContinue | Select-Object -First 1
        } else { $null }
        if ($process -and [string]$managedQueue -ne $QueueName) {
            throw "Worker $i is running on unexpected queue '$managedQueue'; expected '$QueueName'."
        }
        [pscustomobject]@{
            Worker = $i
            Running = [bool]$process
            Pid = if ($process) { $process.Id } else { $null }
            Queue = $managedQueue
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
