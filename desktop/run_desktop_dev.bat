@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-desktop\Scripts\python.exe" py -3 -m venv .venv-desktop
call ".venv-desktop\Scripts\activate.bat"
python -m pip install -r requirements-desktop.txt
python desktop_launcher.py
