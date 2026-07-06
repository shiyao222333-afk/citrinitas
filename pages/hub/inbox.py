"""
收件箱标签页 — 统一收件箱文件列表 + 状态追踪 + 手动操作。
"""

import os
import asyncio
from nicegui import ui
from .helpers import (
    INBOX_DIR, _load_inbox_files, _retry_inbox_file,
    _delete_inbox_file,
)


def _build_inbox_tab():
    """收件箱标签页（v1.0.0） — 统一收件箱文件列表 + 状态追踪 + 手动操作。"""
    ui.markdown("### 📥 统一收件箱")
    ui.markdown("*所有通过守望文件夹进入的文件都在这里。状态由 `file_state.jsonl` 追踪。*")

    inbox_container = ui.column().classes("w-full")

    def _refresh_inbox():
        inbox_container.clear()
        with inbox_container:
            items = _load_inbox_files()

            if not items:
                ui.badge("📭 收件箱为空 — 将文件放入 data/inbox/ 目录即可自动处理", color="grey").classes("text-lg")
                ui.label(f"监控目录: {INBOX_DIR}").classes("text-xs text-gray-500 mt-2")
                return

            # 统计条
            stats = {"pending": 0, "failed": 0, "needs_review": 0, "retry": 0, "processing": 0}
            for item in items:
                s = item.get("state", "pending")
                stats[s] = stats.get(s, 0) + 1

            stat_parts = []
            if stats["pending"]:
                stat_parts.append(f"⏳ 待处理: {stats['pending']}")
            if stats["failed"]:
                stat_parts.append(f"❌ 失败: {stats['failed']}")
            if stats["needs_review"]:
                stat_parts.append(f"⚠️ 需审核: {stats['needs_review']}")
            if stats["retry"]:
                stat_parts.append(f"🔄 等待重试: {stats['retry']}")
            ui.label(f"共 {len(items)} 个文件 — " + " | ".join(stat_parts)).classes("text-sm text-gray-500 mb-2")

            # 状态筛选按钮
            filter_state = {"value": "all"}

            def _set_filter(s):
                filter_state["value"] = s
                _refresh_inbox()

            with ui.row().classes("gap-2 mb-3"):
                for label, key in [("全部", "all"), ("待处理", "pending"), ("失败", "failed"),
                                    ("需审核", "needs_review"), ("重试中", "retry")]:
                    color = "blue" if filter_state["value"] == key else "grey"
                    ui.button(label, on_click=lambda k=key: _set_filter(k)).props(f"color={color} flat size=sm")

            # 文件列表
            for item in items:
                if filter_state["value"] != "all" and item["state"] != filter_state["value"]:
                    continue
                _build_inbox_card(item, _refresh_inbox)

    _refresh_inbox()

    # 自动刷新：每 3 秒刷新收件箱，实时反映守望处理进度（无需手动点刷新）
    if not getattr(_build_inbox_tab, "_timer_started", False):
        def _auto_refresh():
            try:
                _refresh_inbox()
            except Exception:
                pass
        ui.timer(3.0, _auto_refresh)
        _build_inbox_tab._timer_started = True

    with ui.row().classes("gap-2 mt-2"):
        ui.button("🔄 刷新", on_click=_refresh_inbox).props("flat")
        ui.label(f"目录: data/inbox/").classes("text-xs text-gray-500 ml-4")


def _build_inbox_card(item: dict, on_refresh):
    """渲染单个收件箱文件卡片。"""
    filename = item["_filename"]
    fp = item["_file"]
    state = item.get("state", "pending")
    error = item.get("error", "")
    step = item.get("step", "")
    failure_type = item.get("failure_type", "")
    retry_count = item.get("retry_count", 0)
    ts = item.get("ts", "")[:19]

    # 状态 → 图标、颜色、中文
    state_display = {
        "pending":       ("⏳", "blue",   "待处理"),
        "processing":    ("🔄", "blue",   "处理中"),
        "done":          ("✅", "green",  "已完成"),
        "failed":        ("❌", "red",    "失败"),
        "needs_review":  ("⚠️", "orange", "需审核"),
        "retry":         ("🔄", "purple", "等待重试"),
    }
    icon, color, state_cn = state_display.get(state, ("❓", "grey", state))

    # 步骤中文名
    step_names = {
        "format_check": "格式检查", "size_check": "大小检查",
        "extract": "文本提取", "extract_empty": "文本为空",
        "classify": "AI 分类", "ingest": "知识入库",
        "ocr": "文字识别", "ocr_check": "OCR 检查",
        "timeout": "处理超时", "unknown": "未知步骤",
        "migrated_from_v1": "旧版迁移",
    }
    step_cn = step_names.get(step, step) if step else "—"

    # 文件大小
    fsize = ""
    try:
        size_bytes = os.path.getsize(fp)
        if size_bytes > 1024 * 1024:
            fsize = f" | {size_bytes / (1024*1024):.1f}MB"
        elif size_bytes > 1024:
            fsize = f" | {size_bytes / 1024:.0f}KB"
        else:
            fsize = f" | {size_bytes}B"
    except OSError:
        pass

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center gap-4"):
            ui.label(f"{icon} {filename}").classes("font-bold flex-1")
            ui.badge(state_cn, color=color)
            if failure_type:
                ui.badge(failure_type, color="grey").classes("text-xs")

        # 详细信息（仅失败/需审核/重试时显示）
        if state in ("failed", "needs_review", "retry"):
            with ui.column().classes("w-full text-xs text-gray-500 mt-1"):
                ui.label(f"失败步骤: {step_cn}")
                if error:
                    ui.label(f"原因: {error}")
                if retry_count > 0:
                    ui.label(f"重试次数: {retry_count}")
                if ts:
                    ui.label(f"时间: {ts}")

        # 文件信息
        ui.label(f"路径: {fp}{fsize}").classes("text-xs text-gray-400 mt-1")

        with ui.row().classes("gap-2 mt-2"):
            # 重试按钮（失败/需审核/重试状态）
            if state in ("failed", "needs_review", "retry"):
                async def _retry(fn=filename):
                    if _retry_inbox_file(fn):
                        ui.notify(f"✅ {fn} 已加入处理队列", type="positive")
                    else:
                        ui.notify(f"❌ {fn} 重试失败（守望进程可能未运行）", type="negative")
                    on_refresh()
                ui.button("🔄 重试", on_click=lambda: asyncio.ensure_future(_retry())).props("color=blue flat size=sm")

            # 删除按钮（所有状态均可删除）
            del_dialog = ui.dialog()
            with del_dialog:
                with ui.card().classes("p-4"):
                    ui.label("⚠️ 确认删除此文件？").classes("text-lg font-bold")
                    ui.label(f"文件: {filename}").classes("text-sm text-gray-500")
                    ui.label("文件及其状态记录将被永久删除。").classes("text-xs text-gray-400")
                    with ui.row().classes("gap-2 mt-4"):
                        ui.button("取消", on_click=del_dialog.close).props("flat")
                        ui.button("确认删除", on_click=lambda dd=del_dialog, fn=filename: [
                            _delete_inbox_file(fn),
                            dd.close(),
                            ui.notify(f"已删除: {fn}", type="positive"),
                            on_refresh(),
                        ]).props("color=red")
            ui.button("❌ 删除", on_click=del_dialog.open).props("color=red flat size=sm")
