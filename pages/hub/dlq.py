"""
死信队列标签页 — DLQ 管理（置信度过低条目）。
"""

import os
import asyncio
import tempfile
from nicegui import ui
import kb_query
from utils.state import STATE
from utils.activity_log import log_activity
from .helpers import _load_dlq_files, _delete_dlq_file


async def _build_dlq_tab():
    """死信队列标签页 — 列出置信度 < 低阈值的条目，支持修正/上传/删除。
    v1.0.0: 旧守望 DLQ 已迁移到统一收件箱，此标签页仅显示置信度 DLQ。"""
    ui.markdown("### 🗑️ 死信队列")
    ui.markdown("*AI 置信度过低的内容，需要手动处理。*")

    dlq_container = ui.column().classes("w-full")

    def _refresh_dlq():
        dlq_container.clear()
        with dlq_container:
            json_items = _load_dlq_files()

            if not json_items:
                ui.badge("🎉 死信队列为空", color="green")
                ui.label("收件箱中的处理失败文件 → 请查看「📥 收件箱」标签页").classes("text-xs text-gray-500 mt-2")
                return

            ui.label(f"共 {len(json_items)} 条死信（置信度过低）").classes("text-sm text-gray-500 mb-2")

            # 辅助函数：避免在循环中重复定义
            def _make_edit_handler(item, refresh_callback):
                def _handler():
                    _show_dlq_edit_dialog(item, refresh_callback)
                return _handler

            def _make_upload_handler(item, refresh_callback):
                def _handler():
                    _show_dlq_upload_dialog(item, refresh_callback)
                return _handler

            # ── 置信度过低 DLQ（JSON 格式）──
            for item in json_items:
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
                        ui.badge("AI 不确定", color="orange")

                    ui.label(f"原因: {reason} | 时间: {ingested_at}").classes("text-xs text-gray-400")
                    ui.label(f"类型: {content_type} | 领域: {domain_str}").classes("text-xs text-gray-400")

                    if content:
                        ui.label(content).classes("text-xs text-gray-500 mt-1").style("white-space: pre-wrap")

                    with ui.row().classes("gap-2 mt-2"):
                        ui.button("✏️ 手动修正", on_click=_make_edit_handler(item, _refresh_dlq)).props("color=blue flat")
                        ui.button("📎 重新上传", on_click=_make_upload_handler(item, _refresh_dlq)).props("color=teal flat")

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
