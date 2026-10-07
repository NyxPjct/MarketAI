@echo off
cd /d "%~dp0"
if not exist .venv (python -m venv .venv)
call .venv\Scriptsctivate
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
set PYTHONPATH=.
uvicorn app.main:app --reload --port 9000
