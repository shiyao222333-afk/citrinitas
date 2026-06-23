""""
Citrinitas · 熔知 — 知识库管理页面

此模块包含知识库管理页面（/hub）的函数。
从 main.py 拆分出来以降低主文件复杂度。

v0.9.0: 侧边栏 5→4 合并，/hub 承接原 /manage 功能，4 标签：概览/浏览/待审核/死信
"""

import asyncio
import os
import json
import glob as glob_mod
from datetime import datetime, timezone

from nicegui import ui

import kb_query
from utils.state import STATE
from utils.ui_shared import build_left_drawer, refresh_system_state, set_active_collection
from utils.activity_log import log_activity, read_recent_activities

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DLQ_DIR = os.path.join(PROJECT_DIR, "local_data", "dead_letter")


def _load_dlq_files() -> list:
    """加载所有死信队列 JSON 文件。"""
    items = []
    if not os.path.isdir(DLQ_DIR):
        return items
    for fp in sorted(glob_mod.glob(os.path.join(DLQ_DIR, "*.json")), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["_file"] = fp
            data["_filename"] = os.path.basename(fp)
            items.append(data)
        except Exception:
            pass
    return items


def _delete_dlq_file(fp: str):
    """删除单个死信文件。"""
    if os.path.exists(fp):
        os.unlink(fp)


@ui.page("/hub")
def page_hub():
    """知识库管理页面（/hub）—— 概览 + 浏览 + 待审核 + 死信队列"""

    build_left_drawer()

    with ui.column().classes("w-full p-6"):
        ui.markdown("# 📚 知识库管理")
        ui.markdown("*统一的知识库管理中心 — 概览、浏览、审核、清理。*")

        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线，请先启动。", color="red")
            return

        tabs = ui.tabs().props("align=left")
        with tabs:
            overview_tab = ui.tab("📊 概览")
            browse_tab = ui.tab("📋 浏览")
            review_tab = ui.tab("⚠️ 待审核")
            dlq_tab = ui.tab("🗑️ 死信")
        tab_panels = ui.tab_panels(tabs, value=overview_tab).classes("w-full")

        # ══════════════════════════════════════
        # Tab 1: 概览（仪表盘 — D2 重设计）
        # ══════════════════════════════════════
        with tab_panels:
            with ui.tab_panel(overview_tab):
                _build_overview_tab()

        # ══════════════════════════════════════
        # Tab 2: 浏览（文档浏览器 — D3 实现）
        # ══════════════════════════════════════
        with tab_panels:
            with ui.tab_panel(browse_tab):
                _build_browse_tab()

        # ══════════════════════════════════════
        # Tab 3: 待审核
        # ══════════════════════════════════════
        with tab_panels:
            with ui.tab_panel(review_tab):
                _build_review_tab()

        # ══════════════════════════════════════
        # Tab 4: 死信
        # ══════════════════════════════════════
        with tab_panels:
            with ui.tab_panel(dlq_tab):
                _build_dlq_tab()


# ═══════════════════════════════════════════
# Tab Builders
# ═══════════════════════════════════════════

def _build_overview_tab():
    """概览标签页 — 卡片式仪表盘 + 活动时间线 + 快速入口 + 知识库管理。"""
    collections = STATE["collections"]
    current = STATE["active_collection"]
    stats = STATE.get("stats", {})

    # 获取实时统计数据
    total_docs = stats.get("points", 0)
    dlq_count = len(_load_dlq_files())

    review_count = 0
    try:
        review_result = kb_query.list_documents(collection=current, needs_review=True)
        if review_result.get("ok"):
            review_count = review_result.get("doc_count", 0)
    except Exception:
        pass

    # ═══════════════════════════════
    # Row 1: 统计卡片（4 列）
    # ═══════════════════════════════
    with ui.row().classes("w-full gap-4"):
        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("📄").classes("text-3xl")
            ui.label(str(total_docs)).classes("text-2xl font-bold")
            ui.label("总文档块").classes("text-sm text-gray-400")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("⚠️").classes("text-3xl")
            ui.label(str(review_count)).classes("text-2xl font-bold text-orange-400")
            ui.label("待审核").classes("text-sm text-gray-400")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("🗑️").classes("text-3xl")
            ui.label(str(dlq_count)).classes("text-2xl font-bold text-red-400")
            ui.label("死信").classes("text-sm text-gray-400")

        with ui.card().classes("flex-1 text-center p-4"):
            ui.label("📚").classes("text-3xl")
            ui.label(str(len(collections))).classes("text-2xl font-bold")
            ui.label("知识库").classes("text-sm text-gray-400")

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
                    asyncio.ensure_future(_after_create())
                except Exception as ex:
                    ui.notify(f"创建失败: {ex}", type="negative")

            ui.button("➕ 创建", on_click=lambda: asyncio.ensure_future(create_col())).props("color=blue flat")

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
                    ui.button("确认清空", on_click=lambda: [
                        asyncio.ensure_future(do_clear_collection()),
                        clear_dialog.close(),
                    ]).props("color=red")

        ui.button("🗑️ 清空当前库", on_click=clear_dialog.open).props("color=red flat").classes("ml-2")

        # 切换集合
        if len(collections) > 1:
            ui.separator()
            ui.markdown("#### 🔄 切换知识库")
            with ui.row().classes("w-full gap-2"):
                for c in collections:
                    color = "green" if c == current else "grey"
                    ui.button(c, on_click=lambda c=c: asyncio.ensure_future(_set_active_collection(c))).props(f"color={color} flat")


async def _set_active_collection(collection_name: str):
    """异步切换集合。"""
    set_active_collection(collection_name)
    ui.notify(f"✅ 已切换到 {collection_name}", type="positive")


def _build_browse_tab():
    """浏览标签页 — 全文搜索 + 分面过滤 + 排序 + 批量操作 + 文档卡片列表。"""
    from config.classifications import CONTENT_TYPE_OPTIONS, TEMPORAL_NATURE_OPTIONS, EPISTEMIC_STATUS_OPTIONS

    # UDC 选项
    UDC_OPTIONS = [
        ("0", "0 总论/信息科学"),
        ("1", "1 哲学/心理学"),
        ("2", "2 宗教/神学"),
        ("3", "3 社会科学"),
        ("5", "5 数学/自然科学"),
        ("6", "6 应用科学/技术"),
        ("7", "7 艺术/文体"),
        ("8", "8 语言/文学"),
        ("9", "9 历史/地理"),
    ]

    # ═══════════════════════════════
    # 工具栏: 搜索 + 过滤 + 排序
    # ═══════════════════════════════
    with ui.row().classes("w-full gap-2 items-end"):
        search_input = ui.input(placeholder="搜索标题/来源...").classes("w-64").props("clearable dense")
        sort_select = ui.select(
            options={"created_desc": "🕐 最新优先", "created_asc": "🕐 最早优先", "title_asc": "🔤 标题 A-Z"},
            value="created_desc",
        ).classes("w-40").props("dense")

    with ui.row().classes("w-full gap-2 wrap mt-2"):
        ct_filter = ui.select(
            label="内容类型",
            options={k: v.split(" ")[-1] if " " in v else v for k, v in CONTENT_TYPE_OPTIONS},
            value=[],
            multiple=True,
        ).classes("w-40").props("dense clearable")
        domain_filter = ui.select(
            label="领域",
            options={k: v for k, v in UDC_OPTIONS},
            value=[],
            multiple=True,
        ).classes("w-40").props("dense clearable")
        temp_filter = ui.select(
            label="时效",
            options={k: v for k, v in TEMPORAL_NATURE_OPTIONS},
            value=[],
            multiple=True,
        ).classes("w-40").props("dense clearable")
        epi_filter = ui.select(
            label="认知状态",
            options={k: v for k, v in EPISTEMIC_STATUS_OPTIONS},
            value=[],
            multiple=True,
        ).classes("w-40").props("dense clearable")

    # ═══════════════════════════════
    # 文档列表
    # ═══════════════════════════════
    ui.separator()

    result_info = ui.label("").classes("text-sm text-gray-500 mb-2")
    doc_container = ui.column().classes("w-full")
    batch_bar = ui.row().classes("w-full gap-2 items-center")

    def _refresh_browse():
        """刷新文档列表（异步加载 + 客户端过滤）。"""
        doc_container.clear()
        batch_bar.clear()

        async def _load():
            try:
                result = await asyncio.to_thread(
                    kb_query.list_documents,
                    collection=STATE["active_collection"],
                    page=1,
                    page_size=500,  # 一次性加载全部用于客户端过滤
                )
            except Exception as ex:
                ui.notify(f"加载失败: {ex}", type="negative")
                return

            if not result.get("ok"):
                ui.notify(f"加载失败: {result.get('error', '?')}", type="negative")
                return

            all_docs = result.get("documents", [])

            # 应用过滤
            search_text = (search_input.value or "").lower().strip()
            ct_vals = set(ct_filter.value or [])
            domain_vals = set(domain_filter.value or [])
            temp_vals = set(temp_filter.value or [])
            epi_vals = set(epi_filter.value or [])
            sort_key = sort_select.value or "created_desc"

            filtered = []
            for d in all_docs:
                # 搜索过滤
                if search_text:
                    title = (d.get("title") or "").lower()
                    source = (d.get("source") or "").lower()
                    preview = (d.get("content_preview") or "").lower()
                    if search_text not in title and search_text not in source and search_text not in preview:
                        continue
                # 分面过滤
                if ct_vals and d.get("content_type", "") not in ct_vals:
                    continue
                if domain_vals:
                    doc_domains = set(d.get("domain", []))
                    if not domain_vals & doc_domains:
                        continue
                if temp_vals and d.get("temporal_nature", "") not in temp_vals:
                    continue
                if epi_vals and d.get("epistemic_status", "") not in epi_vals:
                    continue
                filtered.append(d)

            # 排序
            if sort_key == "created_asc":
                filtered.sort(key=lambda d: d.get("created_at", ""))
            elif sort_key == "title_asc":
                filtered.sort(key=lambda d: (d.get("title") or d.get("source", "")).lower())
            else:  # created_desc
                filtered.sort(key=lambda d: d.get("created_at", ""), reverse=True)

            result_info.set_text(f"共 {len(filtered)} 条文档" + (f"（已过滤，总计 {len(all_docs)} 条）" if len(filtered) != len(all_docs) else ""))

            if not filtered:
                with doc_container:
                    ui.badge("📭 无匹配文档", color="grey").classes("text-lg")
                return

            # 批量操作栏
            selected_ids = set()
            with batch_bar:
                ui.button("🗑️ 批量删除选中", on_click=lambda: _batch_delete(selected_ids, _refresh_browse)).props("color=red flat")
                ui.label(f"已选 0/{len(filtered)}").classes("text-sm text-gray-500").bind_text_from(
                    selected_ids, backward=lambda s: f"已选 {len(s)}/{len(filtered)}"
                ) if False else None

            # 文档卡片
            with doc_container:
                for idx, d in enumerate(filtered):
                    _build_doc_card(d, idx, selected_ids, _refresh_browse)

        asyncio.ensure_future(_load())

    # 搜索/过滤变更时自动刷新（debounce 处理在业务层）
    search_input.on("keydown.enter", lambda: _refresh_browse())
    ct_filter.on("update:model-value", lambda: _refresh_browse())
    domain_filter.on("update:model-value", lambda: _refresh_browse())
    temp_filter.on("update:model-value", lambda: _refresh_browse())
    epi_filter.on("update:model-value", lambda: _refresh_browse())
    sort_select.on("update:model-value", lambda: _refresh_browse())

    # 初始加载
    _refresh_browse()

    ui.button("🔄 刷新", on_click=_refresh_browse).props("flat").classes("mt-2")


def _build_doc_card(doc: dict, idx: int, selected_ids: set, on_refresh):
    """渲染单个文档卡片（浏览标签页用）。"""
    title = doc.get("title") or doc.get("source") or "未知"
    doc_uid = doc.get("doc_uid", "")
    content_type = doc.get("content_type", "?")
    domain = doc.get("domain", [])
    temporal = doc.get("temporal_nature", "")
    epistemic = doc.get("epistemic_status", "")
    confidence = doc.get("overall_confidence", 0)
    needs_review = doc.get("needs_review", False)
    preview = (doc.get("content_preview") or "")[:150]
    created = doc.get("created_at", "")[:10]
    chunk_count = doc.get("chunk_count", 1)

    with ui.card().classes("w-full").props("flat bordered"):
        with ui.row().classes("w-full items-center gap-2"):
            # 勾选框
            cb = ui.checkbox(on_change=lambda e, uid=doc_uid: (
                selected_ids.add(uid) if e.value else selected_ids.discard(uid)
            )).props("dense")

            # 标题
            ui.label(title).classes("font-bold flex-1")

            if needs_review:
                ui.badge("⚠️ 待审", color="orange").classes("text-xs")
            ui.badge(content_type, color="blue").classes("text-xs")

        # 元数据行
        with ui.row().classes("gap-2 text-xs text-gray-400 mt-1"):
            if domain:
                ui.label("🏷️ " + ", ".join(domain)).classes("text-xs")
            if temporal:
                ui.label("⏱️ " + temporal)
            if epistemic:
                ui.label("✅ " + epistemic)
            if created:
                ui.label("📅 " + created)
            ui.label(f"📦 {chunk_count} 块")

        # 预览文本
        if preview:
            ui.label(preview).classes("text-xs text-gray-500 mt-1").style("white-space: pre-wrap; max-height: 3em; overflow: hidden")

        # 操作按钮
        with ui.row().classes("gap-2 mt-2"):
            ui.button("👁️ 快览", on_click=lambda d=doc: _show_doc_quickview(d)).props("flat size=sm")
            ui.link("📋 完整档案", f"/doc/{doc_uid}").classes("no-underline")

    ui.separator()


def _show_doc_quickview(doc: dict):
    """文档快览弹窗 — 精简信息 + 跳转完整档案入口。"""
    title = doc.get("title") or doc.get("source") or "未知"
    doc_uid = doc.get("doc_uid", "")
    content_type = doc.get("content_type", "?")
    domain = doc.get("domain", [])
    temporal = doc.get("temporal_nature", "")
    epistemic = doc.get("epistemic_status", "")
    confidence = doc.get("overall_confidence", 0)
    preview = (doc.get("content_preview") or "")[:300]
    created = doc.get("created_at", "")[:19]

    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("p-4 w-full max-w-lg"):
        ui.label(f"📄 {title}").classes("text-lg font-bold")

        with ui.row().classes("gap-2 mt-2"):
            if doc.get("needs_review"):
                ui.badge("⚠️ 待审核", color="orange")
            ui.badge(content_type, color="blue")
            if domain:
                for d in domain[:3]:
                    ui.badge(d, color="green").classes("text-xs")

        with ui.row().classes("gap-4 mt-2 text-xs text-gray-400"):
            ui.label(f"⏱️ {temporal or 'N/A'}")
            ui.label(f"✅ {epistemic or 'N/A'}")
            ui.label(f"📊 置信度: {confidence:.0%}")
            ui.label(f"📅 {created}")

        if preview:
            ui.separator()
            ui.markdown(f"```\n{preview}\n```")

        with ui.row().classes("gap-2 mt-3"):
            ui.button("关闭", on_click=dialog.close).props("flat")
            ui.button("📋 查看完整档案", on_click=lambda: [
                dialog.close(),
                ui.run_javascript(f"window.location.href='/doc/{doc_uid}'"),
            ]).props("color=blue flat")

    dialog.open()


def _batch_delete(selected_ids: set, on_refresh):
    """批量删除选中的文档。"""
    if not selected_ids:
        ui.notify("未选择任何文档", type="warning")
        return

    async def _do_batch_delete():
        deleted = 0
        failed = 0
        for uid in list(selected_ids):
            try:
                result = await asyncio.to_thread(
                    kb_query.delete_document,
                    uid,
                    collection=STATE["active_collection"],
                )
                if result.get("ok"):
                    log_activity("batch_delete", uid, "", STATE["active_collection"])
                    deleted += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        ui.notify(f"✅ 已删除 {deleted} 条" + (f"，{failed} 条失败" if failed else ""), type="positive")
        on_refresh()

    ui.notify(f"正在删除 {len(selected_ids)} 条文档...", type="info")
    asyncio.ensure_future(_do_batch_delete())


def _build_review_tab():
    """待审核标签页 — 列出 needs_review=True 的文档，支持通过/丢弃。"""
    ui.markdown("### 📋 待审核条目")
    ui.markdown("*AI 不太确定这些内容，请确认。*")

    review_container = ui.column().classes("w-full")

    def _refresh_review():
        review_container.clear()
        with review_container:
            try:
                result = kb_query.list_documents(
                    collection=STATE["active_collection"],
                    needs_review=True,
                )
            except Exception as ex:
                ui.badge(f"加载失败: {ex}", color="red")
                return

            docs = result.get("documents", []) if result.get("ok") else []
            if not docs:
                ui.badge("🎉 没有待审核的条目", color="green")
                return

            ui.label(f"共 {len(docs)} 条待审核").classes("text-sm text-gray-500 mb-2")

            for doc in docs:
                _build_review_card(doc, _refresh_review)

    _refresh_review()

    ui.button("🔄 刷新", on_click=_refresh_review).props("flat").classes("mt-2")


def _build_review_card(doc: dict, on_refresh):
    """渲染单个待审核文档卡片。"""
    doc_uid = doc.get("doc_uid", "?")
    title = doc.get("title") or "未命名"
    source = doc.get("source") or doc.get("source_path") or "手动输入"
    confidence = doc.get("overall_confidence", 0)
    content_preview = doc.get("content_preview", "")[:200]
    content_type = doc.get("content_type", "?")
    domain = doc.get("domain", [])
    domain_str = ", ".join(domain) if domain else "未分类"

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center gap-4"):
            ui.markdown(f"**{title}**").classes("flex-1")
            ui.badge(f"置信度: {confidence:.0%}", color="orange" if confidence < 0.60 else "blue")

        ui.label(f"来源: {source}").classes("text-xs text-gray-400")
        ui.label(f"类型: {content_type} | 领域: {domain_str}").classes("text-xs text-gray-400")

        with ui.row().classes("items-center gap-2"):
            ui.label("靠谱程度:").classes("text-xs text-gray-400")
            bar_color = "red" if confidence < 0.50 else "orange" if confidence < 0.65 else "blue"
            ui.linear_progress(
                value=confidence,
                size="12px",
            ).classes("w-48").props(f"color={bar_color}")

        if content_preview:
            ui.label(content_preview).classes("text-xs text-gray-500 mt-1").style("white-space: pre-wrap")

        with ui.row().classes("gap-2 mt-2"):
            # 通过按钮 — 使用工厂函数避免闭包捕获问题
            async def _approve():
                try:
                    await asyncio.to_thread(
                        kb_query.update_metadata,
                        doc_uid,
                        {"needs_review": False},
                        collection=STATE["active_collection"],
                    )
                    title = doc.get("title", "") or doc.get("source", "")
                    log_activity("review_approve", doc_uid, title, STATE["active_collection"])
                    ui.notify(f"✅ 已通过: {doc_uid[:12]}", type="positive")
                    on_refresh()
                except Exception as ex:
                    ui.notify(f"操作失败: {ex}", type="negative")

            ui.button("✅ 通过并入库", on_click=lambda: asyncio.ensure_future(_approve())).props("color=green flat")

            # 丢弃按钮（带确认）
            async def _drop():
                try:
                    await asyncio.to_thread(
                        kb_query.delete_document,
                        doc_uid,
                        collection=STATE["active_collection"],
                    )
                    title = doc.get("title", "") or doc.get("source", "")
                    log_activity("review_drop", doc_uid, title, STATE["active_collection"])
                    ui.notify(f"已丢弃: {doc_uid[:12]}", type="positive")
                    on_refresh()
                except Exception as ex:
                    ui.notify(f"丢弃失败: {ex}", type="negative")

            drop_dialog = ui.dialog()
            with drop_dialog:
                with ui.card().classes("p-4"):
                    ui.label(f"⚠️ 确认丢弃「{title}」？").classes("text-lg font-bold")
                    ui.label("此操作不可撤销。").classes("text-sm text-gray-500")
                    with ui.row().classes("gap-2 mt-4"):
                        ui.button("取消", on_click=drop_dialog.close).props("flat")
                        ui.button("确认丢弃", on_click=lambda: [asyncio.ensure_future(_drop()), drop_dialog.close()]).props("color=red")

            ui.button("❌ 丢弃", on_click=drop_dialog.open).props("color=red flat")


def _build_dlq_tab():
    """死信队列标签页 — 列出置信度 < 低阈值的条目，支持修正/上传/删除。"""
    ui.markdown("### 🗑️ 死信队列")
    ui.markdown("*AI 完全无法分类的内容，需要手动处理。*")

    dlq_container = ui.column().classes("w-full")

    def _refresh_dlq():
        dlq_container.clear()
        with dlq_container:
            items = _load_dlq_files()
            if not items:
                ui.badge("🎉 死信队列为空", color="green")
                return

            ui.label(f"共 {len(items)} 条死信").classes("text-sm text-gray-500 mb-2")

            for item in items:
                confidence = item.get("confidence", 0)
                reason = item.get("reason", "未知")
                content = item.get("content", "")[:200]
                metadata = item.get("metadata", {})
                fp = item["_file"]
                fname = item["_filename"]
                content_type = metadata.get("content_type", "?")
                domain = metadata.get("domain", [])
                domain_str = ", ".join(domain) if domain else "?"
                ingested_at = item.get("ingested_at", "")[:19]

                with ui.card().classes("w-full"):
                    with ui.row().classes("w-full items-center gap-4"):
                        ui.label(f"📄 {fname}").classes("font-bold flex-1")
                        ui.badge(f"置信度: {confidence:.0%}", color="red")

                    ui.label(f"原因: {reason} | 时间: {ingested_at}").classes("text-xs text-gray-400")
                    ui.label(f"类型: {content_type} | 领域: {domain_str}").classes("text-xs text-gray-400")

                    if content:
                        ui.label(content).classes("text-xs text-gray-500 mt-1").style("white-space: pre-wrap")

                    with ui.row().classes("gap-2 mt-2"):
                        # 方式一：手动修正
                        async def _open_edit_dialog(item=item):
                            _show_dlq_edit_dialog(item, _refresh_dlq)

                        ui.button("✏️ 手动修正", on_click=_open_edit_dialog).props("color=blue flat")

                        # 方式二：重新上传文件
                        async def _open_upload_dialog(item=item):
                            _show_dlq_upload_dialog(item, _refresh_dlq)

                        ui.button("📎 重新上传", on_click=_open_upload_dialog).props("color=teal flat")

                        # 方式三：永久删除
                        del_dialog = ui.dialog()
                        with del_dialog:
                            with ui.card().classes("p-4"):
                                ui.label("⚠️ 确认永久删除？").classes("text-lg font-bold")
                                ui.label(f"文件: {fname}").classes("text-sm text-gray-500")
                                with ui.row().classes("gap-2 mt-4"):
                                    ui.button("取消", on_click=del_dialog.close).props("flat")
                                    ui.button("确认删除", on_click=lambda f=fp, dd=del_dialog: [
                                        _delete_dlq_file(f),
                                        log_activity("dlq_delete", "", os.path.basename(f)),
                                        dd.close(),
                                        ui.notify(f"已删除: {os.path.basename(f)}", type="positive"),
                                        _refresh_dlq(),
                                    ]).props("color=red")

                        ui.button("❌ 删除", on_click=del_dialog.open).props("color=red flat")

    _refresh_dlq()

    ui.button("🔄 刷新", on_click=_refresh_dlq).props("flat").classes("mt-2")


def _show_dlq_edit_dialog(item: dict, refresh_callback):
    """死信手动修正弹窗 — 编辑分类字段后重新走管道入库。"""
    content = item.get("content", "")
    metadata = item.get("metadata", {})
    fp = item["_file"]
    fname = item["_filename"]

    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("p-4 w-full max-w-lg"):
        ui.label(f"✏️ 手动修正: {fname}").classes("text-lg font-bold")
        ui.label("编辑分类字段后，点击确认将走正常管道重新入库。").classes("text-sm text-gray-500 mb-2")

        # 可编辑字段
        title_field = ui.input(
            label="标题",
            value=metadata.get("title", ""),
        ).classes("w-full")
        content_type_field = ui.input(
            label="内容类型 (content_type)",
            value=metadata.get("content_type", ""),
        ).classes("w-full")
        domain_field = ui.input(
            label="领域 (domain, 逗号分隔)",
            value=", ".join(metadata.get("domain", [])),
        ).classes("w-full")

        content_area = ui.textarea(
            label="原文内容",
            value=content,
        ).props("outlined rows=6").classes("w-full")

        with ui.row().classes("gap-2 mt-4"):
            ui.button("取消", on_click=dialog.close).props("flat")

            async def _submit():
                # 构建修正后的元数据
                new_meta = {
                    **metadata,
                    "title": title_field.value or "",
                    "content_type": content_type_field.value or metadata.get("content_type", "other"),
                    "domain": [d.strip() for d in domain_field.value.split(",") if d.strip()] if domain_field.value else [],
                }
                new_content = content_area.value or content

                try:
                    # 走正常摄入管道
                    result = await asyncio.to_thread(
                        kb_query.ingest,
                        text=new_content,
                        metadata=new_meta,
                        collection=STATE["active_collection"],
                        field_sources={k: "user" for k in new_meta},
                        overall_confidence=1.0,  # 手动修正，置信度设为1
                    )
                    if result.get("ok"):
                        _delete_dlq_file(fp)
                        log_activity("dlq_reingest", result.get("doc_id", ""), fname, STATE["active_collection"])
                        ui.notify(f"✅ 已重新入库: {fname}", type="positive")
                        dialog.close()
                        refresh_callback()
                    else:
                        ui.notify(f"入库失败: {result.get('error', '?')}", type="negative")
                except Exception as ex:
                    ui.notify(f"操作异常: {ex}", type="negative")

            ui.button("✅ 确认并入库", on_click=lambda: asyncio.ensure_future(_submit())).props("color=blue")

    dialog.open()


def _show_dlq_upload_dialog(item: dict, refresh_callback):
    """死信重新上传文件弹窗 — 换一个新文件替换旧的，走完整管道。"""
    fp = item["_file"]
    fname = item["_filename"]

    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes("p-4 w-full max-w-lg"):
        ui.label(f"📎 重新上传替换: {fname}").classes("text-lg font-bold")
        ui.label("上传新文件后将走完整管道（格式检测 → 提取 → AI分类 → 入库），替换旧内容。").classes("text-sm text-gray-500 mb-2")

        upload_result = ui.label("").classes("text-sm")

        def _on_upload(e):
            async def _handle():
                try:
                    from utils.file_handler import detect_file_type, extract_text, extract_auto_metadata, SIZE_LIMIT_MB
                    import tempfile

                    file_bytes = await e.file.read()
                    new_fname = e.file.name or "unknown"
                    fsize = len(file_bytes)
                    if fsize > SIZE_LIMIT_MB * 1024 * 1024:
                        ui.notify(f"⚠️ 文件超过 {SIZE_LIMIT_MB}MB 上限", type="warning")
                        return

                    suffix = os.path.splitext(new_fname)[1] or ".tmp"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tf:
                        tf.write(file_bytes)
                        temp_path = tf.name

                    try:
                        file_type = detect_file_type(temp_path)
                        extract_result = await asyncio.to_thread(extract_text, temp_path)
                        if isinstance(extract_result, dict) and extract_result.get("ocr_required"):
                            ui.notify("⚠️ 图片需先在摄入页 OCR，死信暂不支持图片重传", type="warning")
                            os.unlink(temp_path)
                            return

                        text = extract_result.get("text", "") if isinstance(extract_result, dict) else str(extract_result)
                        if len(text) > 5000:
                            text = text[:5000]

                        auto_meta = {}
                        try:
                            auto_meta_result = await asyncio.to_thread(extract_auto_metadata, temp_path, file_type)
                            auto_meta = auto_meta_result.get("flat", {}) if isinstance(auto_meta_result, dict) else {}
                        except Exception:
                            pass

                        # 走完整分类管道
                        import classify_pipeline
                        classify_result = await asyncio.to_thread(
                            classify_pipeline.classify_document,
                            text,
                            auto_meta,
                            STATE.get("current_project", "通用"),
                        )
                        if classify_result and classify_result.get("ok"):
                            annotated = classify_result.get("annotated", {})
                            cls = classify_result.get("classification", {})
                            field_sources = dict(annotated.get("field_sources", {}))
                            overall_conf = annotated.get("overall_confidence", 0.0)
                        else:
                            cls = {"content_type": "other"}
                            field_sources = {}
                            overall_conf = 0.0

                        result = await asyncio.to_thread(
                            kb_query.ingest,
                            text=text,
                            metadata={
                                **item.get("metadata", {}),
                                **cls,
                                "source_path": new_fname,
                                "ingest_method": "upload",
                                "metadata_source": "file",
                            },
                            collection=STATE["active_collection"],
                            field_sources=field_sources,
                            overall_confidence=overall_conf,
                        )

                        if result.get("ok"):
                            _delete_dlq_file(fp)
                            log_activity("dlq_reupload", result.get("doc_id", ""), new_fname, STATE["active_collection"])
                            ui.notify(f"✅ 新文件已入库，死信已清除", type="positive")
                            dialog.close()
                            refresh_callback()
                        else:
                            ui.notify(f"入库失败: {result.get('error', '?')}", type="negative")

                    finally:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)

                except Exception as ex:
                    ui.notify(f"上传处理异常: {ex}", type="negative")

            asyncio.ensure_future(_handle())

        upload = ui.upload(
            label="拖拽或点击上传新文件",
            auto_upload=True,
            multiple=False,
        ).classes("w-full").props("accept='.txt,.md,.json,.csv,.pdf,.epub,.html,.htm,.docx,.pptx'")
        upload.on_upload(_on_upload)

        ui.button("取消", on_click=dialog.close).props("flat mt-2")

    dialog.open()


# ═══════════════════════════════════════════
# 文档详情页 /doc/{doc_uid} — v0.9.0 D4
# ═══════════════════════════════════════════

@ui.page("/doc/{doc_uid}")
def page_doc_detail(doc_uid: str):
    """文档详情页 — 28 字段完整展示 + 分块列表 + 来源追踪。"""

    build_left_drawer()

    with ui.column().classes("w-full p-6"):
        # 返回按钮
        with ui.row().classes("w-full items-center gap-2 mb-4"):
            ui.link("← 返回知识库管理", "/hub").classes("text-sm text-gray-400 no-underline")

        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线", color="red")
            return

        # 加载文档元数据
        collection = STATE["active_collection"]
        meta_result = kb_query.list_documents(collection=collection, page=1, page_size=500)
        doc_meta = None
        if meta_result.get("ok"):
            for d in meta_result["documents"]:
                if d.get("doc_uid") == doc_uid:
                    doc_meta = d
                    break

        if not doc_meta:
            ui.markdown("### 📄 文档不存在")
            ui.label(f"未找到 doc_uid={doc_uid} 的记录，可能已被删除。").classes("text-gray-500")
            return

        # 加载分块
        chunk_result = kb_query.get_document(doc_uid, collection=collection)
        chunks = chunk_result.get("chunks", []) if chunk_result.get("ok") else []

        # ════════════════════
        # 标题区
        # ════════════════════
        title = doc_meta.get("title") or doc_meta.get("source") or "未知"
        ui.markdown(f"# 📄 {title}")
        if doc_meta.get("needs_review"):
            ui.badge("⚠️ 待审核", color="orange").classes("mb-2")

        # ════════════════════
        # 元数据卡片
        # ════════════════════
        ui.markdown("### 📋 元数据")
        with ui.card().classes("w-full p-4"):
            # 分组1: 分面
            with ui.row().classes("w-full gap-4 mb-3"):
                ui.markdown("#### 🏷️ 分面分类")
            with ui.row().classes("w-full gap-4 text-sm"):
                ui.label(f"**内容类型**: {doc_meta.get('content_type', 'N/A')}")
                ui.label(f"**领域**: {', '.join(doc_meta.get('domain', [])) or 'N/A'}")
                ui.label(f"**时效属性**: {doc_meta.get('temporal_nature', 'N/A')}")
                ui.label(f"**认知状态**: {doc_meta.get('epistemic_status', 'N/A')}")

            ui.separator()

            # 分组2: 内容
            with ui.row().classes("w-full gap-4 mb-3"):
                ui.markdown("#### 📝 内容信息")
            with ui.row().classes("w-full gap-4 text-sm"):
                ui.label(f"**来源**: {doc_meta.get('source', 'N/A')}")
                ui.label(f"**源路径**: {doc_meta.get('source_path', 'N/A')}")
                ui.label(f"**语言**: {doc_meta.get('language', 'N/A')}")
                ui.label(f"**分块数**: {len(chunks)}")

            ui.separator()

            # 分组3: 知识管理
            with ui.row().classes("w-full gap-4 mb-3"):
                ui.markdown("#### ⚙️ 知识管理")
            with ui.row().classes("w-full gap-4 text-sm"):
                ui.label(f"**置信度**: {doc_meta.get('overall_confidence', 0):.0%}")
                ui.label(f"**信任分**: {doc_meta.get('trust_score', 3)}/5")
                ui.label(f"**个人知识**: {'是' if doc_meta.get('is_personal') else '否'}")
                ui.label(f"**待审核**: {'是' if doc_meta.get('needs_review') else '否'}")

            ui.separator()

            # 分组4: 时间
            with ui.row().classes("w-full gap-4 mb-3"):
                ui.markdown("#### 🕐 时间")
            with ui.row().classes("w-full gap-4 text-sm"):
                ui.label(f"**创建时间**: {doc_meta.get('created_at', 'N/A')[:19]}")

        # ════════════════════
        # 分块内容
        # ════════════════════
        if chunks:
            ui.markdown("### 📦 分块内容")
            with ui.card().classes("w-full p-4"):
                for c in chunks:
                    chunk_text = c.get("text", "")
                    chunk_idx = c.get("chunk_index", 0)
                    chunk_title = c.get("title", "") or f"分块 {chunk_idx}"
                    with ui.expansion(f"#{chunk_idx} {chunk_title[:60]}", value=chunk_idx == 0).classes("w-full"):
                        ui.markdown(f"```\n{chunk_text[:2000]}\n```")
                        if len(chunk_text) > 2000:
                            ui.label(f"... 共 {len(chunk_text)} 字符，已截断").classes("text-xs text-gray-500")

        # ════════════════════
        # 操作区
        # ════════════════════
        ui.separator()
        with ui.row().classes("gap-2"):
            async def _delete_this():
                try:
                    result = await asyncio.to_thread(
                        kb_query.delete_document,
                        doc_uid,
                        collection=collection,
                    )
                    if result.get("ok"):
                        log_activity("delete", doc_uid, title, collection)
                        ui.notify("✅ 已删除", type="positive")
                        ui.run_javascript("window.location.href='/hub'")
                    else:
                        ui.notify(f"删除失败: {result.get('error', '?')}", type="negative")
                except Exception as ex:
                    ui.notify(f"操作异常: {ex}", type="negative")

            del_dialog = ui.dialog().props("persistent")
            with del_dialog:
                with ui.card().classes("p-4"):
                    ui.label("⚠️ 确认删除此文档？").classes("text-lg font-bold")
                    ui.label("所有分块将被永久删除，此操作不可撤销。").classes("text-sm text-gray-500")
                    with ui.row().classes("gap-2 mt-4"):
                        ui.button("取消", on_click=del_dialog.close).props("flat")
                        ui.button("确认删除", on_click=lambda: [
                            asyncio.ensure_future(_delete_this()),
                            del_dialog.close(),
                        ]).props("color=red")

            ui.button("🗑️ 删除此文档", on_click=del_dialog.open).props("color=red flat")
