@echo off
REM Remove a Tarefa Agendada do Heartbeat de boot. Pede permissao de administrador.

net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

schtasks /Delete /TN "TI Heartbeat Boot" /F
echo.
echo (Isso nao remove os .exe; apenas tira o heartbeat do boot.)
pause
