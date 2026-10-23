@echo off
REM Usar Python 3.12 (o Jinja2 atual quebra no Python 3.14).
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install -r requirements.txt
pause