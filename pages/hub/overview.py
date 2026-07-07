"""
概览标签 — 仪表盘 + 分面统计。
"""

import asyncio
from nicegui import ui
import kb_query
from utils.state import STATE
from utils.activity_log import read_recent_activities
from .helpers import _load_dlq_files, _get_inbox_stats
# ═══════════════════════════════════════════
# Tab Builders
# ═══════════════════════════════════════════

async def _build_overview_tab():
    """概览标签页 — 卡片式仪表盘 + 活动时间线 + 快速入口 + 知识库管理。"""
    collections = STATE["collections"]
    current = STATE["active_collection"]
    stats = STATE.get("stats", {})

    # 获取实时统计数据
    total_docs = stats.get("points", 0)
    dlq_count = len(_load_dlq_files())
    inbox_stats = _get_inbox_stats()

    review_count = 0
    review_label = None

    async def _load_review_count():
        nonlocal review_count
        try:
            review_result = await asyncio.to_thread(kb_query.list_documents, collection=current, needs_review=True)
            if review_result.get("ok"):
                review_count = review_result.get("total", 0)
                if review_label is not None:
                    review_label.set_text(str(review_count))
                    review_label.classes(remove="text-gray-400", add="text-orange-400" if review_count > 0 else "text-gray-400")
        except Exception:
            pass

    await _load_review_count()

    # ═══════════════════════════════
    # Row 1: 统计卡片（5 列）
    # ═══════════════════════════════
    with ui.row().classes("w-full gap-4"):
        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("📄").classes("text-3xl")
            ui.label(str(total_docs)).classes("text-2xl font-bold")
            ui.label("总文档块").classes("text-sm text-gray-400")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("⚠️").classes("text-3xl")
            review_label = ui.label(str(review_count)).classes("text-2xl font-bold text-orange-400")
            ui.label("待审核").classes("text-sm text-gray-400")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("📥").classes("text-3xl")
            inbox_total = inbox_stats["total"]
            inbox_color = "text-red-400" if inbox_stats["failed"] > 0 else "text-blue-400"
            ui.label(str(inbox_total)).classes(f"text-2xl font-bold {inbox_color}")
            ui.label("收件箱").classes("text-sm text-gray-400")
            if inbox_stats["pending"] > 0:
                ui.badge(f"{inbox_stats['pending']} 待处理", color="blue").classes("text-xs mt-1")
            if inbox_stats["failed"] > 0:
                ui.badge(f"{inbox_stats['failed']} 失败", color="red").classes("text-xs mt-1")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("🗑️").classes("text-3xl")
            ui.label(str(dlq_count)).classes("text-2xl font-bold text-red-400" if dlq_count > 0 else "text-2xl font-bold")
            ui.label("死信").classes("text-sm text-gray-400")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("📚").classes("text-3xl")
            ui.label(str(len(collections))).classes("text-2xl font-bold")
            ui.label("知识库").classes("text-sm text-gray-400")


    # ══════════════════════════════
    # Row 1.5: 分面统计分布 (P2-3 修复)
    # ══════════════════════════════
    ui.separator()
    ui.markdown("### 📊 分面分布")

    # 创建容器用于异步更新
    facet_containers = {}

    async def _load_facet_stats():
        """异步加载分面统计。"""
        try:
            result = await asyncio.to_thread(kb_query.get_facet_stats, current)
            if result.get("ok"):
                facets = result.get("facets", {})
                for facet_name, counts in facets.items():
                    if facet_name in facet_containers and counts:
                        container = facet_containers[facet_name]
                        container.clear()
                        with container:
                            # 显示前 5 个最常见的值
                            sorted_items = sorted(counts.items(), key=lambda x: -x[1])[:5]
                            for value, count in sorted_items:
                                ui.label(f"  {value}: {count}").classes("text-xs text-gray-600")
                            if len(counts) > 5:
                                ui.label(f"  ... 还有 {len(counts) - 5} 种").classes("text-xs text-gray-500 italic")
        except Exception as e:
            ui.notify(f"分面统计加载失败: {e}", type="warning")

    with ui.row().classes("w-full gap-4"):
        for facet_name, facet_label in [
            ("content_type", "内容类型"),
            ("domain", "领域"),
            ("temporal_nature", "时效属性"),
            ("epistemic_status", "认知状态"),
        ]:
            with ui.card().classes("flex-1 p-3"):
                ui.label(facet_label).classes("text-sm font-bold mb-2")
                container = ui.column().classes("w-full")
                facet_containers[facet_name] = container

    await _load_facet_stats()

    # ═══════════════════════════════
    # Row 2: 快速入口按钮
    # ═══════════════════════════════
    ui.separator()
    with ui.row().classes("w-full gap-3 justify-center"):
        ui.link("📥 摄入新文档", "/").classes("no-underline")
        ui.link("🔍 搜索知识库", "/search").classes("no-underline")
        # 切换到浏览标签（用 JS 跳转）
        ui.button("📋 浏览文档", on_click=lambda: ui.run_javascript(
            "document.querySelector('.q-tab[role=\"tab\"]:nth-child(2)').click()"
        )).props("flat color=blue")

    # ═══════════════════════════════
    # Row 3: 活动时间线
    # ═══════════════════════════════
    ui.separator()
    ui.markdown("### 🕐 最近活动")

    activities = read_recent_activities(20)
    if not activities:
        ui.label("暂无活动记录").classes("text-sm text-gray-500 italic")
    else:
        # 按日期分组渲染
        _ACTION_ICONS = {
            "ingest_success": "📥",
            "ingest_failed": "❌",
            "review_approve": "✅",
            "review_drop": "🗑️",
            "dlq_delete": "🗑️",
            "dlq_reingest": "♻️",
            "dlq_reupload": "📎",
        }
        _ACTION_LABELS = {
            "ingest_success": "摄入成功",
            "ingest_failed": "摄入失败",
            "review_approve": "审核通过",
            "review_drop": "审核丢弃",
            "dlq_delete": "永久删除",
            "dlq_reingest": "手动修复入库",
            "dlq_reupload": "重新上传入库",
        }

        with ui.column().classes("w-full gap-1"):
            for a in activities[:20]:
                icon = _ACTION_ICONS.get(a["action"], "•")
                label = _ACTION_LABELS.get(a["action"], a["action"])
                ts = a["ts"][:16].replace("T", " ")
                detail = a.get("detail", "")[:50]
                color = "red" if "fail" in a["action"] or "drop" in a["action"] or "delete" in a["action"] else ""
                # 格式化时间
                try:
                    from datetime import datetime, timezone
                    dt = datetime.fromisoformat(a["ts"])
                    ts = dt.strftime("%m-%d %H:%M")
                except Exception:
                    pass

                with ui.row().classes("items-center gap-2"):
                    ui.label(f"{icon} {ts}").classes("text-xs text-gray-500")
                    ui.label(label).classes(f"text-sm {'text-red-400' if color else ''}")
                    if detail:
                        ui.label(detail).classes("text-xs text-gray-400")

    # ═══════════════════════════════
    # Row 4: 知识库管理（原有，折叠）
    # ═══════════════════════════════
    ui.separator()
    with ui.expansion("🔧 知识库管理 (创建/清空/切换)", value=False).classes("w-full"):
        ui.label(f"当前知识库：**{current}**").classes("text-sm mb-2")

        with ui.row().classes("w-full gap-2 mb-4"):
            new_col_name = ui.input(label="新知识库名称", placeholder="输入名称...").classes("w-48")

            async def create_col():
                name = (new_col_name.value or "").strip()
                if not name:
                    ui.notify("请输入名称", type="warning")
                    return
                try:
                    await asyncio.to_thread(kb_query.create_collection, name)
                    ui.notify(f"✅ 知识库「{name}」已创建", type="positive")
                    async def _after_create():
                        await asyncio.to_thread(refresh_system_state)
                        new_col_name.set_value("")
                    await _after_create()
                except Exception as ex:
                    ui.notify(f"创建失败: {ex}", type="negative")

            ui.button("➕ 创建", on_click=create_col).props("color=blue flat")

        # 清空集合（带确认）
        async def do_clear_collection():
            try:
                result = await asyncio.to_thread(kb_query.clear_collection, STATE["active_collection"])
                if result.get("ok"):
                    ui.notify(f"✅ 已清空 {result.get('deleted', 0)} 条", type="positive")
                    await asyncio.to_thread(refresh_system_state)
                else:
                    ui.notify(f"清空失败: {result.get('error', '?')}", type="negative")
            except Exception as ex:
                ui.notify(f"清空失败: {ex}", type="negative")

        clear_dialog = ui.dialog().props("persistent")
        with clear_dialog:
            with ui.card().classes("p-4"):
                ui.label("⚠️ 确认清空知识库？").classes("text-lg font-bold")
                ui.label("所有数据将被永久删除，此操作不可撤销。").classes("text-sm text-gray-500")
                with ui.row().classes("gap-2 mt-4"):
                    ui.button("取消", on_click=clear_dialog.close).props("flat")

                    async def _confirm_clear():
                        await do_clear_collection()
                        clear_dialog.close()
                    ui.button("确认清空", on_click=_confirm_clear).props("color=red")

        ui.button("🗑️ 清空当前库", on_click=clear_dialog.open).props("color=red flat").classes("ml-2")

        # 切换集合
        if len(collections) > 1:
            ui.separator()
            ui.markdown("#### 🔄 切换知识库")
            with ui.row().classes("w-full gap-2"):
                for c in collections:
                    color = "green" if c == current else "grey"
                    ui.button(c, on_click=lambda c=c: _set_active_collection(c)).props(f"color={color} flat")


async def _set_active_collection(collection_name: str):
    """异步切换集合。"""
    set_active_collection(collection_name)
    ui.notify(f"✅ 已切换到 {collection_name}", type="positive")


