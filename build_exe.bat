@echo off
REM Builds dist\SQE\SQE.exe.  Run from the project folder with the venv active (see docs\GUIDE.md).
cd /d "%~dp0"
python -m pip install -r requirements-build.txt || goto :err
python -m PyInstaller --noconfirm --clean --windowed --name SQE ^
  --collect-all dcs --collect-submodules sqe run_sqe.py || goto :err
echo.
echo Built: dist\SQE\SQE.exe   (copy the whole dist\SQE folder, not just the .exe)
exit /b 0
:err
echo Build failed. See docs\GUIDE.md, section "Troubleshooting".
exit /b 1
