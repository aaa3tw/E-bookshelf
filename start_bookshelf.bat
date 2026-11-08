@echo off
cd /d "%~dp0"
title Acrobat Bookshelf Launcher
echo ========================================================
echo   Starting Acrobat Bookshelf
echo ========================================================
set PYTHONUTF8=1

where python >nul 2>nul
if %errorlevel% neq 0 (
    if exist "C:\Users\JamesW\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
        set "PY_CMD=C:\Users\JamesW\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    ) else (
        echo [ERROR] Python not found in PATH!
        pause
        exit /b 1
    )
) else (
    set "PY_CMD=python"
)

"%PY_CMD%" "%~dp0start_bookshelf.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Application exited with error.
    pause
)