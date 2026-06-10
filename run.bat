@echo off
title Royalty Automation Dashboard
color 0B
echo.
echo  ============================================================
echo    Royalty Automation — Telangana Mines EPermit
echo  ============================================================
echo.

set PYTHON_EXE=C:\Users\kpras\AppData\Local\Python\pythoncore-3.11-64\python.exe

if not exist "%PYTHON_EXE%" (
    echo  ERROR: Python 3.11 not found at %PYTHON_EXE%
    echo  Please run setup.bat first.
    pause
    exit /b 1
)

echo  Python: %PYTHON_EXE%
echo  URL   : http://localhost:8501
echo  Press Ctrl+C in this window to stop.
echo.

%PYTHON_EXE% -m streamlit run app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo  ERROR launching dashboard. Check error above.
    pause
)
