import os
import sys
import time
import threading
from nicegui import ui, app
import requests as _r

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

# ── 日志初始化（最早执行）───────────────────────────────────────────────────────
from utils.logging_config import setup_logging
setup_logging()  # 配置控制台 + 文件日志（local_data/logs/）
logger = __import__("logging").getLogger(__name__)

# ── .env 加载 ─────────────────────────────
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ── 页面 / 共享函数 导入 ─────────────────
from utils.state import STATE
from utils.ui_shared import (
    render_chunk_card, build_left_drawer, refresh_system_state,
    set_active_collection, EMBED_PRESETS, _status_tick, set_main_loop,
)
import kb_query
import watcher

from pages.ingest import page_ingest
from pages.search import page_search
from pages.hub    import page_hub
from pages.config import page_config

# ── .env 写入辅助 ────────────────────────
def _save_env(key: str, val: str):
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={val}\n"
            found = True
            break
    if not found:
        lines.append(f"{key}={val}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

# ── 启动回调 ─────────────────────────────
@app.on_startup
def startup():
    """启动回调：只做轻量操作，不阻塞事件循环。"""
    logger.info("startup 回调开始（事件循环线程）")
    set_main_loop()
    threading.Thread(target=_auto_shutdown, daemon=True).start()
    # 启动守望文件夹 v2
    try:
        watcher.start_watcher()
        logger.info("守望文件夹 v2 已启动")
    except Exception as e:
        logger.error(f"守望文件夹 v2 启动失败: {e}")
    logger.info(f"startup 回调完成 — STATE 已有 stats={STATE.get('stats')}")


@app.on_shutdown
def shutdown():
    """关闭回调：停止守望文件夹。"""
    logger.info("停止守望文件夹 v2…")
    try:
        watcher.stop_watcher()
    except Exception as e:
        logger.error(f"守望文件夹 v2 停止异常: {e}")

def _auto_shutdown():
    CHECK = 3
    IDLE_MAX = 5  # 连续5次失败才退出（避免偶发超时误判）
    time.sleep(15)  # 启动后等15秒再开始检测（给 NiceGUI 足够的启动时间）
    idle = 0
    while True:
        time.sleep(CHECK)
        try:
            # 用 127.0.0.1 而非 localhost（Windows 下 localhost 可能走 IPv6 ::1，导致连接失败）
            _r.get("http://127.0.0.1:8080", timeout=2)
            idle = 0
        except Exception:
            idle += 1
            if idle >= IDLE_MAX:
                logger.info("浏览器已关闭，自动退出。")
                # 先优雅停止守望文件夹，释放锁和资源
                try:
                    watcher.stop_watcher()
                except Exception as e:
                    logger.warning(f"守望停止异常: {e}")
                os._exit(0)


@app.get("/health")
def _health_check():
    """绕过 NiceGUI 路由，直接测试 FastAPI 层"""
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "status": "ok",
        "qdrant_online": STATE["qdrant_online"],
        "stats": STATE.get("stats"),
        "pid": os.getpid(),
        "watcher": {
            "alive": watcher.is_watcher_alive(),
            "stats": watcher.get_watch_stats(),
        },
    })

@app.get("/reports/{filename}")
def _serve_report(filename: str):
    from fastapi.responses import FileResponse
    file_path = os.path.join(PROJECT_DIR, "local_data", "reports", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    from fastapi.responses import JSONResponse
    return JSONResponse({"error": "File not found"}, status_code=404)

# ── 主入口 ───────────────────────────────
if __name__ in {"__main__", "__mp_main__"}:
    print(f"[启动] 检查 Qdrant: {kb_query.QDRANT_URL}/collections")
    _qdrant_ok = False
    for _attempt in range(3):
        try:
            _test = _r.get(f"{kb_query.QDRANT_URL}/collections", timeout=5)
            if _test.status_code == 200:
                logger.info("✅ Qdrant 连接正常")
                _qdrant_ok = True
                break
            else:
                logger.warning(f"Qdrant 返回异常状态码: {_test.status_code}")
        except Exception as _e:
            logger.warning(f"Qdrant 连接失败 (尝试 {_attempt+1}/3): {_e}")
        if not _qdrant_ok and _attempt < 2:
            logger.info("等待 5 秒后重试...")
            import time
            time.sleep(5)

    if not _qdrant_ok:
        # 尝试通过 qdrant_helper.ps1 启动 Qdrant（真正启动，不只是检测）
        import subprocess
        _ps = os.path.join(PROJECT_DIR, "scripts", "qdrant_helper.ps1")
        logger.info("尝试启动 Qdrant...")
        try:
            _r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", _ps, "-Action", "start", "-ProjectDir", PROJECT_DIR,
                 "-MaxRetries", "30", "-RetryDelay", "2"],
                capture_output=True, text=True, timeout=80
            )
            if _r.returncode == 0:
                logger.info("✅ Qdrant 已启动")
                _qdrant_ok = True
            else:
                logger.error(f"Qdrant 启动失败，返回码: {_r.returncode}")
                if _r.stdout:
                    logger.debug(f"Qdrant 启动输出: {_r.stdout[-500:]}")
        except Exception as _e2:
            logger.error(f"自动启动 Qdrant 失败: {_e2}")

    if not _qdrant_ok:
        logger.critical("无法连接到 Qdrant，Citrinitas 不能启动。")
        logger.critical("  请确保 Qdrant 正在运行：")
        logger.critical("    1. 手动检查：打开 http://127.0.0.1:6333 看是否响应")
        logger.critical("    2. 或重新运行 run.bat（它会自动启动 Qdrant）")
        sys.exit(1)

    # 在事件循环启动前刷新状态（阻塞主线程没问题，此时事件循环还没启动）
    logger.info("刷新系统状态（ui.run 前）...")
    refresh_system_state()
    logger.info(f"状态刷新完成 — stats={STATE.get('stats')}")

    logger.info("Citrinitas 服务启动成功！")
    logger.info("  📍 Web UI:  http://127.0.0.1:8080")
    logger.info("  📍 Qdrant:  http://127.0.0.1:6333")

    # 备用浏览器开启（NiceGUI 的 webbrowser.open 在 Windows 下可能静默失败）
    def _fallback_browser():
        for i in range(30):
            time.sleep(0.5)
            try:
                _r.get("http://127.0.0.1:8080", timeout=1)
                os.startfile("http://127.0.0.1:8080")
                logger.info("浏览器已自动打开")
                break
            except Exception:
                continue
    threading.Thread(target=_fallback_browser, daemon=True).start()

    ui.run(
        title="Citrinitas · 熔知",
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=True,
        storage_secret=os.environ.get("STORAGE_SECRET", "citrinitas-dev-secret-change-me"),
    )
