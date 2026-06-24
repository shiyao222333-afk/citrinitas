# qdrant_helper.ps1 — Qdrant 自动检测 + 自动安装
# 被 run.bat Step 5 调用
# 输出：Qdrant 可执行文件路径（找到则输出路径并 exit 0；未找到输出空字符串并 exit 1）

param(
    [string]$Action = "detect",   # detect | install | health
    [string]$ProjectDir = "",
    [int]$MaxRetries = 30,        # health action: max retry count
    [int]$RetryDelay = 2          # health action: seconds between retries
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$InformationPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"

# ─────────────────────────────────────────────
# 0. 结果输出函数（写临时文件，避免 stdout 污染）
# ─────────────────────────────────────────────
function Write-DetectResult {
    param([string]$Result)
    # 写到临时文件，run.bat 会读取这个文件
    $tmpFile = Join-Path $env:TEMP "qdrant_detect_result.txt"
    Set-Content -Path $tmpFile -Value $Result -Encoding UTF8
}

function Get-EnvQdrantPath {
    param($PrjDir)
    $envFile = Join-Path $PrjDir ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^QDRANT_PATH=(.+)$') {
                return $Matches[1].Trim()
            }
        }
    }
    return $null
}

# ─────────────────────────────────────────────
# 1. 检测 Qdrant
# ─────────────────────────────────────────────
if ($Action -eq "detect") {
    # 1a. 检查 qdrant.exe 进程是否在运行
    try {
        $proc = Get-Process qdrant -ErrorAction Stop
        # 进程存在，做快速健康检查（2次重试，判断是否是僵尸）
        $healthy = $false
        for ($i = 1; $i -le 3; $i++) {
            try {
                # 用 /collections 检查 API 是否真正响应（/health 在部分版本不存在）
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:6333/collections" `
                    -Method GET -TimeoutSec 3 -UseBasicParsing `
                    -ErrorAction Stop
                if ($resp.StatusCode -eq 200) {
                    $healthy = $true
                    break
                }
            } catch { }
            if ($i -lt 3) { Start-Sleep -Seconds 1 }
        }
        if ($healthy) {
            Write-DetectResult "API_ALREADY_RUNNING"
            exit 0
        } else {
            # 进程存在但不响应 → 僵尸进程，返回路径让 run.bat 杀掉重启
            $qdrantPath = ""
            try { $qdrantPath = @($proc)[0].MainModule.FileName } catch { $qdrantPath = "" }
            if ($qdrantPath) {
                Write-DetectResult $qdrantPath
            } else {
                Write-DetectResult "ZOMBIE"
            }
            exit 0
        }
    } catch {
        # qdrant.exe 未运行，继续搜索二进制文件
    }
    $candidates = @()

    # 1b. 读取 .env 中的 QDRANT_PATH（用户手动指定路径）
    if ($ProjectDir) {
        $envPath = Get-EnvQdrantPath -PrjDir $ProjectDir
        if ($envPath -and (Test-Path $envPath)) {
            $candidates += $envPath
        }
    }

    # 1c. PATH 中查找（Get-Command）
    try {
        $inPath = (Get-Command qdrant -ErrorAction Stop).Source
        if ($inPath) { $candidates += $inPath }
    } catch {}

    # 1d. 项目本地目录（自动安装位置）
    if ($ProjectDir) {
        $localPath = Join-Path $ProjectDir "qdrant\qdrant.exe"
        if (Test-Path $localPath) { $candidates += $localPath }
    }

    # 1e. 有限递归搜索（使用环境变量，通用不依赖具体机器）
    #     搜索根目录：ProgramFiles, LOCALAPPDATA, USERPROFILE, APPDATA
    #     递归深度：2（兼顾覆盖率和速度）
    $searchRoots = @()
    if ($env:ProgramFiles)         { $searchRoots += $env:ProgramFiles }
    if (${env:ProgramFiles(x86)}) { $searchRoots += ${env:ProgramFiles(x86)} }
    if ($env:LOCALAPPDATA)        { $searchRoots += $env:LOCALAPPDATA }
    if ($env:USERPROFILE)         { $searchRoots += $env:USERPROFILE }
    if ($env:APPDATA)            { $searchRoots += $env:APPDATA }

    foreach ($root in $searchRoots) {
        if (Test-Path $root) {
            try {
                Get-ChildItem -Path $root -Filter "qdrant.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue | ForEach-Object {
                    $candidates += $_.FullName
                }
            } catch {
                # 忽略权限错误等
            }
        }
    }

    # 1f. 去重并写结果文件
    $candidates = $candidates | Select-Object -Unique
    if ($candidates.Count -gt 0) {
        Write-DetectResult $candidates[0]
        exit 0
    }

    # 未找到
    Write-DetectResult ""
    exit 1
}

# ─────────────────────────────────────────────
# 2. 安装 Qdrant（下载独立二进制文件到项目本地目录）
# ─────────────────────────────────────────────
if ($Action -eq "install") {
    $installDir = Join-Path $ProjectDir "qdrant"
    $exePath    = Join-Path $installDir "qdrant.exe"
    $cfgDir     = Join-Path $installDir "config"
    $cfgPath    = Join-Path $cfgDir "config.yaml"

    # 创建目录
    if (-not (Test-Path $installDir)) { New-Item -ItemType Directory -Path $installDir -Force | Out-Null }
    if (-not (Test-Path $cfgDir))     { New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null }

    # 获取最新版本号
    Write-Host "  Fetching latest Qdrant version..."
    try {
        $releaseInfo = Invoke-RestMethod -Uri "https://api.github.com/repos/qdrant/qdrant/releases/latest" -TimeoutSec 10 -UseBasicParsing
        $version = $releaseInfo.tag_name
    } catch {
        $version = "v1.13.4"   # 兜底版本
        Write-Host "  [!] GitHub API unreachable, using fallback version $version"
    }
    $versionNoV = $version -replace "^v", ""
    Write-Host "  Version: $versionNoV"

    # 下载 URL
    $arch = "x86_64-pc-windows-msvc"
    $url  = "https://github.com/qdrant/qdrant/releases/download/$version/qdrant-$arch.exe"
    Write-Host "  Downloading: $url"

    # 下载（显示进度）
    $progressPref = $ProgressPreference
    $ProgressPreference = "Continue"
    try {
        Invoke-WebRequest -Uri $url -OutFile $exePath -TimeoutSec 300 -UseBasicParsing
    } catch {
        # 备用：用 curl.exe
        Write-Host "  [!] Invoke-WebRequest failed, trying curl..."
        curl.exe -L -o $exePath $url
    }
    $ProgressPreference = $progressPref

    if (-not (Test-Path $exePath)) {
        Write-Host "  [ERROR] Download failed. Please install Qdrant manually."
        Write-Host "  Visit: https://github.com/qdrant/qdrant/releases"
        exit 1
    }
    Write-Host "  Downloaded to: $exePath"

    # 生成默认配置文件
    $defaultConfig = @"
# Qdrant 默认配置（由 run.bat 自动生成）
storage:
  storage_path: "$($installDir.Replace('\', '\\'))\\storage"
  on_disk_payload: true
  wal:
    wal_capacity_mb: 32
    max_segment_size_kb: 200

service:
  http_port: 6333
  grpc_port: 6334
  enable_cors: true
  host: 127.0.0.1

log_level: INFO
"@
    Set-Content -Path $cfgPath -Value $defaultConfig -Encoding UTF8
    Write-Host "  Config written to: $cfgPath"

    # 验证安装
    if (Test-Path $exePath) {
        Write-Host "  Qdrant $versionNoV installed successfully."
        Write-DetectResult $exePath
        exit 0
    } else {
        Write-Host "  [ERROR] Installed binary not found."
        exit 1
    }
}

# ─────────────────────────────────────────────
# 3. 健康检查 — 轮询 Qdrant 端口直到响应
#    参数: -MaxRetries 最大重试次数（默认 30）
#          -RetryDelay 重试间隔秒数（默认 2）
#    退出码: 0 = 健康, 1 = 超时未响应
#
#    流程: 先检查 qdrant.exe 进程是否存在
#          ↓ 不存在 → 立即失败（不浪费 60 秒轮询）
#          ↓ 存在   → TcpClient 轮询端口直到 HTTP 就绪
# ─────────────────────────────────────────────
if ($Action -eq "health") {
    # 快速检查：qdrant.exe 进程是否在运行？
    try {
        $proc = Get-Process qdrant -ErrorAction Stop
    } catch {
        Write-Host "  [ERROR] Qdrant process not running. Cannot check health."
        Write-DetectResult "UNHEALTHY"
        exit 1
    }

    # 进程存在，轮询 TcpClient 直到 HTTP 就绪
    for ($i = 1; $i -le $MaxRetries; $i++) {
        $connected = $false
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $iar = $tcp.BeginConnect("127.0.0.1", 6333, $null, $null)
            $wait = $iar.AsyncWaitHandle.WaitOne(2000)
            if ($wait) {
                $tcp.EndConnect($iar) | Out-Null
                $connected = $true
            }
            $tcp.Close()
        } catch {}

        if ($connected) {
            # 只在多轮轮询时才输出"就绪"消息（单次检查安静通过）
            if ($MaxRetries -gt 1) {
                Write-Host "  Qdrant healthy (port 6333)"
            }
            Write-DetectResult "HEALTHY"
            exit 0
        }

        # 进度消息 — 只在多轮轮询时显示
        if ($MaxRetries -gt 1) {
            Write-Host "  Waiting for Qdrant... ($i/$MaxRetries)"
        }
        if ($i -lt $MaxRetries) {
            Start-Sleep -Seconds $RetryDelay
        }
    }

    # 全部重试失败
    Write-Host "  [ERROR] Qdrant did not start within $($MaxRetries * $RetryDelay) seconds."
    Write-Host "  Please check Qdrant installation manually."
    Write-DetectResult "UNHEALTHY"
    exit 1
}

Write-Host "  [ERROR] Unknown action: $Action"
exit 1