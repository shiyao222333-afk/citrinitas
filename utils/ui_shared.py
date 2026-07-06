"""
Citrinitas · 熔知 — 共享 UI 函数

此模块存放页面间共享的 UI 函数和业务函数，避免循环导入。
main.py 和 pages/*.py 都从此模块导入共享函数。
"""

import asyncio
from nicegui import ui, app
import requests
import kb_query
import threading
from utils.state import STATE

# ═══════════════════════════════════════════
# 嵌入模型预设（main.py 和 pages/config.py 共用）
# ═══════════════════════════════════════════

EMBED_PRESETS = {
    "qwen3-embedding": "qwen3-embedding:4b",
    "bge-m3": "bge-m3:latest",
    "nomic-embed-text": "nomic-embed-text:latest",
    "mxbai-embed-large": "mxbai-embed-large:latest",
}

# ═══════════════════════════════════════════
# 全局状态刷新
# ═══════════════════════════════════════════

def refresh_system_state():
    """刷新全局状态：Qdrant 连接、集合列表、统计信息（所有请求带 timeout）。"""
    try:
        col_data = kb_query.list_collections()
        STATE["collections"] = [c["name"] for c in col_data.get("collections", [])] if col_data.get("ok") else []
        STATE["qdrant_online"] = col_data.get("ok", False)

        if STATE["active_collection"] not in STATE["collections"] and STATE["collections"]:
            STATE["active_collection"] = STATE["collections"][0]

        if STATE["qdrant_online"]:
            try:
                url = f"{kb_query.QDRANT_URL}/collections/{STATE['active_collection']}"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("result", {})
                    cfg = data.get("config", {}).get("params", {}).get("vectors", {})
                    pts = data.get("points_count", 0)
                    # Qdrant >=1.x 将向量配置嵌套在 dense/sparse 下
                    if isinstance(cfg, dict):
                        dim = cfg.get("size") or (cfg.get("dense", {}).get("size")) or "?"
                    else:
                        dim = "?"
                    STATE["stats"] = {
                        "points": pts,
                        "dim": dim,
                        "collection": STATE["active_collection"],
                    }
                else:
                    STATE["stats"] = {}
            except Exception:
                STATE["stats"] = {}
        else:
            STATE["stats"] = {}
    except Exception:
        STATE["collections"] = []
        STATE["qdrant_online"] = False
        STATE["stats"] = {}

    try:
        STATE["embed_models"] = kb_query.get_embed_models()
    except Exception:
        STATE["embed_models"] = []


def set_active_collection(name: str):
    STATE["active_collection"] = name


# ═══════════════════════════════════════════
# 左侧抽屉（所有页面共用）
# ═══════════════════════════════════════════

_STATUS_WIDGETS = {}   # 状态栏控件引用（供 _status_tick 回调更新）
_GLOBAL_TIMER = None    # app.timer 只创建一次
_MAIN_LOOP = None       # 事件循环引用（在事件循环线程中设置）


def set_main_loop():
    """在事件循环线程中调用，保存 loop 引用供后台线程使用。"""
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_event_loop()


def _status_tick():
    """全局状态刷新回调（由 app.timer 每60秒触发，独立于任何UI元素）。
    ⚠️ 在后台线程调用 refresh_system_state()，避免阻塞事件循环。"""
    w = _STATUS_WIDGETS
    if not w:
        return
    # 在后台线程执行，不阻塞事件循环
    def _do_refresh():
        try:
            refresh_system_state()
            # 用 call_soon_threadsafe 将 UI 更新调度到事件循环线程
            def _update_ui():
                try:
                    if STATE["qdrant_online"]:
                        w["badge"].set_text("在线")
                        w["badge"].props("color=green")
                        stats = STATE.get("stats", {})
                        w["points"].set_text(f"文档块: {stats.get('points', '--')}")
                        w["dim"].set_text(f"维度: {stats.get('dim', '--')}")
                    else:
                        w["badge"].set_text("离线")
                        w["badge"].props("color=red")
                except Exception:
                    pass
            if _MAIN_LOOP is not None:
                _MAIN_LOOP.call_soon_threadsafe(_update_ui)
        except Exception:
            pass
    threading.Thread(target=_do_refresh, daemon=True).start()


def build_left_drawer(active_page: str = ""):
    """构建左侧导航抽屉（所有页面共用）。

    Args:
        active_page: 当前页面标识，用于高亮导航链接。
                    取值：""（摄入）、"search"、"hub"、"config"
    """
    global _GLOBAL_TIMER, _STATUS_WIDGETS

    # 保存事件循环引用（供 _status_tick 的后台线程使用）
    set_main_loop()

    # startup() 已经填好了 STATE["stats"]，直接读取，不再重复请求 Qdrant
    if STATE.get("qdrant_online"):
        _badge_text = "在线"
        _badge_color = "green"
    else:
        _badge_text = "离线"
        _badge_color = "red"

    _stats = STATE.get("stats", {})
    _points_text = f"文档块: {_stats.get('points', '--')}"
    _dim_text = f"维度: {_stats.get('dim', '--')}"

    # 导航链接样式辅助
    def _nav_class(page_key: str) -> str:
        """当前页高亮，其他页悬停高亮。"""
        if page_key == active_page:
            return "w-full text-left p-2 rounded bg-blue-700 no-underline text-white font-bold"
        return "w-full text-left p-2 rounded hover:bg-blue-700 transition no-underline text-white"

    with ui.left_drawer(value=True, fixed=False, bordered=True).classes("bg-gray-900 text-white") as drawer:
        with ui.column().classes("w-full items-center p-4"):
            ui.markdown("## 🏭 Citrinitas")
            ui.markdown("##### 熔知 · Citrinitas")
            ui.label("个人本地知识引擎").classes("text-sm text-gray-400")
            ui.separator()

        # 知识库选择器
        with ui.column().classes("w-full px-4"):
            ui.markdown("### 📚 当前知识库")
            collection_select = ui.select(
                options=STATE["collections"] if STATE["collections"] else [kb_query.DEFAULT_COLLECTION],
                value=STATE["active_collection"],
                on_change=lambda e: set_active_collection(e.value),
            ).classes("w-full").props("dense outlined dark")

        ui.separator()

        # 系统状态（用上面计算好的值初始化）
        with ui.column().classes("w-full px-4"):
            ui.markdown("### 📊 系统状态")
            status_badge = ui.badge(_badge_text, color=_badge_color)
            points_label = ui.label(_points_text).classes("text-sm")
            dim_label = ui.label(_dim_text).classes("text-sm")

            def _update_status():
                """手动刷新按钮回调：只更新 UI，不调用 refresh_system_state（避免阻塞事件循环）"""
                # 注意：这里直接读 STATE，不重新请求 Qdrant（避免阻塞）
                if STATE["qdrant_online"]:
                    status_badge.set_text("在线")
                    status_badge.props("color=green")
                    stats = STATE.get("stats", {})
                    points_label.set_text(f"文档块: {stats.get('points', '--')}")
                    dim_label.set_text(f"维度: {stats.get('dim', '--')}")
                else:
                    status_badge.set_text("离线")
                    status_badge.props("color=red")

            ui.button("🔄 刷新", on_click=_update_status).props("flat dense").classes("text-xs")

            # 注册控件引用（供 _status_tick 定时器使用）
            _STATUS_WIDGETS.update(badge=status_badge, points=points_label, dim=dim_label)

            # 全局定时器（app.timer 独立于UI，只创建一次）
            # 注意：_status_tick 里会调用 refresh_system_state()，
            # 为避免阻塞事件循环，改为每60秒刷新一次（降低频率）
            if _GLOBAL_TIMER is None:
                _GLOBAL_TIMER = app.timer(60.0, _status_tick)

            # 页面加载后不再自动触发 _update_status（避免阻塞）
            # ui.timer(0.5, _update_status, once=True)  # 已禁用

        ui.separator()

        # 导航链接（支持 active_page 高亮）
        with ui.column().classes("w-full px-2 gap-1"):
            ui.link("📥 摄入", "/").classes(_nav_class(""))
            ui.link("🔍 搜索", "/search").classes(_nav_class("search"))
            ui.link("📚 知识库管理", "/hub").classes(_nav_class("hub"))
            ui.link("📄 文档管理", "/manage").classes(_nav_class("manage"))
            ui.link("⚙️ 设置", "/config").classes(_nav_class("config"))

        ui.separator()
        with ui.column().classes("w-full px-4"):
            ui.link("🔗 GitHub", "https://github.com/shiyao222333-afk/citrinitas").classes("text-xs text-blue-300")
            ui.button("⏻ 关机", on_click=lambda: __import__("os")._exit(0)).props("flat dense color=red").classes("text-xs mt-2")

        return drawer


# ═══════════════════════════════════════════
# 搜索结果卡片
# ═══════════════════════════════════════════

def render_chunk_card(c: dict, idx: int):
    """渲染搜索结果卡片（U4 修复 - 显示新字段）"""
    with ui.card().classes("w-full"):
        title = c.get("title") or c.get("source") or "未知"
        ui.markdown(f"**{idx}.** {title}")

        # 显示新字段（U4 修复）
        with ui.row().classes("items-center gap-2 wrap"):
            if c.get("needs_review"):
                ui.badge("⚠️ 待审核", color="orange").classes("text-xs")
            ui.label(f"📄 {c.get('content_type', 'N/A')}").classes("text-xs text-gray-400")
            ui.label(f"🏷️ {', '.join(c.get('domain', []))}").classes("text-xs text-gray-400")
            ui.label(f"✅ {c.get('epistemic_status', 'N/A')}").classes("text-xs text-gray-400")
            ui.label(f"⏱️ {c.get('temporal_nature', 'N/A')}").classes("text-xs text-gray-500")

        ui.markdown(f"```\n{c.get('text', '')[:300]}\n```")
        ui.label(f"分数: {c.get('score', 0):.2f}").classes("text-xs text-gray-500")
