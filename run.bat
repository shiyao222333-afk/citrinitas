@echo off
REM ============================================================
REM  Citrinitas · 熔知 - One-Click Launcher
REM ============================================================
chcp 65001 > nul
setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo.
echo ============================================================
echo    Citrinitas - 熔知  v1.0.0
echo ============================================================
echo.

REM ============================================================
REM  Step 1: 清理旧进程
REM ============================================================
echo [1/8] Cleaning up stale processes...
for /f "tokens=5" %%a in ('netstat -ano 2^>NUL ^| findstr ":8080 " ^| findstr "LISTENING"') do (
    echo   Killing old process on port 8080 [PID %%a]
    taskkill /PID %%a /F 2>NUL
    timeout /t 2 /nobreak > nul
)
echo   OK

REM ============================================================
REM  Step 2: 检查 Python 环境 + 依赖完整性 (P1-6)
REM ============================================================
echo.
echo [2/8] Checking Python environment...

if not exist "venv\Scripts\python.exe" (
    echo   [ERROR] Virtual environment not found.
    echo   Please run: install.ps1
    pause
    exit /b 1
)

REM 关键包导入测试
echo   Verifying packages...
set "PKG_OK=1"
venv\Scripts\python.exe -c "import nicegui, qdrant_client, openai, pypdf, docx, watchdog, jieba, yaml, dotenv, paddle, paddleocr" 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo   [WARNING] Some packages are missing.
    echo   Please run: install.ps1
    set "PKG_OK=0"
)
if !PKG_OK! EQU 1 echo   All packages OK

REM ============================================================
REM  Step 3: 配置变更检测 (P2-6)
REM 首次启动或 pipe_cfg.yaml 变更时提醒重启
REM ============================================================
echo.
echo [3/8] Checking config changes...
set "CFG_FILE=%PROJECT_DIR%pipe_cfg.yaml"
set "CFG_STAMP=%PROJECT_DIR%local_data\pipe_cfg_stamp.txt"

if not exist "%CFG_FILE%" (
    echo   [^^!] pipe_cfg.yaml missing. Please run install.ps1.
    goto :skip_cfg_check
)

if not exist "%PROJECT_DIR%local_data" mkdir "%PROJECT_DIR%local_data"

REM 计算当前配置哈希，对比上次存储的哈希
powershell -Command ^
  "$cfg = [System.IO.File]::ReadAllBytes($env:CFG_FILE); $hash = [System.BitConverter]::ToString((New-Object System.Security.Cryptography.SHA256Managed).ComputeHash($cfg)).Replace('-','');" ^
  "$old=''; if (Test-Path $env:CFG_STAMP) { $old = [System.IO.File]::ReadAllText($env:CFG_STAMP).Trim() };" ^
  "if ($old -and $old -ne $hash) { Write-Host '  [NOTICE] pipe_cfg.yaml has changed since last run. Restart to apply new settings.' };" ^
  "[System.IO.File]::WriteAllText($env:CFG_STAMP, $hash)"
if %ERRORLEVEL% EQU 0 (
    echo   Config check OK
) else (
    echo   Config check skipped ^(PowerShell error^)
)

:skip_cfg_check

REM ============================================================
REM  Step 4: 检查 Ollama (P0-4)
REM ============================================================
echo.
echo [4/8] Checking Ollama...

where ollama >NUL 2>NUL
if %ERRORLEVEL% EQU 0 (
    REM Ollama installed, check if running
    ollama list >NUL 2>NUL
    if %ERRORLEVEL% EQU 0 (
        echo   Ollama is running
        echo   Checking embed model...
        ollama list 2>NUL | findstr /C:"qwen3-embedding" >NUL
        if %ERRORLEVEL% EQU 0 (
            echo   Embed model ready: qwen3-embedding
        ) else (
            echo   [^^!] Embed model not found. Please run: ollama pull qwen3-embedding:4b
        )
    ) else (
        echo   [^^!] Ollama installed but not running. Start Ollama first.
        echo   Vector embedding will not work without Ollama.
    )
) else (
    echo   [^^!] Ollama not installed. Vector embedding will not work.
    echo   Install from: https://ollama.com
)

REM  LLM API check removed -- app starts without LLM, degrades gracefully at runtime

REM ============================================================
REM  Step 5: 启动 Qdrant（自动检测 + 自动安装）
REM ============================================================
echo.
echo [5/8] Starting Qdrant...

set "QDRANT_EXE="
set "QDRANT_SKIP="

REM 5a. 调用 qdrant_helper.ps1 检测 Qdrant
REM     Result: API_ALREADY_RUNNING = already serving on port
REM             path-to-exe     = found binary
REM             (empty)         = not found
echo   Detecting Qdrant...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%scripts\qdrant_helper.ps1" -Action detect -ProjectDir "%PROJECT_DIR%" >NUL 2>&1
set "QDRANT_RESULT="
set "QDRANT_TMP=%TEMP%\qdrant_detect_result.txt"
if exist "!QDRANT_TMP!" (
    for /f "delims=" %%r in (!QDRANT_TMP!) do set "QDRANT_RESULT=%%r"
)

REM 检查检测结果
if "!QDRANT_RESULT!"=="API_ALREADY_RUNNING" (
    echo   Qdrant is already running ^(API responding on port 6333^)
    set "QDRANT_SKIP=0"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%scripts\qdrant_helper.ps1" -Action health -MaxRetries 3 -RetryDelay 2 >NUL 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo   [WARNING] Qdrant health check failed. Continuing anyway, may fail later.
    ) else (
        echo   Qdrant healthy ^(port 6333^)
    )
    goto :skip_qdrant
)

if not "!QDRANT_RESULT!"=="" (
    set "QDRANT_EXE=!QDRANT_RESULT!"
    echo   Found Qdrant: !QDRANT_EXE!
    goto :launch_qdrant
)

REM 5b. 未检测到 -> 询问用户是否自动安装
echo   [!] Qdrant not found on this system.
echo   Citrinitas needs Qdrant for vector search.
echo.
set /p QDRANT_INSTALL="  Auto-install Qdrant locally (Y/N)? [Y]: "
if "!QDRANT_INSTALL!"=="" set "QDRANT_INSTALL=Y"

if /i "!QDRANT_INSTALL!"=="Y" (
    echo   Installing Qdrant to %PROJECT_DIR%qdrant\ ...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%scripts\qdrant_helper.ps1" -Action install -ProjectDir "%PROJECT_DIR%" >NUL 2>&1
    if !ERRORLEVEL! EQU 0 (
        REM 重新检测（读临时文件）
        set "QDRANT_RESULT="
        set "QDRANT_TMP=%TEMP%\qdrant_detect_result.txt"
        if exist "!QDRANT_TMP!" (
            for /f "delims=" %%r in (!QDRANT_TMP!) do set "QDRANT_RESULT=%%r"
        )
        if not "!QDRANT_RESULT!"=="" (
            set "QDRANT_EXE=!QDRANT_RESULT!"
            echo   Qdrant installed successfully: !QDRANT_EXE!
            goto :launch_qdrant
        )
    )
    echo   [ERROR] Auto-install failed. Please install manually.
    echo   Visit: https://github.com/qdrant/qdrant/releases
    pause
    exit /b 1
) else (
    echo   [^^!] Skipping Qdrant. Vector search will be disabled.
    set "QDRANT_SKIP=1"
    goto :skip_qdrant
)

REM 5c. 启动 Qdrant
:launch_qdrant
echo   Launching Qdrant...
set "QDRANT_DIR="
for %%p in ("!QDRANT_EXE!\..") do set "QDRANT_DIR=%%~fp"

REM 构建启动命令（config 可选）
set "PS_CMD=Start-Process -FilePath '!QDRANT_EXE!' -WindowStyle Hidden"
if exist "!QDRANT_DIR!\config\config.yaml" (
    set "PS_CMD=!PS_CMD! -ArgumentList '--config-path','!QDRANT_DIR!\config\config.yaml'"
)
powershell -Command "!PS_CMD!"
set "QDRANT_SKIP=0"

REM 健康检查 — 轮询 Qdrant 端口（TcpClient，无 curl.exe 依赖）
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%scripts\qdrant_helper.ps1" -Action health -MaxRetries 30 -RetryDelay 2
if !ERRORLEVEL! NEQ 0 (
    pause
    exit /b 1
)
goto :skip_qdrant

:skip_qdrant

REM ============================================================
REM  Step 6: 守望文件夹守护进程 (A4 -- 由 main.py 内部启动)
REM ============================================================
echo.
echo [6/8] Watch folder: enabled
echo   Drop files into data\watch\ and they will be auto-ingested.
echo   data\watch_processed\ = success    data\watch_dead_letter\ = need attention

REM ============================================================
REM  Step 7: 显示配置摘要
REM ============================================================
echo.
echo [7/8] Configuration summary:
echo   Web UI:      http://127.0.0.1:8080
echo   Qdrant:      http://127.0.0.1:6333
echo   Embed model: qwen3-embedding:4b
echo   Config:      pipe_cfg.yaml ^(tuneables^) + .env ^(secrets^)
echo   Watch dir:   %PROJECT_DIR%data\watch\

REM ============================================================
REM  Step 7b: 模型预热（PaddleOCR + Ollama 嵌入）
REM ============================================================
echo.
echo [7b/8] Warming up models ^(PaddleOCR + Ollama^)...
venv\Scripts\python.exe warmup.py
if %ERRORLEVEL% EQU 0 (
    echo   Models warmed up successfully.
) else (
    echo   [^^!] Model warmup failed ^(some models may be unavailable^)
)

REM ============================================================
REM  Step 8: 启动 Web UI
REM ============================================================
echo.
echo [8/8] Starting Web UI...
echo.
echo   Press Ctrl+C to stop all services.
echo ═══════════════════════════════════════════════════════
echo.

venv\Scripts\python.exe main.py
set EXIT_CODE=%errorlevel%

echo.
echo   Web UI stopped.

REM ============================================================
REM 优雅关闭 (P2-4)
REM      shutdown order: watch daemon(stops with main) -> Web UI(stopped) -> Qdrant -> (Ollama stays)
REM ============================================================
echo.
echo Shutting down services...

REM Qdrant
tasklist /FI "IMAGENAME eq qdrant.exe" 2>NUL | find /I "qdrant.exe" >NUL
if %ERRORLEVEL% EQU 0 (
    echo   Stopping Qdrant...
    taskkill /FI "IMAGENAME eq qdrant.exe" /F 2>NUL
    echo   Qdrant stopped.
) else (
    echo   Qdrant already stopped.
)

echo.
echo ═══════════════════════════════════════════════════════
echo   All services stopped. Goodbye!
echo ═══════════════════════════════════════════════════════
pause
