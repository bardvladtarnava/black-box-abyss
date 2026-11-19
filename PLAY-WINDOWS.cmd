@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto python
py -3 -X utf8 play.py --launch %*
goto done
:python
python -X utf8 play.py --launch %*
:done
if errorlevel 1 pause
