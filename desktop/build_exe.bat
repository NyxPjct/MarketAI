@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title MarketAI v0.0 - Build EXE
where py >nul 2>nul || (echo Python nao encontrado.& pause & exit /b 1)
if not exist ".venv-desktop\Scripts\python.exe" py -3 -m venv .venv-desktop
call ".venv-desktop\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt || goto :fail
set PYTHONPATH=%CD%
python -m pytest -q || goto :fail
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --clean MarketAI.spec || goto :fail
echo.
echo Criado: %CD%\dist\MarketAI.exe
explorer "%CD%\dist"
pause
exit /b 0
:fail
echo Build interrompido.
pause
exit /b 1
