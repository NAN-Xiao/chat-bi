$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $workspaceRoot '.codex-runtime'
$pythonExe = Join-Path $workspaceRoot 'backend\.venv\Scripts\python.exe'
$powershellExe = (Get-Process -Id $PID).Path

function Stop-LocalListeners {
    $ports = @(5173, 8000, 8001)
    $listeners = @(Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue)
    $listeners | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize
    foreach ($processId in @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping local listener PID=$processId"
            $process | Stop-Process -Force -ErrorAction Stop
        }
    }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $remaining = @(Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue)
        if (-not $remaining) {
            Write-Host 'Ports 5173, 8000, 8001 released.'
            return
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    $remaining | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table -AutoSize
    throw 'Local ports are still occupied. Startup stopped; no other ports will be cleared.'
}

function Wait-LocalHttp([string]$Url, [int[]]$AcceptedStatus) {
    $deadline = (Get-Date).AddSeconds(90)
    do {
        $statusCode = 0
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            $statusCode = [int]$response.StatusCode
        } catch {
            if ($_.Exception.Response) { $statusCode = [int]$_.Exception.Response.StatusCode }
        }
        if ($statusCode -in $AcceptedStatus) {
            Write-Host "$Url HTTP=$statusCode"
            return
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "Service did not become ready: $Url (last HTTP status=$statusCode)."
}

function Invoke-LocalStack([string]$Action) {
    & $powershellExe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'stack-local.ps1') `
        -Action $Action -BackendPorts 8000 -QueueName $queueName -Workers 1 -StartMcp `
        -SkipDatabase -SkipRedis -SkipNginx
    if ($LASTEXITCODE -ne 0) { throw "Local stack $Action failed (exit=$LASTEXITCODE)." }
}

Push-Location $workspaceRoot
try {
    Get-Command git, npm.cmd -ErrorAction Stop | Out-Null
    foreach ($relativePath in @('backend\.venv\Scripts\python.exe', 'frontend\node_modules', 'frontend\package.json', 'tools\stack-local.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $workspaceRoot $relativePath))) {
            throw "Missing dependency: $relativePath. Install dependencies in $workspaceRoot before startup."
        }
    }
    $gitRoot = & git rev-parse --show-toplevel
    if ($LASTEXITCODE -ne 0 -or -not $gitRoot) { throw 'Cannot resolve the current Git worktree.' }
    if ([IO.Path]::GetFullPath($gitRoot.Trim()) -ne [IO.Path]::GetFullPath($workspaceRoot)) {
        throw 'The launcher must be inside the current Git worktree root.'
    }
    $branch = & git branch --show-current
    if ($LASTEXITCODE -ne 0 -or -not $branch) { throw 'Detached HEAD: select a branch before startup.' }
    Write-Host "Workspace: $workspaceRoot"
    Write-Host "Branch: $branch"
    & git fetch --prune origin
    if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed. Existing services have not been stopped.' }
    & git pull --ff-only origin $branch.Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Git pull failed. Existing services have not been stopped.' }

    $computerSlug = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { 'local' }
    $workspaceSlug = Split-Path -Leaf $workspaceRoot
    $queueName = "local-$computerSlug-$workspaceSlug" -replace '[^A-Za-z0-9_.-]', '-'
    Write-Host "Local queue: $queueName"
    $env:TASK_QUEUE_NAME = $queueName
    $env:LLM_REQUEST_TIMEOUT = '120'
    $env:LLM_TASK_MAX_WAIT_SECONDS = '900'
    $env:LLM_MAX_RETRIES = '1'

    Stop-LocalListeners
    Invoke-LocalStack -Action restart
    Start-Process -FilePath $env:ComSpec -WorkingDirectory (Join-Path $workspaceRoot 'frontend') `
        -ArgumentList '/d', '/c', 'npm run dev -- --host 0.0.0.0 --port 5173 --strictPort' `
        -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend-5173.current.out.log') `
        -RedirectStandardError (Join-Path $runtimeRoot 'frontend-5173.current.err.log') `
        -WindowStyle Hidden | Out-Null

    Wait-LocalHttp -Url 'http://127.0.0.1:5173/' -AcceptedStatus @(200)
    Wait-LocalHttp -Url 'http://127.0.0.1:8000/api/v1/system/getLoginMethod' -AcceptedStatus @(200, 401)
    Wait-LocalHttp -Url 'http://127.0.0.1:8001/' -AcceptedStatus @(200, 404)
    Invoke-LocalStack -Action status
    Get-NetTCPConnection -LocalPort 5173,8000,8001 -State Listen -ErrorAction Stop |
        Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize

    foreach ($queueFile in @('backend-replicas\backend-8000.queue', 'task-workers\worker-1.queue')) {
        $actualQueue = (Get-Content -LiteralPath (Join-Path $runtimeRoot $queueFile) -Raw).Trim()
        if ($actualQueue -ne $queueName) { throw "Queue mismatch: $queueFile uses $actualQueue." }
    }
    $workerId = [int](Get-Content -LiteralPath (Join-Path $runtimeRoot 'task-workers\worker-1.pid') -Raw).Trim()
    Get-Process -Id $workerId -ErrorAction Stop | Out-Null
    $workerLog = Join-Path $runtimeRoot 'task-workers\worker-1.err.log'
    $queuePattern = 'Task worker started:.*queue=' + [regex]::Escape($queueName) + '(\s|$)'
    if (-not (Select-String -LiteralPath $workerLog -Pattern $queuePattern -Quiet)) {
        throw "Worker startup queue was not confirmed. Check $workerLog."
    }
    Write-Host "Worker running: PID=$workerId queue=$queueName"
    Push-Location (Join-Path $workspaceRoot 'backend')
    try {
        & $pythonExe -c "from common.core.config import settings; values = (settings.LLM_REQUEST_TIMEOUT, settings.LLM_TASK_MAX_WAIT_SECONDS, settings.LLM_MAX_RETRIES); print('LLM_REQUEST_TIMEOUT=%s LLM_TASK_MAX_WAIT_SECONDS=%s LLM_MAX_RETRIES=%s' % values); assert values == (120, 900, 1), values"
        if ($LASTEXITCODE -ne 0) { throw 'LLM configuration verification failed.' }
    } finally { Pop-Location }
    Write-Host 'Local startup completed: http://localhost:5173/' -ForegroundColor Green
} catch {
    Write-Host "Local startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Logs: $runtimeRoot\frontend-5173.current.*.log"
    Write-Host "Logs: $runtimeRoot\backend-replicas\ and $runtimeRoot\task-workers\"
    exit 1
} finally { Pop-Location }
