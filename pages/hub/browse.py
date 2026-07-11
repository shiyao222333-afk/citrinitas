"""
浏览标签 — 文档列表 + 分页 + 过滤 + 批量删除。
"""

import asyncio
from nicegui import ui, context
import kb_query
from utils.state import STATE
from utils.ui_shared import set_active_collection
from utils.activity_log import log_activity
async def _build_browse_tab():
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

    async def _refresh_browse():
        """刷新文档列表（异步加载 + 客户端过滤）。"""
        doc_container.clear()
        batch_bar.clear()

        client = context.client

        current_page = 1
        page_size = 20
        total_pages = 1

        async def _go_prev():
            nonlocal current_page
            if current_page > 1:
                current_page -= 1
                await _load()

        async def _go_next():
            nonlocal current_page, total_pages
            if current_page < total_pages:
                current_page += 1
                await _load()

        async def _load():
            with client:
                nonlocal current_page, page_size, total_pages
                try:
                    result = await asyncio.to_thread(
                        kb_query.list_documents,
                        collection=STATE["active_collection"],
                        page=current_page,
                        page_size=page_size,
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
                    selection_label = ui.label(f"已选 0/{len(filtered)}").classes("text-sm text-gray-500")

                    def _on_selection_change():
                        selection_label.set_text(f"已选 {len(selected_ids)}/{len(filtered)}")

                    ui.button("🗑️ 批量删除选中", on_click=lambda: _batch_delete(selected_ids, _refresh_browse)).props("color=red flat")

                # 文档卡片
                with doc_container:
                    for idx, d in enumerate(filtered):
                        _build_doc_card(d, idx, selected_ids, _refresh_browse, _on_selection_change)

                # 分页控件
                total = result.get("total", 0)
                _calc_pages = max(1, (total + page_size - 1) // page_size) if total else 1
                total_pages = _calc_pages

                with ui.row().classes("w-full justify-center items-center gap-4 mt-4"):
                    prev_btn = ui.button("◀ 上一页", on_click=_go_prev).props("flat")
                    if current_page <= 1:
                        prev_btn.props("disabled")
                    ui.label(f"第 {current_page} 页 / 共 {total_pages} 页").classes("text-sm text-gray-500")
                    next_btn = ui.button("下一页 ▶", on_click=_go_next).props("flat")
                    if current_page >= total_pages:
                        next_btn.props("disabled")

        await _load()
    search_input.on("keydown.enter", lambda: _refresh_browse())
    ct_filter.on("update:model-value", lambda: _refresh_browse())
    domain_filter.on("update:model-value", lambda: _refresh_browse())
    temp_filter.on("update:model-value", lambda: _refresh_browse())
    epi_filter.on("update:model-value", lambda: _refresh_browse())
    sort_select.on("update:model-value", lambda: _refresh_browse())

    # 初始加载
    await _refresh_browse()

    ui.button("🔄 刷新", on_click=_refresh_browse).props("flat").classes("mt-2")


def _build_doc_card(doc: dict, idx: int, selected_ids: set, on_refresh, on_selection_change=None):
    """渲染单个文档卡片（浏览标签页用）。"""
    title = doc.get("title") or doc.get("source") or "未知"
    doc_uid = doc.get("doc_id") or doc.get("doc_uid", "")
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
                selected_ids.add(uid) if e.value else selected_ids.discard(uid),
                on_selection_change() if on_selection_change else None
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
    doc_uid = doc.get("doc_id") or doc.get("doc_uid", "")
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


async def _batch_delete(selected_ids: set, on_refresh):
    """批量删除选中的文档。"""
    if not selected_ids:
        ui.notify("未选择任何文档", type="warning")
        return

    client = context.client

    async def _do_batch_delete():
        with client:
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
    await _do_batch_delete()


