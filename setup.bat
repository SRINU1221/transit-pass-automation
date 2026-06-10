@echo off
title Royalty Automation — Setup
color 0A
echo.
echo  ============================================================
echo    Royalty Automation - First Time Setup
echo  ============================================================
echo.

:: Try multiple common Python paths
set PYTHON_EXE=
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "C:\Python39\python.exe"
) do (
    if exist %%P (
        set PYTHON_EXE=%%P
        goto :found_python
    )
)

echo  ERROR: Python not found!
echo.
echo  Please install Python 3.10 or newer from:
echo  https://www.python.org/downloads/
echo.
echo  IMPORTANT: During installation, CHECK the box:
echo  "Add Python to PATH"
echo.
pause
exit /b 1

:found_python
echo  [OK] Python found at: %PYTHON_EXE%
echo.

:: Install packages
echo  Installing required packages...
%PYTHON_EXE% -m pip install streamlit pandas openpyxl playwright xlsxwriter Pillow --upgrade -q
if errorlevel 1 (
    echo  ERROR: Package install failed. Check internet connection.
    pause
    exit /b 1
)
echo  [OK] Packages installed.
echo.

:: Install Playwright Chromium browser
echo  Installing Playwright Chromium browser...
%PYTHON_EXE% -m playwright install chromium
if errorlevel 1 (
    echo  ERROR: Playwright browser install failed.
    pause
    exit /b 1
)
echo  [OK] Browser installed.
echo.

:: Save python path for run.bat
echo %PYTHON_EXE% > python_path.txt

echo  ============================================================
echo    Setup Complete!
echo    Now double-click  run.bat  to start the dashboard.
echo  ============================================================
echo.
pause
