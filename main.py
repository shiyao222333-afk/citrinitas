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
    set_active_collection, EMBED_PRESETS, _status_tick,
)
import kb_query

from pages.ingest import page_ingest
from pages.search import page_search
from pages.hub    import page_hub
from pages.config import page_config
from pages.manage import page_manage

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
    print("[启动] 正在刷新系统状态…", flush=True)
    refresh_system_state()
    threading.Thread(target=_auto_shutdown, daemon=True).start()
    app.timer(10.0, _status_tick)
    print(f"[启动] 完成 — stats={STATE.get('stats')}", flush=True)

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
                os._exit(0)

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
    try:
        _test = _r.get(f"{kb_query.QDRANT_URL}/collections", timeout=5)
        print(f"[启动] Qdrant 状态: {_test.status_code} -> {_test.ok}", flush=True)
    except Exception as _e:
        print(f"[启动] ⚠️ Qdrant 未启动: {_e}", flush=True)

    ui.run(
        title="Citrinitas · 熔知",
        host="127.0.0.1",
        port=8080,
        reload=False,
        show=False,
        storage_secret="citrinitas-mindforge-secret",
    )
