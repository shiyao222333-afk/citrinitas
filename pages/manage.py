"""
Citrinitas · 熔知 — 文档管理页面

此模块包含文档管理页面（/manage）的函数。
从 main.py 拆分出来以降低主文件复杂度。
"""

import os
import asyncio

from nicegui import ui

import kb_query
from utils.state import STATE
from utils.ui_shared import build_left_drawer


@ui.page("/manage")
def page_manage():
    """文档管理页面（/manage）—— 列表、查看、删除"""

    build_left_drawer(active_page="manage")

    with ui.column().classes("w-full p-6"):
        ui.markdown("# 📄 文档管理")
        ui.markdown("*查看、删除知识库中的文档。*")

        # ── 过滤器 ──
        with ui.row().classes('w-full gap-4 items-center mb-4'):
            ui.label('过滤器：').classes('font-bold')
            filter_select = ui.select(
                options=['全部文档', '待审核', '已审核'],
                value='全部文档',
                label='审核状态'
            ).classes('w-64')

        async def _on_filter_change():
            val = filter_select.value
            nr = None if val == '全部文档' else (True if val == '待审核' else False)
            page_state['needs_review'] = nr
            await load_docs(1)
            filter_select.on('update:model-value', lambda e: _on_filter_change())

        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线，无法管理。", color="red")
            return

        # ── 状态 ──
        page_state = {"page": 1, "page_size": 20, "total": 0, "total_pages": 1, "needs_review": None}
        doc_list = ui.column().classes("w-full gap-2")
        pagination_row = ui.row().classes("w-full justify-center gap-2 mt-4")

        # ── 删除确认对话框 ──
        confirm_dlg = ui.dialog()
        dlg_doc_uid = {"val": ""}

        async def _do_delete():
            """确认删除（异步，不阻塞事件循环）。"""
            uid = dlg_doc_uid["val"]
            confirm_dlg.close()
            res = await asyncio.to_thread(
                kb_query.delete_document,
                uid,
                STATE["active_collection"],
            )
            if res.get("ok"):
                ui.notify(f"✅ 已删除 {res.get('deleted', 0)} 个分块", type="positive")
                await load_docs(page_state["page"])
            else:
                ui.notify(f"删除失败: {res.get('error', '')}", type="negative")

        with confirm_dlg:
            with ui.card():
                ui.label("⚠️ 确认删除").classes("text-lg font-bold")
                ui.label("删除后不可恢复。确定要删除此文档吗？")
                with ui.row():
                    ui.button("确认删除", on_click=_do_delete, color="red")
                    ui.button("取消", on_click=confirm_dlg.close)

        # ── 查看详情对话框 ──
        detail_dlg = ui.dialog()
        with detail_dlg:
            with ui.card().classes("w-800 max-w-full"):
                dlg_title = ui.markdown("")
                dlg_content = ui.markdown("")

        async def show_detail(doc_uid: str):
            """加载并显示文档详情（异步，不阻塞事件循环）。"""
            dlg_title.set_content("## ⏳ 加载中...")
            dlg_content.set_content("*正在获取文档内容...*")
            detail_dlg.open()
            res = await asyncio.to_thread(
                kb_query.get_document,
                doc_uid,
                STATE["active_collection"],
            )
            if not res.get("ok"):
                ui.notify(f"加载失败: {res.get('error', '')}", type="negative")
                detail_dlg.close()
                return
            chunks = res.get("chunks", [])
            title_text = chunks[0].get('title', '') if chunks else doc_uid
            dlg_title.set_content(f"## 📄 {title_text}")
            preview = "\n\n---\n\n".join(
                f"**分块 {c['chunk_index']}**\n```\n{c['text'][:500]}\n```" for c in chunks[:5]
            )
            if len(chunks) > 5:
                preview += f"\n\n...（共 {len(chunks)} 个分块）"
            dlg_content.set_content(preview)

        async def load_docs(page: int):
            """加载指定页（异步，不阻塞事件循环）。"""
            page = max(1, page)
            nr = page_state.get("needs_review", None)

            # 显示加载状态
            doc_list.clear()
            with doc_list:
                ui.spinner(size="lg")
                ui.label("正在加载文档列表...").classes("text-sm text-gray-400")

            # 后台线程执行阻塞调用
            res = await asyncio.to_thread(
                kb_query.list_documents,
                STATE["active_collection"],
                page=page,
                page_size=page_state["page_size"],
                needs_review=nr,
            )

            if not res.get("ok"):
                ui.notify(f"加载失败: {res.get('error', '')}", type="negative")
                return

            page_state["page"] = page
            page_state["total"] = res.get("total", 0)
            page_state["total_pages"] = res.get("total_pages", 1)

            doc_list.clear()
            with doc_list:
                for d in res.get("documents", []):
                    uid = d.get("doc_id") or d.get("doc_uid", "")
                    title = d.get("title", "") or d.get("source", "未知")
                    ct = d.get("content_type", "")
                    domains = ", ".join(d.get("domain", []))
                    n_chunks = d.get("chunk_count", 0)
                    with ui.card().classes("w-full"):
                        with ui.row().classes("w-full items-center gap-4"):
                            ui.markdown(f"**{title}**").classes("flex-1")
                            ui.label(f"类型: {ct}").classes("text-sm text-gray-500")
                            ui.label(f"领域: {domains}").classes("text-sm text-gray-500")
                            ui.label(f"分块: {n_chunks}").classes("text-sm text-gray-500")
                            with ui.row().classes("gap-1"):
                                ui.button(
                                    "👁️",
                                    on_click=lambda u=uid: show_detail(u),
                                    color="blue",
                                ).props("flat dense")
                                def _del(u=uid):
                                    dlg_doc_uid["val"] = u
                                    confirm_dlg.open()
                                ui.button("🗑️", on_click=_del, color="red").props("flat dense")

            # 分页
            pagination_row.clear()
            with pagination_row:
                tp = page_state["total_pages"]
                p = page_state["page"]
                ui.button(
                    "◀ 上一页",
                    on_click=lambda p=p: load_docs(p - 1),
                ).props("flat dense").set_enabled(p > 1)
                ui.label(f"第 {p} / {tp} 页（共 {page_state['total']} 篇）").classes("self-center")
                ui.button(
                    "下一页 ▶",
                    on_click=lambda p=p: load_docs(p + 1),
                ).props("flat dense").set_enabled(p < tp)

        # 初次加载（用 timer 触发异步加载，不阻塞页面渲染）
        async def _initial_load():
            await load_docs(1)
        ui.timer(0.1, _initial_load, once=True)
