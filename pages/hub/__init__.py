"""
Citrinitas · 熔知 — 知识库管理页面

v1.0.1: 从 pages/hub.py 拆分为 pages/hub/ 包。
主入口 page_hub + 辅助函数。
"""

import asyncio
from datetime import datetime, timezone

from nicegui import ui, context

import kb_query
from utils.state import STATE
from utils.ui_shared import build_left_drawer, refresh_system_state, set_active_collection
from utils.activity_log import read_recent_activities

from .helpers import _load_dlq_files, _get_inbox_stats
from .overview import _build_overview_tab
from .browse import _build_browse_tab
from .review import _build_review_tab
from .inbox import _build_inbox_tab
from .dlq import _build_dlq_tab
from .logs import _build_logs_tab
from .detail import page_doc_detail  # noqa: F401 — registered via @ui.page decorator


@ui.page("/hub")
def page_hub():
    """知识库管理 — 侧边栏入口「知识中枢」"""
    import asyncio as _asyncio

    build_left_drawer(active_page="hub")

    # 页面标题
    with ui.header(elevated=True).classes("bg-white dark:bg-gray-900"):
        ui.label("📚 知识中枢").classes("text-h5 font-bold")

    # ── 系统状态 ──
    refresh_system_state()

    # ── 6 个标签页 ────────────────────────────────────────────────────────────
    with ui.tabs().classes("w-full") as tabs:
        overview_tab = ui.tab("📊 概览")
        browse_tab = ui.tab("📋 浏览")
        review_tab = ui.tab("📝 待审核")
        inbox_tab = ui.tab("📥 收件箱")
        dlq_tab = ui.tab("🗑️ 死信")
        logs_tab = ui.tab("📋 日志")

        # 死信徽章
        dlq_count = len(_load_dlq_files())
        if dlq_count > 0:
            with dlq_tab:
                ui.badge(str(dlq_count)).props("color=red floating")

    with ui.tab_panels(tabs, value=overview_tab).classes("w-full"):
        # ══════════════════════════════════════
        # Tab 1: 概览
        # ══════════════════════════════════════
        with ui.tab_panel(overview_tab):
            _asyncio.create_task(_build_overview_tab())

        # ══════════════════════════════════════
        # Tab 2: 浏览
        # ══════════════════════════════════════
        with ui.tab_panel(browse_tab):
            _asyncio.create_task(_build_browse_tab())

        # ══════════════════════════════════════
        # Tab 3: 待审核
        # ══════════════════════════════════════
        with ui.tab_panel(review_tab):
            _asyncio.create_task(_build_review_tab())

        # ══════════════════════════════════════
        # Tab 4: 收件箱（v1.0.0 新增 — 统一收件箱）
        # ══════════════════════════════════════
        with ui.tab_panel(inbox_tab):
            _asyncio.create_task(_build_inbox_tab())

        # ══════════════════════════════════════
        # Tab 5: 死信
        # ══════════════════════════════════════
        with ui.tab_panel(dlq_tab):
            _asyncio.create_task(_build_dlq_tab())

        # ══════════════════════════════════════
        # Tab 6: 日志查看器（v1.1.0 新增）
        # ══════════════════════════════════════
        with ui.tab_panel(logs_tab):
            _asyncio.create_task(_build_logs_tab())
