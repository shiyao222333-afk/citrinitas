import os, sys, time, threading
from nicegui import ui, app
import requests as _r

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

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
import watcher_v2

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
    print("[启动] startup 回调开始（事件循环线程）", flush=True)
    set_main_loop()
    threading.Thread(target=_auto_shutdown, daemon=True).start()
    # 启动守望文件夹 v2
    try:
        watcher_v2.start_watcher_v2()
        print("[启动] 守望文件夹 v2 已启动", flush=True)
    except Exception as e:
        print(f"[启动] ⚠️ 守望文件夹 v2 启动失败: {e}", flush=True)
    print(f"[启动] startup 回调完成 — STATE 已有 stats={STATE.get('stats')}", flush=True)


@app.on_shutdown
def shutdown():
    """关闭回调：停止守望文件夹。"""
    print("[关闭] 停止守望文件夹 v2…", flush=True)
    try:
        watcher_v2.stop_watcher_v2()
    except Exception as e:
        print(f"[关闭] 守望文件夹 v2 停止异常: {e}", flush=True)

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
                print("\n[Citrinitas] 浏览器已关闭，自动退出。")
                # 先优雅停止守望文件夹，释放锁和资源
                try:
                    watcher_v2.stop_watcher_v2()
                except Exception as e:
                    print(f"[Citrinitas] 守望停止异常: {e}")
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
        "watcher_v2": {
            "alive": watcher_v2.is_watcher_v2_alive(),
            "stats": watcher_v2.get_watch_v2_stats(),
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
                print("[启动] ✅ Qdrant 连接正常", flush=True)
                _qdrant_ok = True
                break
            else:
                print(f"[启动] ⚠️ Qdrant 返回异常状态码: {_test.status_code}", flush=True)
        except Exception as _e:
            print(f"[启动] ⚠️ Qdrant 连接失败 (尝试 {_attempt+1}/3): {_e}", flush=True)
        if not _qdrant_ok and _attempt < 2:
            print("[启动] 等待 5 秒后重试...", flush=True)
            import time
            time.sleep(5)

    if not _qdrant_ok:
        # 尝试通过 qdrant_helper.ps1 启动 Qdrant
        import subprocess
        _ps = "D:\\citrinitas\\scripts\\qdrant_helper.ps1"
        _proj = "D:\\citrinitas"
        print("[启动] 尝试启动 Qdrant...", flush=True)
        try:
            _r2 = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", _ps, "-Action", "detect", "-ProjectDir", _proj],
                capture_output=True, text=True, timeout=30
            )
            _r3 = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", _ps, "-Action", "health", "-MaxRetries", "30", "-RetryDelay", "2"],
                capture_output=True, text=True, timeout=70
            )
            if _r3.returncode == 0:
                print("[启动] ✅ Qdrant 已启动", flush=True)
                _qdrant_ok = True
        except Exception as _e2:
            print(f"[启动] 自动启动 Qdrant 失败: {_e2}", flush=True)

    if not _qdrant_ok:
        print("", flush=True)
        print("=" * 60, flush=True)
        print("  ❌ 无法连接到 Qdrant，Citrinitas 不能启动。", flush=True)
        print("", flush=True)
        print("  请确保 Qdrant 正在运行：", flush=True)
        print("    1. 手动检查：打开 http://127.0.0.1:6333 看是否响应", flush=True)
        print("    2. 或重新运行 run.bat（它会自动启动 Qdrant）", flush=True)
        print("=" * 60, flush=True)
        print("", flush=True)
        sys.exit(1)

    # 在事件循环启动前刷新状态（阻塞主线程没问题，此时事件循环还没启动）
    print("[启动] 刷新系统状态（ui.run 前）…", flush=True)
    refresh_system_state()
    print(f"[启动] 状态刷新完成 — stats={STATE.get('stats')}", flush=True)

    ui.run(
        title="Citrinitas · 熔知",
        host="0.0.0.0",
        port=8080,
        reload=False,
        show=False,
        storage_secret="citrinitas-mindforge-secret",
    )
