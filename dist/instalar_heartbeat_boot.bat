@echo off
REM Instala o Heartbeat de boot (roda como SYSTEM, antes do login).
REM 2 cliques: ele pede permissao de administrador sozinho.

net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_heartbeat_boot.ps1"
echo.
pause
