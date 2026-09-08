@echo off
chcp 65001 >nul
title GradQuestionBank

cd /d "%~dp0"

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Python virtual environment not found: %VENV_PYTHON%
    echo Please create it first: python -m venv .venv
    pause
    exit /b 1
)

echo ============================================
echo   GradQuestionBank
echo ============================================
echo.

:: Flask backend
echo [1/2] Backend (Flask :5000)...
start "GradQuestionBank - Backend" /D "%~dp0" cmd /k ""%VENV_PYTHON%" "%~dp0app.py""

timeout /t 2 /nobreak >nul

:: Vite frontend (dev mode)
echo [2/2] Frontend (Vite :3000)...
start "GradQuestionBank - Frontend" /D "%~dp0frontend" cmd /k "pnpm dev"

echo.
echo   Backend  -> http://127.0.0.1:5000
echo   Frontend -> http://127.0.0.1:3000
echo.
pause
