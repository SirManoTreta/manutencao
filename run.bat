@echo off
REM Python 3.12: o Jinja2 atual quebra no Python 3.14 (bug de cache no 3.14).
py -3.12 -m app.main
pause
