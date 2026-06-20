"""
Citrinitas · 熔知 — 共享 UI 函数

此模块存放页面间共享的 UI 函数和业务函数，避免循环导入。
main.py 和 pages/*.py 都从此模块导入共享函数。
"""

from nicegui import ui, app
import requests
import kb_query
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
                resp = requests.get(
                    f"{kb_query.QDRANT_URL}/collections/{STATE['active_collection']}",
                    timeout=3,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    cfg = data.get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
                    pts = data.get("result", {}).get("points_count", 0)
                    STATE["stats"] = {"points": pts, "dim": cfg.get("size", "?"), "collection": STATE["active_collection"]}
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

_STATUS_WIDGETS = {}   # 状态栏控件引用（供 app.timer 回调更新）
_GLOBAL_TIMER = None   # app.timer 只创建一次


def _status_tick():
    """全局状态刷新回调（由 app.timer 每10秒触发，独立于任何UI元素）。"""
    w = _STATUS_WIDGETS
    if not w:
        return
    try:
        refresh_system_state()
        badge = w.get("badge")
        if badge is None:
            return
        if STATE["qdrant_online"]:
            badge.set_text("在线")
            badge.props("color=green")
            stats = STATE.get("stats", {})
            pts = w.get("points")
            if pts:
                pts.set_text(f"文档块: {stats.get('points', '--')}")
            dm = w.get("dim")
            if dm:
                dm.set_text(f"维度: {stats.get('dim', '--')}")
        else:
            badge.set_text("离线")
            badge.props("color=red")
    except Exception:
        pass  # 控件临时不可用（抽屉重建中），静默跳过


def build_left_drawer():
    """构建左侧导航抽屉（所有页面共用）。"""
    global _GLOBAL_TIMER
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

        # 系统状态
        with ui.column().classes("w-full px-4"):
            ui.markdown("### 📊 系统状态")
            _initial = "在线" if STATE["qdrant_online"] else "离线"
            _color   = "green" if STATE["qdrant_online"] else "red"
            status_badge = ui.badge(_initial, color=_color)
            points_label = ui.label("文档块: --").classes("text-sm")
            dim_label = ui.label("维度: --").classes("text-sm")

            def _update_status():
                refresh_system_state()
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

            # 全局定时器（app.timer 独立于UI，只创建一次）
            global _STATUS_WIDGETS, _GLOBAL_TIMER
            _STATUS_WIDGETS.update(badge=status_badge, points=points_label, dim=dim_label)
            if _GLOBAL_TIMER is None:
                _GLOBAL_TIMER = app.timer(10.0, _status_tick)

        ui.separator()

        # 导航链接
        with ui.column().classes("w-full px-2 gap-1"):
            ui.link("📥 文档注入", "/").classes(
                "w-full text-left p-2 rounded hover:bg-blue-700 transition no-underline text-white"
            )
            ui.link("💬 智能检索", "/search").classes(
                "w-full text-left p-2 rounded hover:bg-blue-700 transition no-underline text-white"
            )
            ui.link("📄 文档管理", "/manage").classes(
                "w-full text-left p-2 rounded hover:bg-blue-700 transition no-underline text-white"
            )
            ui.link("🗂️ 知识中枢", "/hub").classes(
                "w-full text-left p-2 rounded hover:bg-blue-700 transition no-underline text-white"
            )
            ui.link("⚙️ 引擎配置", "/config").classes(
                "w-full text-left p-2 rounded hover:bg-blue-700 transition no-underline text-white"
            )

        ui.separator()
        with ui.column().classes("w-full px-4"):
            ui.link("🔗 GitHub", "https://github.com/shiyao222333-afk/citrinitas").classes("text-xs text-blue-300")
            ui.button("⏻ 关机", on_click=lambda: os._exit(0)).props("flat dense color=red").classes("text-xs mt-2")

        return drawer


# ═══════════════════════════════════════════
# 搜索结果卡片
# ═══════════════════════════════════════════

def render_chunk_card(c: dict, idx: int):
    """渲染搜索结果卡片（U4 修复 - 显示新字段）"""
    with ui.card().classes("w-full"):
        title = c.get("title") or c.get("source", "未知")
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
