"""
待审核标签 — 审核队列 UI（人在这里给 AI 不确定的文档"放行"或"丢弃"）。

【小白导读】
  AI 给文档打标签/分类时如果没把握，会把文档丢进"待审核队列"。
  这个页面把队列里的文档一条条列出来，点"通过并入库"=确认没问题正式收下；
  点"丢弃"=不要这篇。通过后会把文档的"待审核"标记关掉。
"""

import asyncio
import json
from nicegui import ui
import kb_query
from utils.state import STATE
from utils.activity_log import log_activity
async def _build_review_tab():
    """待审核标签页 — 列出 needs_review=True 的文档，支持通过/丢弃。"""
    ui.markdown("### 📋 待审核条目")
    ui.markdown("*AI 不太确定这些内容，请确认。*")

    review_container = ui.column().classes("w-full")

    async def _refresh_review():
        review_container.clear()
        with review_container:
            try:
                result = await asyncio.to_thread(
                    kb_query.list_documents,
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

    await _refresh_review()

    ui.button("🔄 刷新", on_click=_refresh_review).props("flat").classes("mt-2")


def _build_review_card(doc: dict, on_refresh):
    """渲染单个待审核文档卡片。"""
    doc_uid = doc.get("doc_id") or doc.get("doc_uid", "?")
    title = doc.get("title") or "未命名"
    source = doc.get("source") or doc.get("source_path") or "手动输入"
    confidence = doc.get("ingest_conf", 0)
    content_preview = doc.get("content_preview", "")[:200]
    content_type = doc.get("content_type", "?")
    domain = doc.get("domain", [])
    domain_str = ", ".join(domain) if domain else "未分类"

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center gap-4"):
            ui.markdown(f"**{title}**").classes("flex-1")
            ui.badge(f"入库置信度: {confidence:.0%}", color="orange" if confidence < 0.60 else "blue")

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
                    # 通过：把这篇文档的"待审核"标记关掉，正式入库（更新它所有分块）
                    await asyncio.to_thread(
                        kb_query.update_metadata,
                        doc_uid,
                        {"needs_review": False},
                        collection=STATE["active_collection"],
                    )
                    doc_title = doc.get("title", "") or doc.get("source", "")
                    log_activity("review_approve", doc_uid, doc_title, STATE["active_collection"])
                    ui.notify(f"✅ 已通过: {doc_uid[:12]}", type="positive")
                    on_refresh()
                except Exception as ex:
                    ui.notify(f"操作失败: {ex}", type="negative")

            ui.button("✅ 通过并入库", on_click=_approve).props("color=green flat")

            # 丢弃按钮（带确认）
            async def _drop():
                try:
                    await asyncio.to_thread(
                        kb_query.delete_document,
                        doc_uid,
                        collection=STATE["active_collection"],
                    )
                    doc_title = doc.get("title", "") or doc.get("source", "")
                    log_activity("review_drop", doc_uid, doc_title, STATE["active_collection"])
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

                        async def _confirm_drop():
                            await _drop()
                            drop_dialog.close()
                        ui.button("确认丢弃", on_click=_confirm_drop).props("color=red")

            ui.button("❌ 丢弃", on_click=drop_dialog.open).props("color=red flat")


