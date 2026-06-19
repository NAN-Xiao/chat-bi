param(
    [ValidateSet("start", "reload", "stop", "test")]
    [string]$Action = "start",
    [string]$NginxHome = $env:NGINX_HOME,
    [int]$ListenPort = 8081,
    [int[]]$BackendPorts = @(8010),
    [int]$McpPort = 8011
)

$ErrorActionPreference = "Stop"

function To-NginxPath([string]$Path) {
    return ($Path -replace "\\", "/")
}

$workspaceRoot = Split-Path -Parent $PSScriptRoot
if (-not $NginxHome) {
    $NginxHome = "D:\tools\nginx"
}

$nginxExe = Join-Path $NginxHome "nginx.exe"
if (-not (Test-Path -LiteralPath $nginxExe)) {
    throw "Cannot find nginx.exe. Set NGINX_HOME or pass -NginxHome. Current path: $nginxExe"
}

$templatePath = Join-Path $workspaceRoot "deploy\nginx\nginx.local.conf.template"
$frontendDist = Join-Path $workspaceRoot "frontend\dist"
$runtimeDir = Join-Path $workspaceRoot ".codex-runtime\nginx"
$generatedConf = Join-Path $runtimeDir "nginx.conf"
$mimeTypes = Join-Path $NginxHome "conf\mime.types"

if (-not (Test-Path -LiteralPath $templatePath)) {
    throw "Cannot find Nginx config template: $templatePath"
}
if (-not (Test-Path -LiteralPath $mimeTypes)) {
    throw "Cannot find mime.types under Nginx home: $mimeTypes"
}
if (-not (Test-Path -LiteralPath $frontendDist)) {
    Write-Warning "frontend/dist does not exist. Run npm run build in frontend before serving production static files."
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$servers = ($BackendPorts | ForEach-Object {
    "        server 127.0.0.1:$($_) max_fails=2 fail_timeout=10s;"
}) -join "`n"

$config = Get-Content -LiteralPath $templatePath -Raw
$config = $config.Replace("__RUNTIME_DIR__", (To-NginxPath $runtimeDir))
$config = $config.Replace("__MIME_TYPES__", (To-NginxPath $mimeTypes))
$config = $config.Replace("__FRONTEND_DIST__", (To-NginxPath $frontendDist))
$config = $config.Replace("__LISTEN_PORT__", [string]$ListenPort)
$config = $config.Replace("__BACKEND_UPSTREAM_SERVERS__", $servers)
$config = $config.Replace("__MCP_PORT__", [string]$McpPort)
[System.IO.File]::WriteAllText($generatedConf, $config, [System.Text.UTF8Encoding]::new($false))

$prefix = To-NginxPath $NginxHome
$conf = To-NginxPath $generatedConf

if ($Action -eq "test") {
    & $nginxExe -p $prefix -c $conf -t
    exit $LASTEXITCODE
}

if ($Action -eq "stop") {
    & $nginxExe -p $prefix -c $conf -s stop
    exit $LASTEXITCODE
}

if ($Action -eq "reload") {
    & $nginxExe -p $prefix -c $conf -t
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & $nginxExe -p $prefix -c $conf -s reload
    exit $LASTEXITCODE
}

& $nginxExe -p $prefix -c $conf -t
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$running = Get-Process nginx -ErrorAction SilentlyContinue
if ($running) {
    & $nginxExe -p $prefix -c $conf -s reload
} else {
    Start-Process -FilePath $nginxExe -ArgumentList "-p", $prefix, "-c", $conf -WorkingDirectory $NginxHome -WindowStyle Hidden
}

Write-Host "Nginx is serving http://127.0.0.1:$ListenPort"
Write-Host "Generated config: $generatedConf"
