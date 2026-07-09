param(
    [ValidateSet("start", "stop", "restart", "status")]
    [string]$Action = "start",
    [string]$AppDbName = "zhishu_bi",
    [int]$FrontendPort = 5173,
    [int]$BackendPort = 8000,
    [int]$McpPort = 8001,
    [switch]$SkipFrontend,
    [switch]$SkipBackend,
    [switch]$SkipMcp,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$workspaceRootUnix = $workspaceRoot.Replace("\", "/")
$backendRoot = Join-Path $workspaceRoot "backend"
$frontendRoot = Join-Path $workspaceRoot "frontend"
$runtimeRoot = Join-Path $workspaceRoot ".codex-runtime"
$pythonExe = Join-Path $backendRoot ".venv\Scripts\python.exe"

$appSystemDbHost = "10.1.5.28"
$appSystemDbPort = 5432
$appSystemDbUser = "root"
$appSystemDbPassword = "Password123@pg"
$coreRedisHost = "10.1.5.28"
$coreRedisPort = 6379

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeRoot "shuzhi") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeRoot "file") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeRoot "images") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeRoot "excel") | Out-Null

function Get-PortOwner([int]$Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    return $connection.OwningProcess
}

function Test-TcpPort([string]$HostName, [int]$Port, [int]$TimeoutMilliseconds = 1000) {
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

function Wait-TcpPort([int]$Port, [int]$TimeoutSeconds = 60) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-HttpStatus([string]$Url, [int]$TimeoutSeconds = 5) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        return $null
    }
}

function Set-LocalAppEnvironment {
    $env:SHUZHI_DB_HOST = $appSystemDbHost
    $env:SHUZHI_DB_PORT = [string]$appSystemDbPort
    $env:SHUZHI_DB_DB = $AppDbName
    $env:SHUZHI_DB_USER = $appSystemDbUser
    $env:SHUZHI_DB_PASSWORD = $appSystemDbPassword

    $env:POSTGRES_SERVER = $appSystemDbHost
    $env:POSTGRES_PORT = [string]$appSystemDbPort
    $env:POSTGRES_DB = $AppDbName
    $env:POSTGRES_USER = $appSystemDbUser
    $env:POSTGRES_PASSWORD = $appSystemDbPassword

    $env:SHUZHI_REDIS_HOST = $coreRedisHost
    $env:SHUZHI_REDIS_PORT = [string]$coreRedisPort
    $env:REDIS_HOST = $coreRedisHost
    $env:REDIS_PORT = [string]$coreRedisPort
    $env:CACHE_TYPE = "redis"

    $env:AUTO_RUN_MIGRATIONS = "false"
    $env:SECRET_KEY = "y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s"
    $env:FRONTEND_HOST = "http://localhost:$FrontendPort"
    $env:BACKEND_CORS_ORIGINS = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"
    $env:BASE_DIR = "$workspaceRootUnix/.codex-runtime/shuzhi"
    $env:UPLOAD_DIR = "$workspaceRootUnix/.codex-runtime/file"
    $env:MCP_IMAGE_PATH = "$workspaceRootUnix/.codex-runtime/images"
    $env:EXCEL_PATH = "$workspaceRootUnix/.codex-runtime/excel"
    $env:LOCAL_MODEL_PATH = "$workspaceRootUnix/.codex-runtime/models"
    $env:MCP_ENABLED = "false"
}

function Assert-StartupDependencies {
    if (-not $SkipBackend -or -not $SkipMcp) {
        if (-not (Test-Path -LiteralPath $pythonExe)) {
            throw "Cannot find backend Python interpreter: $pythonExe"
        }
    }
    if (-not $SkipFrontend) {
        $packageJson = Join-Path $frontendRoot "package.json"
        if (-not (Test-Path -LiteralPath $packageJson)) {
            throw "Cannot find frontend package.json: $packageJson"
        }
    }
    if (-not (Test-TcpPort -HostName $appSystemDbHost -Port $appSystemDbPort -TimeoutMilliseconds 3000)) {
        throw "Core app database is not reachable: ${appSystemDbHost}:$appSystemDbPort/$AppDbName"
    }
    if (-not (Test-TcpPort -HostName $coreRedisHost -Port $coreRedisPort -TimeoutMilliseconds 3000)) {
        throw "Core Redis is not reachable: ${coreRedisHost}:$coreRedisPort"
    }
}

function Stop-PortOwner([string]$Name, [int]$Port) {
    $owner = Get-PortOwner -Port $Port
    if (-not $owner) {
        Write-Host "$Name port $Port is not listening"
        return
    }

    $process = Get-Process -Id $owner -ErrorAction SilentlyContinue
    Stop-Process -Id $owner -Force
    if ($process) {
        $process.WaitForExit(5000)
        Write-Host "Stopped $Name port $Port pid=$owner process=$($process.ProcessName)"
    } else {
        Write-Host "Stopped $Name port $Port pid=$owner"
    }
}

function Start-UvicornService([string]$Name, [string]$AppTarget, [int]$Port, [string]$OutLog, [string]$ErrLog) {
    $owner = Get-PortOwner -Port $Port
    if ($owner) {
        Write-Host "$Name port $Port is already listening pid=$owner"
        return
    }

    Set-LocalAppEnvironment
    Remove-Item -LiteralPath $OutLog, $ErrLog -ErrorAction SilentlyContinue

    $process = Start-Process `
        -FilePath $pythonExe `
        -WorkingDirectory $backendRoot `
        -ArgumentList "-m", "uvicorn", $AppTarget, "--host", "0.0.0.0", "--port", ([string]$Port) `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -WindowStyle Hidden `
        -PassThru

    $ready = Wait-TcpPort -Port $Port -TimeoutSeconds 60
    Write-Host "$Name started launcher_pid=$($process.Id) port=$Port listening=$ready log=$ErrLog"
}

function Start-Frontend {
    $owner = Get-PortOwner -Port $FrontendPort
    if ($owner) {
        Write-Host "frontend port $FrontendPort is already listening pid=$owner"
        return
    }

    $outLog = Join-Path $runtimeRoot "frontend-$FrontendPort.current.out.log"
    $errLog = Join-Path $runtimeRoot "frontend-$FrontendPort.current.err.log"
    Remove-Item -LiteralPath $outLog, $errLog -ErrorAction SilentlyContinue

    $process = Start-Process `
        -FilePath "C:\Windows\System32\cmd.exe" `
        -WorkingDirectory $frontendRoot `
        -ArgumentList "/c", "npm run dev -- --host 0.0.0.0 --port $FrontendPort" `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru

    $ready = Wait-TcpPort -Port $FrontendPort -TimeoutSeconds 60
    Write-Host "frontend started launcher_pid=$($process.Id) port=$FrontendPort listening=$ready log=$errLog"
}

function Start-SelectedServices {
    Assert-StartupDependencies
    if (-not $SkipBackend) {
        Start-UvicornService `
            -Name "backend" `
            -AppTarget "main:app" `
            -Port $BackendPort `
            -OutLog (Join-Path $runtimeRoot "backend-$BackendPort.current.out.log") `
            -ErrLog (Join-Path $runtimeRoot "backend-$BackendPort.current.err.log")
    }
    if (-not $SkipMcp) {
        Start-UvicornService `
            -Name "mcp" `
            -AppTarget "main:mcp_app" `
            -Port $McpPort `
            -OutLog (Join-Path $runtimeRoot "backend-$McpPort.current.out.log") `
            -ErrLog (Join-Path $runtimeRoot "backend-$McpPort.current.err.log")
    }
    if (-not $SkipFrontend) {
        Start-Frontend
    }
}

function Stop-SelectedServices {
    if (-not $SkipFrontend) {
        Stop-PortOwner -Name "frontend" -Port $FrontendPort
    }
    if (-not $SkipBackend) {
        Stop-PortOwner -Name "backend" -Port $BackendPort
    }
    if (-not $SkipMcp) {
        Stop-PortOwner -Name "mcp" -Port $McpPort
    }
}

function Get-ServiceStatusRow([string]$Name, [int]$Port, [string]$Url) {
    $owner = Get-PortOwner -Port $Port
    $process = if ($owner) { Get-Process -Id $owner -ErrorAction SilentlyContinue } else { $null }
    $statusCode = if ($owner -and $Url) { Get-HttpStatus -Url $Url } else { $null }
    [pscustomobject]@{
        Service = $Name
        Port = $Port
        Listening = [bool]$owner
        Pid = $owner
        Process = if ($process) { $process.ProcessName } else { $null }
        HttpStatus = $statusCode
        Url = $Url
    }
}

function Show-SelectedStatus {
    $rows = @()
    if (-not $SkipFrontend) {
        $rows += Get-ServiceStatusRow -Name "frontend" -Port $FrontendPort -Url "http://127.0.0.1:$FrontendPort/"
    }
    if (-not $SkipBackend) {
        $rows += Get-ServiceStatusRow -Name "backend" -Port $BackendPort -Url "http://127.0.0.1:$BackendPort/api/v1/system/getLoginMethod"
    }
    if (-not $SkipMcp) {
        $rows += Get-ServiceStatusRow -Name "mcp" -Port $McpPort -Url "http://127.0.0.1:$McpPort/"
    }
    $rows | Format-Table -AutoSize
}

if ($Action -eq "status") {
    Show-SelectedStatus
    exit 0
}

if ($Action -eq "stop" -or $Action -eq "restart") {
    Stop-SelectedServices
    Start-Sleep -Seconds 2
}

if ($Action -eq "stop") {
    Show-SelectedStatus
    exit 0
}

Start-SelectedServices
Show-SelectedStatus

if (-not $NoOpen -and -not $SkipFrontend) {
    Write-Host "Open: http://127.0.0.1:$FrontendPort/"
}
