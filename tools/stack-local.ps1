param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "status",
    [int[]]$BackendPorts = @(8010),
    [ValidateSet("auto", "memory", "redis", "none")]
    [string]$CacheType = "auto",
    [string]$RedisHost = "127.0.0.1",
    [int]$RedisPort = 6379,
    [string]$RedisServiceName = "",
    [string]$RedisServerPath = "",
    [string]$PostgresHost = "127.0.0.1",
    [int]$PostgresPort = 15432,
    [string]$PostgresServiceName = "",
    [string]$PostgresBin = "",
    [string]$PostgresData = "",
    [string]$NginxHome = $env:NGINX_HOME,
    [int]$NginxPort = 8081,
    [switch]$StartWorker,
    [switch]$SkipWorker,
    [int]$Workers = 1,
    [switch]$StartMcp,
    [int]$McpPort = 8011,
    [switch]$SkipDatabase,
    [switch]$SkipRedis,
    [switch]$SkipNginx
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $workspaceRoot ".codex-runtime"
$stackRuntime = Join-Path $runtimeRoot "stack"
$backendScript = Join-Path $PSScriptRoot "backend-local.ps1"
$workerScript = Join-Path $PSScriptRoot "worker-local.ps1"
$nginxScript = Join-Path $PSScriptRoot "nginx-local.ps1"

New-Item -ItemType Directory -Force -Path $stackRuntime | Out-Null

function Test-TcpPort([string]$HostName, [int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1000, $false)) {
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

function Wait-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 20) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-HttpOk([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Resolve-Executable([string]$ExplicitPath, [string]$CommandName) {
    if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath)) {
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Resolve-NginxHome {
    if ($NginxHome) {
        return $NginxHome
    }
    $runtimeNginx = Join-Path $runtimeRoot "nginx-bin\nginx-1.31.1"
    if (Test-Path -LiteralPath (Join-Path $runtimeNginx "nginx.exe")) {
        return $runtimeNginx
    }
    return "D:\tools\nginx"
}

function Start-Postgres {
    if ($SkipDatabase) {
        Write-Host "Skip PostgreSQL"
        return
    }
    if (Test-TcpPort -HostName $PostgresHost -Port $PostgresPort) {
        Write-Host "PostgreSQL is listening on ${PostgresHost}:$PostgresPort"
        return
    }
    if ($PostgresServiceName) {
        Start-Service -Name $PostgresServiceName
        if (-not (Wait-TcpPort -HostName $PostgresHost -Port $PostgresPort)) {
            throw "PostgreSQL service started but port did not become ready: ${PostgresHost}:$PostgresPort"
        }
        Write-Host "PostgreSQL service started: $PostgresServiceName"
        return
    }
    if ($PostgresBin -and $PostgresData) {
        $pgCtl = Join-Path $PostgresBin "pg_ctl.exe"
        if (-not (Test-Path -LiteralPath $pgCtl)) {
            throw "Cannot find pg_ctl.exe under PostgresBin: $PostgresBin"
        }
        $logPath = Join-Path $stackRuntime "postgres.log"
        & $pgCtl -D $PostgresData -l $logPath start
        if (-not (Wait-TcpPort -HostName $PostgresHost -Port $PostgresPort)) {
            throw "PostgreSQL pg_ctl start returned but port did not become ready: ${PostgresHost}:$PostgresPort"
        }
        Write-Host "PostgreSQL started by pg_ctl"
        return
    }
    Write-Warning "PostgreSQL is not listening on ${PostgresHost}:$PostgresPort. Start it manually or pass -PostgresServiceName / -PostgresBin / -PostgresData."
}

function Stop-Postgres {
    if ($SkipDatabase) {
        return
    }
    if ($PostgresServiceName) {
        Stop-Service -Name $PostgresServiceName
        Write-Host "PostgreSQL service stopped: $PostgresServiceName"
        return
    }
    if ($PostgresBin -and $PostgresData) {
        $pgCtl = Join-Path $PostgresBin "pg_ctl.exe"
        if (Test-Path -LiteralPath $pgCtl) {
            & $pgCtl -D $PostgresData stop -m fast
            Write-Host "PostgreSQL stopped by pg_ctl"
        }
        return
    }
    Write-Host "PostgreSQL stop skipped. Pass -PostgresServiceName or -PostgresBin/-PostgresData to let the script manage it."
}

function Start-Redis {
    if ($SkipRedis) {
        Write-Host "Skip Redis"
        return
    }
    if (Test-TcpPort -HostName $RedisHost -Port $RedisPort) {
        Write-Host "Redis is listening on ${RedisHost}:$RedisPort"
        return
    }
    if ($RedisServiceName) {
        Start-Service -Name $RedisServiceName
        if (-not (Wait-TcpPort -HostName $RedisHost -Port $RedisPort)) {
            throw "Redis service started but port did not become ready: ${RedisHost}:$RedisPort"
        }
        Write-Host "Redis service started: $RedisServiceName"
        return
    }

    $redisExe = Resolve-Executable -ExplicitPath $RedisServerPath -CommandName "redis-server"
    if (-not $redisExe) {
        Write-Warning "Redis is not listening on ${RedisHost}:$RedisPort. Start it manually or pass -RedisServiceName / -RedisServerPath."
        return
    }

    $stdout = Join-Path $stackRuntime "redis.out.log"
    $stderr = Join-Path $stackRuntime "redis.err.log"
    $pidFile = Join-Path $stackRuntime "redis.pid"
    Remove-Item -LiteralPath $stdout, $stderr -ErrorAction SilentlyContinue
    $process = Start-Process `
        -FilePath $redisExe `
        -ArgumentList "--bind", $RedisHost, "--port", ([string]$RedisPort) `
        -WorkingDirectory $stackRuntime `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
    if (-not (Wait-TcpPort -HostName $RedisHost -Port $RedisPort)) {
        throw "Redis process started but port did not become ready: ${RedisHost}:$RedisPort. Check $stderr"
    }
    Write-Host "Redis started pid=$($process.Id)"
}

function Stop-Redis {
    if ($SkipRedis) {
        return
    }
    if ($RedisServiceName) {
        Stop-Service -Name $RedisServiceName
        Write-Host "Redis service stopped: $RedisServiceName"
        return
    }
    $pidFile = Join-Path $stackRuntime "redis.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $pidValue = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
        $process = if ($pidValue) { Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue } else { $null }
        if ($process) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit(5000)
            Write-Host "Redis stopped pid=$($process.Id)"
        }
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
        return
    }
    Write-Host "Redis stop skipped. It was not started by this script and no -RedisServiceName was provided."
}

function Start-Backend {
    $backendParams = @{
        Action = "start"
        BackendPorts = $BackendPorts
        CacheType = $CacheType
        RedisHost = $RedisHost
        RedisPort = $RedisPort
        FrontendHost = "http://localhost:5174"
        McpPort = $McpPort
    }
    if ($StartMcp) {
        $backendParams.StartMcp = $true
    }
    & $backendScript @backendParams
}

function Stop-Backend {
    $backendParams = @{
        Action = "stop"
        BackendPorts = $BackendPorts
        RedisHost = $RedisHost
        RedisPort = $RedisPort
        McpPort = $McpPort
    }
    if ($StartMcp) {
        $backendParams.StartMcp = $true
    }
    & $backendScript @backendParams
}

function Start-Workers {
    if ($SkipWorker) {
        return
    }
    if (-not (Test-TcpPort -HostName $RedisHost -Port $RedisPort)) {
        Write-Warning "Task worker start skipped because Redis is not listening on ${RedisHost}:$RedisPort"
        return
    }
    & $workerScript -Action start -Workers $Workers -RedisHost $RedisHost -RedisPort $RedisPort
}

function Stop-Workers {
    if ($SkipWorker) {
        return
    }
    & $workerScript -Action stop -Workers $Workers -RedisHost $RedisHost -RedisPort $RedisPort
}

function Start-Nginx {
    if ($SkipNginx) {
        Write-Host "Skip Nginx"
        return
    }
    $resolvedNginxHome = Resolve-NginxHome
    $nginxExe = Join-Path $resolvedNginxHome "nginx.exe"
    if (-not (Test-Path -LiteralPath $nginxExe)) {
        Write-Warning "Nginx not found: $nginxExe. Start skipped."
        return
    }
    & $nginxScript -Action start -NginxHome $resolvedNginxHome -ListenPort $NginxPort -BackendPorts $BackendPorts -McpPort $McpPort
}

function Stop-Nginx {
    if ($SkipNginx) {
        return
    }
    $resolvedNginxHome = Resolve-NginxHome
    $nginxExe = Join-Path $resolvedNginxHome "nginx.exe"
    if (-not (Test-Path -LiteralPath $nginxExe)) {
        Write-Host "Nginx stop skipped. Cannot find: $nginxExe"
        return
    }
    & $nginxScript -Action stop -NginxHome $resolvedNginxHome -ListenPort $NginxPort -BackendPorts $BackendPorts -McpPort $McpPort
}

function Show-StackStatus {
    $rows = @()
    if (-not $SkipDatabase) {
        $rows += [pscustomobject]@{
            Component = "postgres"
            Endpoint = "${PostgresHost}:$PostgresPort"
            State = if (Test-TcpPort -HostName $PostgresHost -Port $PostgresPort) { "listening" } else { "closed" }
        }
    }
    if (-not $SkipRedis) {
        $rows += [pscustomobject]@{
            Component = "redis"
            Endpoint = "${RedisHost}:$RedisPort"
            State = if (Test-TcpPort -HostName $RedisHost -Port $RedisPort) { "listening" } else { "closed" }
        }
    }
    foreach ($port in $BackendPorts) {
        $rows += [pscustomobject]@{
            Component = "backend"
            Endpoint = "127.0.0.1:$port"
            State = if (Test-HttpOk -Url "http://127.0.0.1:$port/health") { "healthy" } elseif (Test-TcpPort -HostName "127.0.0.1" -Port $port) { "listening" } else { "closed" }
        }
    }
    if ($StartMcp) {
        $rows += [pscustomobject]@{
            Component = "mcp"
            Endpoint = "127.0.0.1:$McpPort"
            State = if (Test-TcpPort -HostName "127.0.0.1" -Port $McpPort) { "listening" } else { "closed" }
        }
    }
    if (-not $SkipWorker) {
        foreach ($index in 1..$Workers) {
            $pidFile = Join-Path $runtimeRoot "task-workers\worker-$index.pid"
            $pidValue = if (Test-Path -LiteralPath $pidFile) { Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1 } else { $null }
            $process = if ($pidValue) { Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue } else { $null }
            $rows += [pscustomobject]@{
                Component = "worker-$index"
                Endpoint = "redis:${RedisPort}"
                State = if ($process) { "running pid=$($process.Id)" } else { "stopped" }
            }
        }
    }
    if (-not $SkipNginx) {
        $rows += [pscustomobject]@{
            Component = "nginx"
            Endpoint = "127.0.0.1:$NginxPort"
            State = if (Test-HttpOk -Url "http://127.0.0.1:$NginxPort/ready") { "ready" } elseif (Test-TcpPort -HostName "127.0.0.1" -Port $NginxPort) { "listening" } else { "closed" }
        }
    }
    $rows | Format-Table -AutoSize
}

if ($Action -eq "status") {
    Show-StackStatus
    exit 0
}

if ($Action -eq "stop" -or $Action -eq "restart") {
    Stop-Nginx
    Stop-Workers
    Stop-Backend
    Stop-Redis
    Stop-Postgres
}

if ($Action -eq "stop") {
    Show-StackStatus
    exit 0
}

Start-Postgres
Start-Redis
Start-Backend
Start-Workers
Start-Nginx
Show-StackStatus
