@echo off
REM Remove a Tarefa Agendada do Monitor de TI. Pede permissao de administrador.

net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

schtasks /Delete /TN "TI Monitor Manutencao" /F
echo.
echo (Isso nao remove os .exe; apenas tira o inicio automatico.)
pause
