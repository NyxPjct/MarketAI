@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title MarketAI v0.0 - Build Comercial

echo =======================================================
echo       MarketAI v0.0 - Build Comercial para Windows
echo =======================================================
echo.

if "%MARKETAI_CLOUD_URL%"=="" (
  if "%MARKETAI_REQUIRE_CLOUD_URL%"=="1" (
    echo [ERRO] MARKETAI_CLOUD_URL e obrigatoria neste build.
    echo Defina uma URL HTTPS de producao antes de gerar o instalador comercial.
    goto :fail
  )
  echo [AVISO] MARKETAI_CLOUD_URL nao definida. Este build usara o Cloud local para desenvolvimento.
  > backend\cloud_build.py echo CLOUD_URL = "http://127.0.0.1:9000"
) else (
  echo Cloud de producao: %MARKETAI_CLOUD_URL%
  > backend\cloud_build.py echo CLOUD_URL = "%MARKETAI_CLOUD_URL%"
)

set "PYTHON_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ERRO] Python nao encontrado.
    echo Instale Python 3.11 ou 3.12 e marque "Add Python to PATH".
    goto :fail
  )
  set "PYTHON_CMD=python"
)

if not exist ".venv-desktop\Scripts\python.exe" (
  echo [1/9] Criando ambiente de build...
  %PYTHON_CMD% -m venv .venv-desktop
  if errorlevel 1 goto :fail
)

call ".venv-desktop\Scripts\activate.bat"

echo [2/9] Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements-desktop.txt
if errorlevel 1 goto :fail

echo [3/9] Executando testes e validacoes...
set PYTHONPATH=%CD%
python -m pytest -q
if errorlevel 1 goto :fail
where node >nul 2>nul
if errorlevel 1 goto :skip_node_check
node --check frontend\app.js
if errorlevel 1 goto :fail
:skip_node_check

echo [4/9] Limpando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist dist-installer rmdir /s /q dist-installer

echo [5/9] Gerando MarketAI.exe...
python -m PyInstaller --noconfirm --clean MarketAI.spec
if errorlevel 1 goto :fail

echo [6/9] Verificando assinatura digital opcional...
set "SIGNTOOL="
where signtool.exe >nul 2>nul && set "SIGNTOOL=signtool.exe"
if not defined SIGNTOOL if exist "%ProgramFiles(x86)%\Windows Kits\10\bin\x64\signtool.exe" set "SIGNTOOL=%ProgramFiles(x86)%\Windows Kits\10\bin\x64\signtool.exe"
if not defined SIGNTOOL if exist "%ProgramFiles%\Windows Kits\10\bin\x64\signtool.exe" set "SIGNTOOL=%ProgramFiles%\Windows Kits\10\bin\x64\signtool.exe"
if not defined SIGNTOOL if exist "%ProgramFiles(x86)%\Windows Kits\10\bin" for /f "delims=" %%I in ('dir /b /s "%ProgramFiles(x86)%\Windows Kits\10\bin\*\x64\signtool.exe" 2^>nul') do if not defined SIGNTOOL set "SIGNTOOL=%%I"
if not defined SIGNTOOL if exist "%ProgramFiles%\Windows Kits\10\bin" for /f "delims=" %%I in ('dir /b /s "%ProgramFiles%\Windows Kits\10\bin\*\x64\signtool.exe" 2^>nul') do if not defined SIGNTOOL set "SIGNTOOL=%%I"
set "WILL_SIGN=0"
if defined MARKETAI_SIGN_PFX if defined MARKETAI_SIGN_PASSWORD if defined SIGNTOOL set "WILL_SIGN=1"
if "%WILL_SIGN%"=="1" (
  echo Assinando MarketAI.exe...
  "%SIGNTOOL%" sign /fd SHA256 /f "%MARKETAI_SIGN_PFX%" /p "%MARKETAI_SIGN_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "dist\MarketAI.exe"
  if errorlevel 1 goto :fail
) else (
  echo Assinatura digital nao configurada. O build seguira sem Code Signing.
)

echo [7/9] Procurando Inno Setup 6...
set "ISCC="
where ISCC.exe >nul 2>nul && set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
  where winget >nul 2>nul
  if not errorlevel 1 (
    echo Inno Setup nao encontrado. Tentando instalar automaticamente...
    winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
  )
)

if not defined ISCC (
  echo.
  echo [ACAO NECESSARIA] Instale o Inno Setup 6 e rode este arquivo novamente.
  echo https://jrsoftware.org/isdl.php
  if not "%MARKETAI_CI%"=="1" pause
  exit /b 2
)

echo [8/9] Gerando instalador final...
"%ISCC%" "installer\MarketAI.iss"
if errorlevel 1 goto :fail

if not exist "dist-installer\MarketAI-Setup-v0.0.exe" (
  echo [ERRO] O instalador nao foi encontrado com o nome esperado.
  goto :fail
)

echo [9/9] Finalizando pacote...
if "%WILL_SIGN%"=="1" (
  echo Assinando MarketAI-Setup-v0.0.exe...
  "%SIGNTOOL%" sign /fd SHA256 /f "%MARKETAI_SIGN_PFX%" /p "%MARKETAI_SIGN_PASSWORD%" /tr http://timestamp.digicert.com /td SHA256 "dist-installer\MarketAI-Setup-v0.0.exe"
  if errorlevel 1 goto :fail
)

echo Gerando SHA-256 do instalador...
powershell -NoProfile -Command "$h=(Get-FileHash -Algorithm SHA256 'dist-installer\MarketAI-Setup-v0.0.exe').Hash.ToLower(); Set-Content -Encoding ASCII 'dist-installer\MarketAI-Setup-v0.0.sha256' ($h + '  MarketAI-Setup-v0.0.exe'); Write-Host ('SHA-256: ' + $h)"
if errorlevel 1 goto :fail

echo.
echo =======================================================
echo PRONTO!
echo.
echo Executavel desktop:
echo   %CD%\dist\MarketAI.exe
echo.
echo INSTALADOR COMERCIAL FINAL:
echo   %CD%\dist-installer\MarketAI-Setup-v0.0.exe
if "%WILL_SIGN%"=="1" echo   Assinatura digital: APLICADA
if not "%WILL_SIGN%"=="1" echo   Assinatura digital: NAO APLICADA

echo =======================================================
if not "%MARKETAI_CI%"=="1" (
  explorer "%CD%\dist-installer"
  pause
)
exit /b 0

:fail
echo.
echo [ERRO] O build comercial nao foi concluido. Veja as mensagens acima.
if not "%MARKETAI_CI%"=="1" pause
exit /b 1
