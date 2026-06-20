"""
Citrinitas · 熔知 — 文档注入页面

此模块包含文档注入页面（/）的函数。
从 main.py 拆分出来以降低主文件复杂度。
"""

import os
import sys
import asyncio
import json
from datetime import datetime, timezone

from nicegui import ui

import kb_query
from config import classifications
from field_cfg import FIELD_DISPLAY_CFG, SOURCE_ICON, PANEL_VALUES
from panel_funcs import build_result_panel, build_advanced_panel
from utils.file_handler import (
    detect_file_type, extract_text, extract_auto_metadata,
    SIZE_LIMIT_MB, FORMAT_DISPLAY_NAMES,
)
from utils.state import STATE
from utils.ui_shared import build_left_drawer


@ui.page("/")
def page_ingest():
    """文档注入页面（/）—— 两阶段智能摄入：内容准备 → AI 分析 + 人工确认 → 入库"""

    build_left_drawer()

    with ui.column().classes("w-full p-6"):
        ui.markdown("# 📥 文档注入")
        ui.markdown("*两阶段智能摄入：内容准备 → AI 分析 + 人工确认 → 入库*")

        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线，无法摄入。请启动 Qdrant。", color="red")
            return

        # ── 阶段一：内容输入 ──
        tabs = ui.tabs().props("align=left")
        with tabs:
            upload_tab = ui.tab("📎 文件上传")
            ocr_tab = ui.tab("📷 OCR 截图")
            manual_tab = ui.tab("✏️ 手动输入")
        tab_panels = ui.tab_panels(tabs, value=upload_tab).classes("w-full")

        content_text = ui.textarea(label="已提取的文本内容").props("outlined rows=10").classes("w-full")
        content_text_area = content_text
        source_label = ui.label("来源：--").classes("text-sm text-gray-500")

        ingest_content = ""
        ingest_source = ""
        ingest_method = ""

        # ── Tab 1: 文件上传 ──
        with tab_panels:
            with ui.tab_panel(upload_tab):
                # 动态生成支持格式列表（从 FORMAT_DISPLAY_NAMES）
                text_formats = [k for k in FORMAT_DISPLAY_NAMES if k not in ("jpeg","png","tiff","bmp","webp")]
                img_formats = [k for k in FORMAT_DISPLAY_NAMES if k in ("jpeg","png","tiff","bmp","webp")]
                fmt_parts = [f"**{f}** ({FORMAT_DISPLAY_NAMES[f]})" for f in text_formats]
                img_parts = [f"**{f}** ({FORMAT_DISPLAY_NAMES[f]})" for f in img_formats]
                ui.markdown(f"📄 文本格式：{' · '.join(fmt_parts)}").classes("text-sm text-gray-500")
                ui.markdown(f"🖼️ 图片格式（OCR）：{' · '.join(img_parts)}").classes("text-sm text-gray-400")
                upload = ui.upload(
                    label="拖拽或点击上传文件",
                    auto_upload=True,
                    max_file_size=SIZE_LIMIT_MB * 1024 * 1024,
                    multiple=False,
                ).classes("w-full").props("accept='.txt,.md,.json,.csv,.pdf,.epub,.html,.htm,.srt,.docx,.pptx,.png,.jpg,.jpeg,.bmp,.webp,.tiff'")

                up_result = ui.label("").classes("text-sm")

                def on_upload(e):
                    nonlocal ingest_content, ingest_source, ingest_method
                    temp_path = None
                    try:
                        import tempfile
                        file_bytes = e.content.read()
                        fname = e.name
                        fsize = len(file_bytes)
                        if fsize > SIZE_LIMIT_MB * 1024 * 1024:
                            ui.notify(f"⚠️ 文件 {fname} 超过 {SIZE_LIMIT_MB}MB 上限", type="warning")
                            return

                        # 保存到临时文件
                        suffix = os.path.splitext(fname)[1] or ".tmp"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tf:
                            tf.write(file_bytes)
                            temp_path = tf.name

                        # 检测文件类型
                        file_type = detect_file_type(temp_path)
                        STATE["file_info"] = file_type
                        ext_label = ".".join(file_type.get("extensions", ["?"]))

                        up_result.set_text(f"📎 {fname} · {fsize/1024:.1f}KB · {ext_label} · {file_type.get('format_name', '?')}")

                        # 格式识别预览（显示层级 + 元数据能力）
                        tier = file_type.get("tier", "?")
                        tier_name = file_type.get("tier_name", "")
                        has_meta = file_type.get("has_auto_metadata", False)
                        tier_badge = {1: "green", 2: "blue", 3: "orange", 4: "gray"}.get(tier, "gray")
                        meta_badge = "✅ 自带元数据" if has_meta else "🤖 需 AI 标注"
                        ui.badge(f"T{tier}: {tier_name}", color=tier_badge)
                        ui.badge(meta_badge, color="teal" if has_meta else "blue")

                        # 提取文本
                        extract_result = extract_text(temp_path)
                        if isinstance(extract_result, dict):
                            text = extract_result.get("text", "")
                        else:
                            text = str(extract_result)
                        if len(text) > 5000:
                            ui.notify(f"文本较长 ({len(text)} 字)，已截取前 5000 字发送给 AI 分析", type="warning")
                            text = text[:5000]

                        # 提取自动元数据
                        auto_meta_result = extract_auto_metadata(temp_path, file_type)
                        auto_meta = auto_meta_result.get("flat", {}) if isinstance(auto_meta_result, dict) else {}
                        STATE["auto_metadata"] = auto_meta

                        ingest_content = text
                        content_text.set_value(text)
                        ingest_source = f"文件: {fname}"
                        source_label.set_text(f"来源：{fname}")
                        ingest_method = "upload"
                        STATE["ingest_content"] = text
                        STATE["ingest_source"] = fname
                        STATE["ingest_method"] = "upload"
                        STATE["source_path"] = fname  # 原始文件路径标记

                        # 显示自动元数据
                        if auto_meta:
                            meta_lines = [f"📎 **{k}**: {v}" for k, v in auto_meta.items() if v]
                            if meta_lines:
                                ui.notify("文件元数据已自动提取", type="positive")

                    except Exception as ex:
                        ui.notify(f"❌ 处理失败: {ex}", type="negative")
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except OSError:
                                pass

                upload.on_upload(on_upload)

        # ── Tab 2: OCR ──
        with tab_panels:
            with ui.tab_panel(ocr_tab):
                ui.label("支持 OCR（PaddleOCR）识别截图、扫描件中的文字").classes("text-sm text-gray-400")
                ocr_upload = ui.upload(
                    label="上传图片进行 OCR",
                    auto_upload=True,
                    multiple=False,
                ).classes("w-full").props("accept='.png,.jpg,.jpeg,.bmp,.webp,.tiff'")

                ocr_result_label = ui.label("").classes("text-sm")

                def on_ocr(e):
                    nonlocal ingest_content, ingest_source, ingest_method
                    temp_path = None
                    try:
                        import tempfile
                        file_bytes = e.content.read()
                        fname = e.name

                        # 保存到临时文件
                        suffix = os.path.splitext(fname)[1] or ".tmp"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tf:
                            tf.write(file_bytes)
                            temp_path = tf.name

                        result = kb_query.ocr_image(temp_path)
                        text = result.get("ocr_text", "")
                        content_text.set_value(text)
                        ingest_content = text
                        ingest_source = f"OCR: {e.name}"
                        source_label.set_text(f"来源：OCR - {e.name}")
                        ingest_method = "ocr"
                        STATE["ingest_content"] = text
                        STATE["ingest_source"] = f"OCR: {e.name}"
                        STATE["ingest_method"] = "ocr"
                        STATE["source_path"] = f"ocr:{e.name}"  # OCR 来源标记（无源文件路径）
                        ocr_result_label.set_text(f"✅ 识别完成，{len(text)} 字")
                        if result.get("needs_correction"):
                            ocr_result_label.set_text(f"⚠️ 识别质量较低，建议 AI 纠错 ({len(text)} 字)")
                    except Exception as ex:
                        ui.notify(f"❌ OCR 失败: {ex}", type="negative")
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except OSError:
                                pass

                ocr_upload.on_upload(on_ocr)

        # ── Tab 3: 手动输入 ──
        with tab_panels:
            with ui.tab_panel(manual_tab):
                manual_text = ui.textarea(
                    label="粘贴或输入文本",
                    placeholder="直接粘贴内容...",
                ).props("outlined rows=12").classes("w-full")

                def on_manual_save():
                    nonlocal ingest_content, ingest_source, ingest_method
                    txt = manual_text.value or ""
                    content_text.set_value(txt)
                    ingest_content = txt
                    ingest_source = "手动输入"
                    source_label.set_text("来源：手动输入")
                    ingest_method = "manual"
                    STATE["ingest_content"] = txt
                    STATE["ingest_source"] = "手动输入"
                    STATE["ingest_method"] = "manual"
                    STATE["source_path"] = ""  # 手动输入，无源文件
                    # T10: 5000 字截断提醒
                    if len(txt) > 5000:
                        ui.notify(f"⚠️ 内容超过 5000 字（{len(txt)} 字），AI 分析将仅使用前 5000 字", type="warning")

                ui.button("📥 确认内容", on_click=on_manual_save).props("color=blue")

        ui.separator()

        # ── 阶段二：AI 分类 + 确认 ──
        ui.markdown("## 阶段二：AI 分析与元数据")
        ui.markdown("*AI 自动推断分类和标签，请确认后摄入。*")

        ai_cols = ui.row().classes("w-full gap-4")
        with ai_cols:
            ai_btn = ui.button("🤖 AI 分析", color="teal")
            ai_status = ui.label("等待分析...").classes("text-sm text-gray-500")

        # 结果面板区（AI 分析后渲染卡片式面板）
        result_container = ui.column().classes("w-full")
        advanced_container = ui.column().classes("w-full")

        ui.separator()

        # ── 摄入按钮 ──
        async def do_ingest():
            nonlocal ingest_content, ingest_method, ingest_source
            if not STATE["qdrant_online"]:
                ui.notify("⚠️ Qdrant 离线", type="negative")
                return
            if not ingest_content.strip():
                ui.notify("⚠️ 没有内容可摄入", type="negative")
                return

            # 从 PANEL_VALUES 读取当前值（用户可能已编辑）
            metadata = dict(PANEL_VALUES)

            # 补充系统字段
            metadata["source_path"] = STATE.get("source_path", "")
            metadata["ingest_method"] = ingest_method or "manual"
            _meta_source_map = {"upload": "file", "ocr": "ocr", "manual": "manual"}
            metadata["metadata_source"] = _meta_source_map.get(ingest_method, "manual")

            # 获取 AI 分析结果
            classify_result = STATE.get("classify_result")
            if classify_result and classify_result.get("ok"):
                annotated = classify_result.get("annotated", {})
                classification = classify_result.get("classification", {})
                field_sources = dict(annotated.get("field_sources", {}))
                overall_conf = annotated.get("overall_confidence", 0.0)

                # 检测用户修改：对比 PANEL_VALUES 与原始 classification
                for field in FIELD_DISPLAY_CFG:
                    panel_val = PANEL_VALUES.get(field)
                    orig_val = classification.get(field)
                    if isinstance(orig_val, list) and isinstance(panel_val, list):
                        if set(orig_val) != set(panel_val):
                            field_sources[field] = "user"
                    elif panel_val != orig_val:
                        field_sources[field] = "user"
            else:
                field_sources = {f: "user" for f in FIELD_DISPLAY_CFG}
                overall_conf = 0.0
                ui.notify("⚠️ 未执行 AI 分析，将使用当前值直接摄入", type="warning")

            # DLQ 检查
            if overall_conf >= 0.75:
                needs_review = False
                dlq = False
            elif overall_conf >= 0.40:
                needs_review = True
                dlq = False
            else:
                needs_review = False
                dlq = True

            if dlq:
                import time
                PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                dlq_dir = os.path.join(PROJECT_DIR, "local_data", "dead_letter")
                os.makedirs(dlq_dir, exist_ok=True)
                dlq_file = os.path.join(dlq_dir, f"{int(time.time())}.json")
                dlq_data = {
                    "content": ingest_content[:3000],
                    "metadata": metadata,
                    "confidence": overall_conf,
                    "field_sources": field_sources,
                    "reason": f"置信度过低（{overall_conf:.2f} < 0.40），需人工审核",
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                with open(dlq_file, "w", encoding="utf-8") as f:
                    json.dump(dlq_data, f, ensure_ascii=False, indent=2)
                ui.notify(
                    f"✋ 置信度过低（{overall_conf:.0%}），已放入死信队列待审核",
                    type="warning",
                )
                return

            if needs_review:
                metadata["needs_review"] = True

            try:
                result = await asyncio.to_thread(
                    kb_query.ingest,
                    text=ingest_content,
                    metadata=metadata,
                    collection=STATE["active_collection"],
                    field_sources=field_sources,
                    overall_confidence=overall_conf,
                )
                if result.get("ok"):
                    ui.notify(f"✅ 摄入成功！({result.get('chunks', '?')} 块, 置信度 {overall_conf:.0%})", type="positive")
                    # 重置表单
                    ingest_content = ""
                    content_text.set_value("")
                    source_label.set_text("来源：--")
                    STATE["source_path"] = ""
                    STATE.pop("classify_result", None)
                    PANEL_VALUES.clear()
                    result_container.clear()
                    advanced_container.clear()
                    refresh_system_state()
                else:
                    ui.notify(f"❌ 摄入失败: {result.get('error', '?')}", type="negative")
            except Exception as ex:
                ui.notify(f"❌ 异常: {ex}", type="negative")

        ui.button("🚀 摄入到知识库", on_click=do_ingest).props("color=green size=lg").classes("w-full mt-2")

        # ── AI 分析回调（阶段二：调用 classify_document 三层管道）──
        async def do_ai_analyze():
            nonlocal ingest_content
            if not ingest_content.strip():
                ui.notify("⚠️ 请先输入内容", type="warning")
                return

            ai_status.set_text("正在分析...")
            ai_btn.disable()
            try:
                # 传入文件元数据 + 当前项目（让 Layer 0 填 project_source）
                _proj = STATE.get("current_project", "通用")
                result = await asyncio.to_thread(
                    kb_query.classify_document,
                    ingest_content,
                    STATE.get("auto_metadata") if isinstance(STATE.get("auto_metadata"), dict) else None,
                    _proj,
                )
                if result and result.get("ok"):
                    cls = result.get("classification", {})
                    annotated = result.get("annotated", {})
                    STATE["classify_result"] = result
                    overall = annotated.get("overall_confidence", 0.0)
                    sources = annotated.get("field_sources", {})

                    # 填充 PANEL_VALUES（全局缓存，供面板和摄入使用）
                    PANEL_VALUES.clear()
                    for field in FIELD_DISPLAY_CFG:
                        PANEL_VALUES[field] = cls.get(field)

                    # 渲染卡片式结果面板
                    build_result_panel(annotated, cls, result_container)
                    build_advanced_panel(annotated, cls, advanced_container)

                    ai_status.set_text(f"✅ 分析完成（置信度 {overall:.0%}）")
                    ui.notify("AI 分析结果已渲染为卡片面板，可直接修改", type="positive")
                else:
                    ai_status.set_text("⚠️ 分析返回为空，将使用默认值摄入")
            except Exception as ex:
                ai_status.set_text(f"❌ 分析失败: {ex}")
                ui.notify(f"AI 分析失败: {ex}", type="negative")
            finally:
                ai_btn.enable()

        ai_btn.on_click(do_ai_analyze)
