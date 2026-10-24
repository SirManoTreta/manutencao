@echo off
setlocal
cd /d "%~dp0"
REM Configuração opcional desta instalação; arquivo local ignorado pelo Git.
if exist "%~dp0run.local.bat" call "%~dp0run.local.bat"
REM Python 3.12: o Jinja2 atual quebra no Python 3.14 (bug de cache no 3.14).
py -3.12 -m app.main
pause
endlocal
