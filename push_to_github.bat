@echo off
chcp 65001 >nul
title Push E-bookshelf to GitHub

echo ========================================================
echo   Pushing E-bookshelf to GitHub (aaa3tw)
echo ========================================================
echo.
cd /d "%~dp0"

echo [1/2] Checking git status...
git status
echo.

echo [2/2] Pushing to https://github.com/aaa3tw/E-bookshelf.git ...
echo (If prompted, please click 'Sign in with your browser' to authorize)
echo.
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [SUCCESS] Successfully pushed to GitHub!
    echo   Repository: https://github.com/aaa3tw/E-bookshelf
    echo ========================================================
) else (
    echo.
    echo [ERROR] Push failed. Please check your GitHub permissions or network.
)

echo.
pause
