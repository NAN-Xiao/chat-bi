param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start",
    [int[]]$BackendPorts = @(8010),
    [string]$HostAddress = "0.0.0.0",
    [ValidateSet("auto", "memory", "redis", "none")]
    [string]$CacheType = "auto",
    [string]$RedisHost = "127.0.0.1",
    [int]$RedisPort = 6379,
    [string]$FrontendHost = "http://localhost:5174",
    [string]$CorsOrigins = "",
    [switch]$StartMcp,
    [int]$McpPort = 8011,
    [switch]$ForcePortStop
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $workspaceRoot "backend"
$runtimeRoot = Join-Path $workspaceRoot ".codex-runtime"
$replicaRuntime = Join-Path $runtimeRoot "backend-replicas"
$pythonExe = Join-Path $backendRoot ".venv\Scripts\python.exe"
$runtimeRootForEnv = ($runtimeRoot -replace "\\", "/")
$localSecretKey = "chat-bi-local-dev-secret-key-keep-stable-20260620"
$localSensitiveConfigKey = "chat-bi-local-sensitive-config-key-keep-stable-20260620"

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Cannot find backend Python interpreter: $pythonExe"
}

New-Item -ItemType Directory -Force -Path $replicaRuntime | Out-Null

function Resolve-CacheType {
    if ($CacheType -ne "auto") {
        return $CacheType
    }
    if ($BackendPorts.Count -gt 1) {
        return "redis"
    }
    return "memory"
}

function Get-PortOwner([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    return $connection.OwningProcess
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
    $env:SECRET_KEY = $localSecretKey
    $env:SENSITIVE_CONFIG_ENCRYPTION_KEY = $localSensitiveConfigKey

    $env:POSTGRES_SERVER = "127.0.0.1"
    $env:POSTGRES_PORT = "15432"
    $env:POSTGRES_DB = "zhishu_bi_single_ha"
    $env:POSTGRES_USER = "root"
    $env:POSTGRES_PASSWORD = "Password123@pg"

    $env:FRONTEND_HOST = $FrontendHost
    if ($CorsOrigins) {
        $env:BACKEND_CORS_ORIGINS = $CorsOrigins
    } else {
        $env:BACKEND_CORS_ORIGINS = @(
            $FrontendHost,
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:8081",
            "http://127.0.0.1:8081"
        ) -join ","
    }

    $env:BASE_DIR = "$runtimeRootForEnv/zhishu"
    $env:UPLOAD_DIR = "$runtimeRootForEnv/file"
    $env:MCP_IMAGE_PATH = "$runtimeRootForEnv/images"
    $env:EXCEL_PATH = "$runtimeRootForEnv/excel"
    $env:LOCAL_MODEL_PATH = "$runtimeRootForEnv/models"
    $env:MCP_IMAGE_HOST = "http://localhost:3001"
    $env:MCP_ENABLED = "false"
    $env:EMBEDDING_BATCH_SIZE = "10"

    $env:CACHE_TYPE = $ResolvedCacheType
    if ($ResolvedCacheType -eq "redis") {
        $env:REDIS_HOST = $RedisHost
        $env:REDIS_PORT = [string]$RedisPort
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

foreach ($port in $BackendPorts) {
    Start-UvicornApp -Name "backend" -AppTarget "main:app" -Port $port -ResolvedCacheType $resolvedCacheType
}

if ($StartMcp) {
    Start-UvicornApp -Name "mcp" -AppTarget "main:mcp_app" -Port $McpPort -ResolvedCacheType $resolvedCacheType
}

Show-BackendStatus | Format-Table -AutoSize
