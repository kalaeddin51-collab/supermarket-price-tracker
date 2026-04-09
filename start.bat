@echo off
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
echo Stopping any running server...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr "0.0.0.0:8000"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 >nul
echo Starting server...
C:\Users\kalae\miniconda3\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
