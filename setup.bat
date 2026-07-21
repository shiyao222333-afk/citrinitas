@echo off
REM ============================================================
REM Citrinitas (Rong Zhi) - one-click isolated environment setup
REM Creates venv with managed Python 3.13.12 and installs deps.
REM Pure ASCII on purpose (GBK/CP936 safe; no UTF-8 Chinese).
REM
REM Uses requirements.lock (GPU paddle build, exact pins) so the
REM result matches this machine. Do NOT install from requirements.txt
REM alone: it lists bare "paddlepaddle" (CPU baseline) and would drop
REM GPU acceleration.
REM ============================================================
setlocal
set "PROJECT_DIR=%~dp0"
set "VENV=%PROJECT_DIR%venv"
set "MANAGED_PY=C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if exist "%MANAGED_PY%" (
    set "PY=%MANAGED_PY%"
) else (
    set "PY=python"
)

if not exist "%VENV%\Scripts\python.exe" (
    echo [setup] Creating virtualenv with %PY% ...
    "%PY%" -m venv "%VENV%"
) else (
    echo [setup] venv already exists, skipping create
)

echo [setup] Upgrading pip ...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip

echo [setup] Installing from requirements.lock (GPU build, exact pins) ...
"%VENV%\Scripts\python.exe" -m pip install -r "%PROJECT_DIR%requirements.lock"

echo [setup] Done. Citrinitas venv ready at %VENV%
echo [setup] Run server : %VENV%\Scripts\python.exe run.py
echo [setup] Run UI     : %VENV%\Scripts\python.exe main.py
endlocal
