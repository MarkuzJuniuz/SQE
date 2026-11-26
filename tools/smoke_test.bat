@echo off
REM One command for the smoke test, from any folder, with or without an active venv:
REM     tools\smoke_test.bat            (the full run)
REM     tools\smoke_test.bat --only locks
REM Uses the project's .venv; makes it and installs requirements.txt first if it is missing (needs Git for the pydcs fork).
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo No .venv found: creating it and installing the requirements...
    py -m venv .venv || goto :fail
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)
".venv\Scripts\python.exe" tools\smoke_test.py %*
exit /b %errorlevel%
:fail
echo Setup failed: see the messages above.
exit /b 1
