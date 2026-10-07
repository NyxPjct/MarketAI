@echo off
cd /d "%~dp0desktop"
if "%MARKETAI_CLOUD_URL%"=="" (
  echo [ATENCAO] MARKETAI_CLOUD_URL nao foi definida.
  echo Defina a URL HTTPS da API comercial antes do build de producao.
  echo Exemplo: set MARKETAI_CLOUD_URL=https://api.seudominio.com
  pause
)
call build_installer.bat
