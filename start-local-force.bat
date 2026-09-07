@echo off
setlocal
title ChatBI - Force Local Start
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start-local-force.ps1"
set "result=%errorlevel%"
echo.
if not "%result%"=="0" echo [ERROR] Local startup failed. See the error and log paths above.
if /I not "%~1"=="--no-pause" pause
exit /b %result%
