# Windows 本地 Nginx 运行说明

本地开发建议先用 Nginx zip 版，不占用 80 端口，默认监听 `8080`。

## 安装

从 Nginx 官网下载 Windows zip 版并解压，例如：

```powershell
D:\tools\nginx
```

也可以设置环境变量：

```powershell
$env:NGINX_HOME = "D:\tools\nginx"
```

## 启动

先确认后端已经启动，单副本用 `8000`：

```powershell
.\tools\nginx-local.ps1 -Action start -NginxHome "D:\tools\nginx" -ListenPort 8080 -BackendPorts 8000
```

多副本时：

```powershell
.\tools\nginx-local.ps1 -Action start -NginxHome "D:\tools\nginx" -ListenPort 8080 -BackendPorts 8000,8002,8003
```

后端可以用本地脚本启动。开发单副本：

```powershell
.\tools\backend-local.ps1 -Action start -BackendPorts 8000
```

多副本压测/生产模拟：

```powershell
.\tools\backend-local.ps1 -Action start -BackendPorts 8000,8002,8003 -CacheType redis
.\tools\nginx-local.ps1 -Action reload -NginxHome "D:\tools\nginx" -ListenPort 8080 -BackendPorts 8000,8002,8003
```

配置会生成到：

```text
.codex-runtime/nginx/nginx.conf
```

## 验证

```powershell
Invoke-WebRequest http://127.0.0.1:8080/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8080/ready -UseBasicParsing
```

## 管理

```powershell
.\tools\nginx-local.ps1 -Action test -NginxHome "D:\tools\nginx"
.\tools\nginx-local.ps1 -Action reload -NginxHome "D:\tools\nginx"
.\tools\nginx-local.ps1 -Action stop -NginxHome "D:\tools\nginx"
```

`8080` 是本地建议端口，因为这台机器的 `80` 端口已经被系统进程占用。
