@echo off
title Royalty Automation Dashboard
color 0B
echo.
echo  ============================================================
echo    Royalty Automation — Telangana Mines EPermit
echo  ============================================================
echo.

:: --- Find Python ---
set PYTHON_EXE=

:: 1. Try python_path.txt written by setup.bat
if exist "%~dp0python_path.txt" (
    set /p PYTHON_EXE=<"%~dp0python_path.txt"
    :: Remove any trailing spaces/newlines
    for /f "tokens=* delims= " %%A in ("%PYTHON_EXE%") do set PYTHON_EXE=%%A
)

:: 2. If python_path.txt missing or invalid, fall back to system python
if not exist "%PYTHON_EXE%" (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        set PYTHON_EXE=%%P
        goto :check_done
    )
)

:check_done
:: 3. Final check — if still not found, tell user to run setup.bat
if not exist "%PYTHON_EXE%" (
    echo  ERROR: Python not found on this computer.
    echo.
    echo  Please run  setup.bat  first to install everything.
    echo.
    pause
    exit /b 1
)

echo  Python : %PYTHON_EXE%
echo  URL    : http://localhost:8501
echo  Press Ctrl+C in this window to stop.
echo.

"%PYTHON_EXE%" -m streamlit run "%~dp0app.py" --server.port 8501 --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo  ERROR launching dashboard. Check error above.
    pause
)
