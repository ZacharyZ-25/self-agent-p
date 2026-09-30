@echo off
cd /d "%~dp0"
backend\.venv\Scripts\python.exe scripts\start-local-kb.py
if errorlevel 1 pause
