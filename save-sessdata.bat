@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  ============================================
echo   Save bilibili SESSDATA to .credentials
echo  ============================================
echo.
echo  1. Copy the SESSDATA value (or full cookie) first
echo  2. Press any key to read it from the clipboard
echo.
pause >nul
".runtime\Scripts\python.exe" scripts\save_sessdata.py
echo.
pause
