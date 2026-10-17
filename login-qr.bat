@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   Login by QR code - saves SESSDATA
echo ============================================
echo.

if not exist ".runtime\Scripts\python.exe" (
    echo [!] Environment not ready. Run this first:
    echo.
    echo     powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
    echo.
    echo     Or let your AI assistant read AGENTS.md and do it.
    echo.
    pause
    exit /b 1
)

echo Generating the QR code, please wait...
echo.
".runtime\Scripts\python.exe" scripts\qr_login.py --open-image
set CODE=%ERRORLEVEL%

echo.
if "%CODE%"=="0" (
    echo [OK] Saved to .credentials\sessdata.txt
    echo      Now scripts\digest.py will use native captions.
) else if "%CODE%"=="2" (
    echo [!] Not scanned. The code expired or timed out - run this file again.
    echo     If it keeps failing, use the manual method: .credentials\README.txt
) else (
    echo [!] Something went wrong. See the output above.
)
echo.
pause
