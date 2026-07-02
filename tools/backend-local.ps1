param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start",
    [int[]]$BackendPorts = @(8000),
    [string]$HostAddress = "127.0.0.1",
    [ValidateSet("auto", "memory", "redis", "none")]
    [string]$CacheType = "auto",
    [string]$RedisHost = "10.1.5.28",
    [int]$RedisPort = 6379,
    [string]$QueueName = "",
    [string]$FrontendHost = "http://localhost:5173",
    [string]$CorsOrigins = "",
    [switch]$StartMcp,
    [int]$McpPort = 8001,
    [switch]$ForcePortStop
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $workspaceRoot "backend"
$runtimeRoot = Join-Path $workspaceRoot ".codex-runtime"
$replicaRuntime = Join-Path $runtimeRoot "backend-replicas"
$pythonExe = Join-Path $backendRoot ".venv\Scripts\python.exe"
$appSystemDbHost = "10.1.5.28"
$appSystemDbPort = 5432
$appSystemDbName = "zhishu_bi"
$biDemoDatasourcePort = 5432

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Cannot find backend Python interpreter: $pythonExe"
}

New-Item -ItemType Directory -Force -Path $replicaRuntime | Out-Null

if (-not $QueueName) {
    $workspaceSlug = Split-Path -Leaf $workspaceRoot
    $computerSlug = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { "local" }
    $QueueName = "local-$computerSlug-$workspaceSlug" -replace "[^A-Za-z0-9_.-]", "-"
}

function Resolve-CacheType {
    if ($CacheType -ne "auto") {
        return $CacheType
    }
    return "redis"
}

function Get-PortOwner([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    return $connection.OwningProcess
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMilliseconds = 5000) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-PidFile([string]$Name) {
    return Join-Path $replicaRuntime "$Name.pid"
}

function Test-BackendHealth([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-BackendReady([int]$Port, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-BackendHealth -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Set-BackendEnvironment([string]$ResolvedCacheType) {
    $runtimeRootForEnv = $runtimeRoot.Replace("\", "/")

    $env:POSTGRES_SERVER = $appSystemDbHost
    $env:POSTGRES_PORT = [string]$appSystemDbPort
    $env:POSTGRES_DB = $appSystemDbName
    $env:POSTGRES_USER = "root"
    $env:POSTGRES_PASSWORD = "Password123@pg"
    $env:SHUZHI_DB_HOST = $appSystemDbHost
    $env:SHUZHI_DB_PORT = [string]$appSystemDbPort
    $env:SHUZHI_DB_DB = $appSystemDbName
    $env:SHUZHI_DB_USER = "root"
    $env:SHUZHI_DB_PASSWORD = "Password123@pg"
    $env:SECRET_KEY = "y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s"

    $env:FRONTEND_HOST = $FrontendHost
    if ($CorsOrigins) {
        $env:BACKEND_CORS_ORIGINS = $CorsOrigins
    } else {
        $env:BACKEND_CORS_ORIGINS = @(
            $FrontendHost,
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080"
        ) -join ","
    }

    $env:BASE_DIR = "$runtimeRootForEnv/shuzhi"
    $env:UPLOAD_DIR = "$runtimeRootForEnv/file"
    $env:MCP_IMAGE_PATH = "$runtimeRootForEnv/images"
    $env:EXCEL_PATH = "$runtimeRootForEnv/excel"
    $env:LOCAL_MODEL_PATH = "$runtimeRootForEnv/models"
    $env:MCP_ENABLED = "false"
    $env:AUTO_RUN_MIGRATIONS = "false"
    $env:TASK_QUEUE_NAME = $QueueName

    $env:CACHE_TYPE = $ResolvedCacheType
    if ($ResolvedCacheType -eq "redis") {
        $env:REDIS_HOST = $RedisHost
        $env:REDIS_PORT = [string]$RedisPort
        $env:SHUZHI_REDIS_HOST = $RedisHost
        $env:SHUZHI_REDIS_PORT = [string]$RedisPort
    }
}

function Assert-AppSystemDatabaseReady {
    if ($env:POSTGRES_SERVER -eq "127.0.0.1" -and [int]$env:POSTGRES_PORT -eq $biDemoDatasourcePort) {
        throw "Invalid backend system database endpoint: local 127.0.0.1:5432 is reserved for BI/tracking demo datasources. The app system database must be ${appSystemDbHost}:$appSystemDbPort/$appSystemDbName."
    }
    if ($env:POSTGRES_SERVER -ne $appSystemDbHost -or [int]$env:POSTGRES_PORT -ne $appSystemDbPort -or $env:POSTGRES_DB -ne $appSystemDbName) {
        throw "Invalid backend system database settings: POSTGRES_SERVER=$env:POSTGRES_SERVER POSTGRES_PORT=$env:POSTGRES_PORT POSTGRES_DB=$env:POSTGRES_DB. Use ${appSystemDbHost}:$appSystemDbPort/$appSystemDbName for the app system database; local 127.0.0.1:5432 is for BI/tracking datasources."
    }
    if (-not (Test-TcpPort -HostName $appSystemDbHost -Port $appSystemDbPort)) {
        throw "App system database is not listening on ${appSystemDbHost}:$appSystemDbPort. Verify the remote core system DB is reachable; do not point backend startup at local 127.0.0.1:5432 BI/tracking datasources."
    }

    $checkScript = @"
import os
import sys
import psycopg2

try:
    conn = psycopg2.connect(
        host=os.environ["POSTGRES_SERVER"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=3,
    )
    cur = conn.cursor()
    cur.execute(
        "select current_database(), "
        "exists (select 1 from information_schema.tables where table_schema='public' and table_name='core_datasource'), "
        "exists (select 1 from information_schema.tables where table_schema='public' and table_name='sys_tenant'), "
        "exists (select 1 from information_schema.tables where table_schema='public' and table_name='sys_user'), "
        "coalesce((select count(*) from core_dashboard), 0)"
    )
    database_name, has_core_datasource, has_sys_tenant, has_sys_user, dashboard_count = cur.fetchone()
    conn.close()
    if (
        database_name != "zhishu_bi"
        or not has_core_datasource
        or not has_sys_tenant
        or not has_sys_user
        or int(dashboard_count or 0) <= 0
    ):
        print(
            "unexpected app system database: "
            f"database={database_name}, core_datasource={has_core_datasource}, "
            f"sys_tenant={has_sys_tenant}, sys_user={has_sys_user}, "
            f"dashboards={dashboard_count}",
            file=sys.stderr,
        )
        sys.exit(2)
except Exception as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)
"@
    $checkScriptPath = Join-Path $replicaRuntime "check-app-system-db.py"
    Set-Content -LiteralPath $checkScriptPath -Value $checkScript -Encoding UTF8
    try {
        & $pythonExe $checkScriptPath
        if ($LASTEXITCODE -ne 0) {
            throw "App system database check failed for ${appSystemDbHost}:$appSystemDbPort/$appSystemDbName. Verify the core system DB is reachable and not confused with a BI datasource."
        }
    } finally {
        Remove-Item -LiteralPath $checkScriptPath -ErrorAction SilentlyContinue
    }
}

function Start-UvicornApp([string]$Name, [string]$AppTarget, [int]$Port, [string]$ResolvedCacheType) {
    $owner = Get-PortOwner -Port $Port
    if ($owner) {
        $healthy = Test-BackendHealth -Port $Port
        Write-Host "$Name port $Port is already listening by pid $owner. healthy=$healthy"
        return
    }

    Set-BackendEnvironment -ResolvedCacheType $ResolvedCacheType

    $stdout = Join-Path $replicaRuntime "$Name-$Port.out.log"
    $stderr = Join-Path $replicaRuntime "$Name-$Port.err.log"
    Remove-Item -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue

    $process = Start-Process `
        -FilePath $pythonExe `
        -WorkingDirectory $backendRoot `
        -ArgumentList "-m", "uvicorn", $AppTarget, "--host", $HostAddress, "--port", ([string]$Port), "--proxy-headers" `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    if ($AppTarget -eq "main:app") {
        $ready = Wait-BackendReady -Port $Port
        $owner = Get-PortOwner -Port $Port
        if ($owner) {
            Set-Content -LiteralPath (Get-PidFile -Name "$Name-$Port") -Value $owner -Encoding ASCII
        } else {
            Set-Content -LiteralPath (Get-PidFile -Name "$Name-$Port") -Value $process.Id -Encoding ASCII
        }
        Write-Host "$Name $Port started launcher_pid=$($process.Id) listen_pid=$owner ready=$ready"
        if (-not $ready) {
            Write-Warning "Backend $Port did not become ready within timeout. Check $stderr"
        }
    } else {
        Start-Sleep -Seconds 1
        $owner = Get-PortOwner -Port $Port
        if ($owner) {
            Set-Content -LiteralPath (Get-PidFile -Name "$Name-$Port") -Value $owner -Encoding ASCII
        } else {
            Set-Content -LiteralPath (Get-PidFile -Name "$Name-$Port") -Value $process.Id -Encoding ASCII
        }
        Write-Host "$Name $Port started launcher_pid=$($process.Id) listen_pid=$owner"
    }
}

function Stop-ByPidFile([string]$Name, [int]$Port) {
    $pidFile = Get-PidFile -Name "$Name-$Port"
    $stopped = $false
    if (Test-Path -LiteralPath $pidFile) {
        $pidValue = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($pidValue) {
            $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
            if ($process) {
                Stop-Process -Id $process.Id -Force
                $process.WaitForExit(5000)
                Write-Host "Stopped $Name $Port pid=$($process.Id)"
                $stopped = $true
            }
        }
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    }

    if (-not $stopped -and ($ForcePortStop -or $Action -eq "restart")) {
        $owner = Get-PortOwner -Port $Port
        if ($owner) {
            $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
            Stop-Process -Id $owner -Force
            if ($process) {
                $process.WaitForExit(5000)
            }
            Write-Host "Stopped process on port $Port pid=$owner"
        }
    }
}

function Show-BackendStatus {
    foreach ($port in $BackendPorts) {
        $owner = Get-PortOwner -Port $port
        [pscustomobject]@{
            Name = "backend"
            Port = $port
            Listening = [bool]$owner
            Pid = $owner
            Healthy = if ($owner) { Test-BackendHealth -Port $port } else { $false }
            PidFile = Get-PidFile -Name "backend-$port"
        }
    }
    if ($StartMcp -or $Action -eq "status") {
        $owner = Get-PortOwner -Port $McpPort
        [pscustomobject]@{
            Name = "mcp"
            Port = $McpPort
            Listening = [bool]$owner
            Pid = $owner
            Healthy = [bool]$owner
            PidFile = Get-PidFile -Name "mcp-$McpPort"
        }
    }
}

$resolvedCacheType = Resolve-CacheType

if ($Action -eq "status") {
    Show-BackendStatus | Format-Table -AutoSize
    exit 0
}

if ($Action -eq "stop" -or $Action -eq "restart") {
    foreach ($port in $BackendPorts) {
        Stop-ByPidFile -Name "backend" -Port $port
    }
    if ($StartMcp) {
        Stop-ByPidFile -Name "mcp" -Port $McpPort
    }
}

if ($Action -eq "stop") {
    exit 0
}

Write-Host "Starting backend ports: $($BackendPorts -join ',') cache=$resolvedCacheType"
if ($BackendPorts.Count -gt 1 -and $resolvedCacheType -ne "redis") {
    Write-Warning "Multiple backend replicas should use CACHE_TYPE=redis for shared cache state."
}

Set-BackendEnvironment -ResolvedCacheType $resolvedCacheType
Assert-AppSystemDatabaseReady

foreach ($port in $BackendPorts) {
    Start-UvicornApp -Name "backend" -AppTarget "main:app" -Port $port -ResolvedCacheType $resolvedCacheType
}

if ($StartMcp) {
    Start-UvicornApp -Name "mcp" -AppTarget "main:mcp_app" -Port $McpPort -ResolvedCacheType $resolvedCacheType
}

Show-BackendStatus | Format-Table -AutoSize
