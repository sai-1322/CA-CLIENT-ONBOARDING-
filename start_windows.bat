@echo off
REM Double-click this file to start the app. Keep the window open while you use it.
cd /d "%~dp0"

set PY=python
where py >nul 2>nul && set PY=py

if not exist ".venv\Scripts\python.exe" (
  echo First-time setup. This takes a few minutes, and needs internet.
  %PY% -m venv .venv
  if errorlevel 1 goto failed
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)

echo.
echo Starting the app. Your browser will open at http://127.0.0.1:8000
echo To stop the app, close this window or press Ctrl+C.
echo.
.venv\Scripts\python.exe run.py
goto end

:failed
echo.
echo Setup did not finish. Read the message above.
echo If it says "not recognized", install Python from python.org and tick "Add python.exe to PATH".
echo If the folder is on a network drive (Z: or \\server), copy it to your C: drive first.
pause

:end
