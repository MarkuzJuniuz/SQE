@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe run_sqe.py --ai-test) else (py run_sqe.py --ai-test)
