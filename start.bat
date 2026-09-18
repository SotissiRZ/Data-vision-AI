@echo off
setlocal

echo ============================================
echo   DataVision AI - Demarrage
echo ============================================

where docker >nul 2>nul
if errorlevel 1 (
    echo Docker n'est pas trouve dans le PATH. Installez/lancez Docker Desktop puis reessayez.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-datavision.ps1"
if errorlevel 1 (
    echo.
    echo Le demarrage a echoue. Voir le message ci-dessus.
    pause
    exit /b 1
)

echo.
echo DataVision AI est lance.
echo   Frontend : http://localhost:3005
echo   API      : http://localhost:8005
echo   OpenAPI  : http://localhost:8005/docs
pause
