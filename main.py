"""
Citrinitas · 熔知 — NiceGUI 主入口
v0.4.4 → NiceGUI migration (分面 v5.0)

纯 Python SPA 架构：页面切换不重跑脚本，WebSocket 实时通信
底层：FastAPI + Vue + Quasar + WebSocket

页面:
  /            → 文档注入（默认首页）
  /search      → 智能检索
  /hub         → 知识中枢
  /config      → 引擎配置
"""

import os
import sys
import threading
import time
import asyncio
import json
from datetime import datetime, timezone
import html as html_mod
from collections import defaultdict
from fastapi.responses import FileResponse

# ── 路径设置 ──
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import kb_query
from config import classifications
from utils.file_handler import (
    detect_file_type, extract_text, extract_auto_metadata, detect_encoding,
    SIZE_LIMIT_MB, FORMAT_DISPLAY_NAMES,
)

from nicegui import ui, app

# ── 启用 .env ──
ENV_FILE = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


# ═══════════════════════════════════════════
# 辅助函数
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


if os.environ.get("KB_EMBED_MODEL"):
    kb_query.EMBED_MODEL = os.environ["KB_EMBED_MODEL"]

# ═══════════════════════════════════════════
# 全局状态（替代 st.session_state）
# ═══════════════════════════════════════════
STATE = {
    "active_collection": kb_query.DEFAULT_COLLECTION,
    "collections": [],
    "qdrant_online": False,
    "stats": {},
    "embed_models": [],
    "llm_models": [],
    "ingest_content": "",
    "ingest_source": "",
    "ingest_method": "",
    "ingest_stage": "input",
    "classify_result": None,
    "auto_metadata": None,
    "file_info": None,
    "last_answer": None,
    "last_search": None,
}


def refresh_system_state():
    """刷新全局状态：Qdrant 连接、集合列表、统计信息（所有请求带 timeout）。"""
    import requests
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


# ── 启动时刷新状态（异步，不阻塞启动）──
import requests as _requests
_qdrant_alive = False
_r = None
try:
    print(f"[启动] 检查 Qdrant: {kb_query.QDRANT_URL}/collections", flush=True)
    _r = _requests.get(f"{kb_query.QDRANT_URL}/collections", timeout=3)
    _qdrant_alive = _r.status_code == 200
    print(f"[启动] Qdrant 状态: {_r.status_code} -> {_qdrant_alive}", flush=True)
except Exception as _e:
    print(f"[启动] Qdrant 离线: {_e}", flush=True)

if _qdrant_alive:
    refresh_system_state()
else:
    STATE["qdrant_online"] = False

del _r, _qdrant_alive
# _requests 保留（后续路由可能用到）

# 嵌入模型预设
EMBED_PRESETS = {
    "qwen3-embedding": "qwen3-embedding:4b",
    "bge-m3": "bge-m3:latest",
    "nomic-embed-text": "nomic-embed-text:latest",
    "mxbai-embed-large": "mxbai-embed-large:latest",
}


# ═══════════════════════════════════════════
# 共享 UI 函数
# ═══════════════════════════════════════════

def build_left_drawer():
    """构建左侧导航抽屉（所有页面共用）。"""
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
            ).classes("w-full").props('dense outlined dark')

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

            # 定时自动刷新状态（每 10 秒）
            ui.timer(10.0, _update_status)

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


def set_active_collection(name: str):
    STATE["active_collection"] = name


def _sys_status_section() -> tuple:
    """返回系统状态 UI 元素供页面复用。"""
    return STATE["qdrant_online"], STATE.get("stats", {})


# ═══════════════════════════════════════════
# 页面 1：文档注入（首页）
# ═══════════════════════════════════════════

@ui.page("/")
def page_ingest():
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

                ui.button("📥 确认内容", on_click=on_manual_save).props("color=blue")

        ui.separator()

        # ── 阶段二：AI 分类 + 确认 ──
        ui.markdown("## 阶段二：AI 分析与元数据")
        ui.markdown("*AI 自动推断分类和标签，请确认后摄入。*")

        # 确认卡片（初始隐藏）
        confirm_card = ui.card().classes("w-full").set_visibility(False)
        confirm_result = {"ok": False, "metadata": {}}

        ai_cols = ui.row().classes("w-full gap-4")
        with ai_cols:
            ai_btn = ui.button("🤖 AI 分析", color="teal")
            ai_status = ui.label("等待分析...").classes("text-sm text-gray-500")

        async def on_ai_analyze():
            """AI 分析回调：调用 auto_classify，展示确认卡片"""
            nonlocal ingest_content, ingest_method, ingest_source
            if not ingest_content.strip():
                ui.notify("⚠️ 没有内容可分析", type="negative")
                return
            ai_status.text = "AI 分析中..."
            ai_btn.disable()

            try:
                # 准备元数据（传入文件元数据，让 AI 参考）
                meta_for_ai = STATE.get("auto_metadata", {}) or {}
                result = await asyncio.to_thread(
                    kb_query.auto_classify,
                    text=ingest_content[:3000],
                    metadata=meta_for_ai if isinstance(meta_for_ai, dict) else None,
                )
                if not result.get("ok"):
                    ui.notify(f"AI 分析失败: {result.get('error', '')}", type="negative")
                    return

                cls = result.get("classification", {})
                conf = cls.get("confidence", {})
                overall = conf.get("overall", 0.5) if isinstance(conf, dict) else 0.5

                # 存储到 STATE
                STATE["classify_result"] = result

                # 展示确认卡片
                with confirm_card:
                    confirm_card.clear()
                    with ui.column().classes("w-full gap-3"):
                        ui.markdown(f"### ✅ AI 分析完成（置信度 {overall:.0%}）")

                        # 文件元数据（如果有）
                        auto_meta = STATE.get("auto_metadata", {}) or {}
                        if auto_meta:
                            ui.markdown("**📎 文件元数据（已自动提取）**")
                            with ui.grid(columns=2).classes("w-full gap-2"):
                                for k, v in auto_meta.items():
                                    if v:
                                        ui.label(f"{k}:").classes("font-bold")
                                        ui.label(str(v)).classes("text-sm")

                        # AI 分析结果
                        ui.markdown("**🤖 AI 分析结果（请确认/修改）**")
                        with ui.grid(columns=2).classes("w-full gap-2"):
                            ai_content_type = ui.select(
                                options=[o[0] for o in classifications.CONTENT_TYPE_OPTIONS],
                                label="内容类型",
                                value=cls.get("content_type", "knowledge"),
                            ).classes("w-full")
                            ai_domain = ui.select(
                                options=[o[0] for o in classifications.DOMAIN_OPTIONS],
                                label="领域",
                                multiple=True,
                                value=cls.get("domain", []),
                            ).classes("w-full").props("use-chips")
                            ai_temporal = ui.select(
                                options=[o[0] for o in classifications.TEMPORAL_NATURE_OPTIONS],
                                label="时效属性",
                                value=cls.get("temporal_nature", "timeboxed"),
                            ).classes("w-full")
                            ai_epistemic = ui.select(
                                options=[o[0] for o in classifications.EPISTEMIC_STATUS_OPTIONS],
                                label="认知验证",
                                value=cls.get("epistemic_status", "unverified"),
                            ).classes("w-full")

                        # 确认/取消按钮
                        with ui.row().classes("w-full gap-2 mt-4"):
                            def on_confirm():
                                confirm_card.set_visibility(False)
                                # 收集 AI 表单的值
                                confirmed_meta = {
                                    "content_type": ai_content_type.value,
                                    "domain": list(ai_domain.value) if ai_domain.value else [],
                                    "temporal_nature": ai_temporal.value,
                                    "epistemic_status": ai_epistemic.value,
                                }
                                STATE["classify_result"] = {"ok": True, "classification": confirmed_meta}
                                ui.notify("✅ 元数据已确认，可点击「摄入」", type="positive")
                                ai_status.text = f"✅ 已确认（置信度 {overall:.0%}）"

                            def on_cancel():
                                confirm_card.set_visibility(False)
                                STATE.pop("classify_result", None)
                                ui.notify("已取消 AI 分析", type="info")

                            ui.button("✅ 确认并入库", on_click=on_confirm, color="green")
                            ui.button("取消", on_click=on_cancel, color="grey")

                confirm_card.set_visibility(True)
                ai_status.text = f"✅ 分析完成（置信度 {overall:.0%}），请确认元数据"

            except Exception as ex:
                ui.notify(f"AI 分析出错: {ex}", type="negative")
            finally:
                ai_btn.enable()

        ai_btn.on_click(on_ai_analyze)

        # 四核心分面表单（简化版）
        with ui.row().classes("w-full gap-4 mt-4"):
            with ui.column().classes("flex-1"):
                ct_options = [o[0] for o in classifications.CONTENT_TYPE_OPTIONS]
                ct_display = {o[0]: o[1] for o in classifications.CONTENT_TYPE_OPTIONS}
                content_type = ui.select(
                    label="内容类型 *",
                    options=ct_options,
                    value="knowledge",
                ).classes("w-full")

            with ui.column().classes("flex-1"):
                dm_options = [o[0] for o in classifications.DOMAIN_OPTIONS]
                dm_display = {o[0]: o[1] for o in classifications.DOMAIN_OPTIONS}
                domain = ui.select(
                    label="主题域 *",
                    options=dm_options,
                    multiple=True,
                ).classes("w-full").props("use-chips")

        with ui.row().classes("w-full gap-4 mt-2"):
            with ui.column().classes("flex-1"):
                tn_options = [o[0] for o in classifications.TEMPORAL_NATURE_OPTIONS]
                temporal_nature = ui.select(
                    label="时效属性 *",
                    options=tn_options,
                    value="timeboxed",
                ).classes("w-full")

            with ui.column().classes("flex-1"):
                ep_options = [o[0] for o in classifications.EPISTEMIC_STATUS_OPTIONS]
                epistemic_status = ui.select(
                    label="认知验证 *",
                    options=ep_options,
                    value="unverified",
                ).classes("w-full")

        with ui.row().classes("w-full gap-4 mt-2"):
            with ui.column().classes("flex-1"):
                lc_options = [o[0] for o in classifications.LIFECYCLE_OPTIONS]
                lifecycle = ui.select(
                    label="工作流阶段",
                    options=lc_options,
                    value="published",
                ).classes("w-full")

            with ui.column().classes("flex-1"):
                project_source = ui.input(
                    label="关联项目",
                    value="",
                    placeholder="如：智能台灯Pro",
                ).classes("w-full")

        # 置信度 + 关键词
        with ui.row().classes("w-full gap-4 mt-2"):
            trust_score = ui.number(label="可信度 (0-5)", value=3, min=0, max=5, step=1).classes("w-1/3")
            keywords = ui.input(label="关键词（逗号分隔）", placeholder="如: 机器学习, 神经网络, 深度学习").classes("w-2/3")

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

            # ── 域字段可选了（AI 会自动填，不再强制用户手动选）──
            domain_val = domain.value or []

            try:
                # 元数据来源：根据摄入方式标记
                _meta_source_map = {"upload": "file", "ocr": "ocr", "manual": "manual"}
                metadata = {
                    "content_type": content_type.value,
                    "domain": list(domain_val) if isinstance(domain_val, (list, tuple)) else [],
                    "temporal_nature": temporal_nature.value,
                    "epistemic_status": epistemic_status.value,
                    "lifecycle": lifecycle.value,
                    "project_source": (project_source.value or "").strip(),
                    "trust_score": trust_score.value,
                    "keywords": [k.strip() for k in (keywords.value or "").split(",") if k.strip()],
                    "source": ingest_source,
                    "source_path": STATE.get("source_path", ""),
                    "ingest_method": ingest_method or "manual",
                    "metadata_source": _meta_source_map.get(ingest_method, "manual"),
                }

                # ── 合并 AI 分类结果（全量字段）──
                cls_result = STATE.get("classify_result", {}).get("classification", {})
                if cls_result:
                    # 只填充用户未手动设置的字段（避免覆盖 UI 手动选择）
                    metadata.update({k: v for k, v in cls_result.items() if k not in metadata})

                # ── 置信度路由 ──
                classify_result = STATE.get("classify_result", {})
                confidence = classify_result.get("classification", {}).get("confidence", {})
                overall_conf = confidence.get("overall", 0.5) if isinstance(confidence, dict) else 0.5

                if overall_conf >= 0.8:
                    needs_review = False
                    dlq = False
                elif overall_conf >= 0.5:
                    needs_review = True
                    dlq = False
                else:
                    # 置信度过低 → 死信队列
                    needs_review = False
                    dlq = True

                if dlq:
                    # 写入 Dead Letter Queue
                    import json, time as _time
                    dlq_dir = os.path.join(PROJECT_DIR, "local_data", "dead_letter")
                    os.makedirs(dlq_dir, exist_ok=True)
                    dlq_file = os.path.join(dlq_dir, f"{int(_time.time())}.json")
                    dlq_data = {
                        "content": ingest_content[:3000],
                        "metadata": metadata,
                        "confidence": confidence,
                        "reason": f"置信度过低（{overall_conf:.2f} < 0.5），需人工审核",
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                    }
                    with open(dlq_file, "w", encoding="utf-8") as f:
                        json.dump(dlq_data, f, ensure_ascii=False, indent=2)
                    ui.notify(
                        f"✋ 置信度过低（{overall_conf:.1%}），已放入死信队列待审核",
                        type="warning",
                    )
                    return

                if needs_review:
                    metadata["needs_review"] = True

                result = await asyncio.to_thread(
                    kb_query.ingest,
                    text=ingest_content,
                    metadata=metadata,
                    collection=STATE["active_collection"],
                )
                if result.get("ok"):
                    ui.notify(f"✅ 摄入成功！({result.get('chunks', '?')} 块)", type="positive")
                    # 重置
                    ingest_content = ""
                    content_text.set_value("")
                    source_label.set_text("来源：--")
                    content_type.set_value("knowledge")
                    domain.set_value([])
                    temporal_nature.set_value("timeboxed")
                    epistemic_status.set_value("unverified")
                    lifecycle.set_value("published")
                    project_source.set_value("")
                    STATE["source_path"] = ""
                    refresh_system_state()
                else:
                    ui.notify(f"❌ 摄入失败: {result.get('error', '?')}", type="negative")
            except Exception as ex:
                ui.notify(f"❌ 异常: {ex}", type="negative")

        ui.button("🚀 摄入到知识库", on_click=do_ingest).props("color=green size=lg").classes("w-full mt-2")

        # AI 分析回调
        async def do_ai_analyze():
            nonlocal ingest_content
            if not ingest_content.strip():
                ui.notify("⚠️ 请先输入内容", type="warning")
                return

            llm_configured = bool(os.environ.get("KB_LLM_API_KEY"))
            if not llm_configured:
                ui.notify("⚠️ 未配置 LLM（请在引擎配置中设置 API Key）", type="warning")
                return

            ai_status.set_text("正在分析...")
            try:
                result = await asyncio.to_thread(kb_query.auto_classify, ingest_content)
                if result and result.get("ok"):
                    cls = result.get("classification", result)
                    STATE["classify_result"] = result
                    ai_status.set_text("✅ 分析完成！")
                    # 自动填充表单
                    ct_val = cls.get("content_type", "knowledge")
                    if ct_val in ct_options:
                        content_type.set_value(ct_val)
                    dm_val = cls.get("domain", [])
                    if dm_val:
                        if isinstance(dm_val, str):
                            dm_val = [dm_val]
                        valid_dm = [d for d in dm_val if d in dm_options]
                        if valid_dm:
                            domain.set_value(valid_dm)
                    tn_val = cls.get("temporal_nature", "timeboxed")
                    if tn_val in tn_options:
                        temporal_nature.set_value(tn_val)
                    ep_val = cls.get("epistemic_status", "unverified")
                    if ep_val in ep_options:
                        epistemic_status.set_value(ep_val)
                    lc_val = cls.get("lifecycle", "published")
                    if lc_val in lc_options:
                        lifecycle.set_value(lc_val)
                    ts = cls.get("trust_score", 3)
                    trust_score.set_value(max(0, min(5, int(ts) if ts else 3)))
                    kw = cls.get("keywords", [])
                    if kw:
                        keywords.set_value(", ".join(kw if isinstance(kw, list) else [str(kw)]))
                    ui.notify("AI 分析结果已自动填入，可直接摄入", type="positive")
                else:
                    ai_status.set_text("⚠️ 分析返回为空，将使用默认值摄入")
            except Exception as ex:
                ai_status.set_text(f"❌ 分析失败: {ex}")
                ui.notify(f"AI 分析失败: {ex}", type="negative")

        ai_btn.on_click(do_ai_analyze)


# ═══════════════════════════════════════════
# 页面 2：智能检索
# ═══════════════════════════════════════════

@ui.page("/search")
def page_search():
    build_left_drawer()

    with ui.column().classes("w-full p-6"):
        ui.markdown("# 💬 智能检索")
        ui.markdown("*语义搜索 + AI 问答：输入问题，勾选选项控制搜索行为。*")

        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线，无法搜索。", color="red")
            return

        # 搜索范围
        with ui.row().classes("w-full gap-4 items-end"):
            search_col = ui.select(
                label="📚 搜索范围",
                options=STATE["collections"] if STATE["collections"] else [STATE["active_collection"]],
                value=STATE["active_collection"],
            ).classes("w-64")

        # 搜索栏
        with ui.row().classes("w-full gap-2 items-end mt-4"):
            query_input = ui.input(
                label="输入问题或关键词",
                placeholder="例如：齿轮的失效形式有哪些？",
            ).classes("flex-1")

            top_k = ui.number(label="Top K", value=5, min=1, max=20, step=1).classes("w-20")
            use_llm = ui.switch("使用 AI 回答", value=True)

        search_btn = ui.button("🔍 搜索").props("color=blue size=lg")
        results_area = ui.column().classes("w-full mt-6")

        async def do_search():
            results_area.clear()
            query = (query_input.value or "").strip()
            if not query:
                ui.notify("请输入搜索内容", type="warning")
                return

            try:
                if use_llm.value:
                    # 先搜索（较快），显示中间状态
                    with results_area:
                        ui.spinner(size="lg")
                        ui.label("🔍 正在搜索相关文档...").classes("text-sm text-gray-400")

                    search_result = await asyncio.to_thread(
                        kb_query.search,
                        query,
                        top_k.value,
                        search_col.value,
                    )

                    # 再调用 LLM 合成答案（可能较慢）
                    with results_area:
                        results_area.clear()
                        ui.spinner(size="lg")
                        ui.label("🤖 正在调用 AI 合成答案（首次加载模型约需30秒）...").classes("text-sm text-gray-400")

                    result = await asyncio.to_thread(
                        kb_query.answer,
                        query,
                        top_k.value,
                        search_col.value,
                        output_dir=kb_query.OUTPUT_DIR,
                    )

                    with results_area:
                        results_area.clear()
                        if result.get("ok"):
                            ui.markdown("### 🤖 AI 回答")
                            answer_text = result.get("synthesis", "无回答")
                            ui.markdown(answer_text)

                            # HTML 报告链接
                            html_path = result.get("html")
                            if html_path and os.path.exists(html_path):
                                with ui.card().classes("w-full bg-blue-50"):
                                    ui.markdown("#### 📄 完整报告已生成")
                                    ui.label(f"文件: {os.path.basename(html_path)}").classes("text-xs text-gray-500")
                                    ui.button("🌐 在浏览器打开", on_click=lambda p=os.path.basename(html_path): ui.run_javascript(f'window.open("/reports/{p}", "_blank")')).props("dense flat color=blue")

                            chunks = result.get("chunks", [])
                            if chunks:
                                ui.separator()
                                ui.markdown("### 📚 来源引用")
                                for i, c in enumerate(chunks):
                                    render_chunk_card(c, i+1)
                        else:
                            # LLM 不可用，回退显示搜索结果
                            error_msg = result.get("error", "")
                            if "LLM API" in error_msg or "未配置" in error_msg:
                                ui.notify("💡 LLM 未配置，已回退为纯搜索模式。在配置页设置 API Key 后可启用 AI 回答。", type="info")
                            else:
                                ui.notify(f"AI 回答失败: {error_msg}", type="warning")

                            # 回退显示搜索结果
                            ui.markdown("### 🔍 搜索结果（AI 未启用）")
                            sr = search_result
                            for i, c in enumerate(sr.get("chunks", [])):
                                render_chunk_card(c, i+1)

                    STATE["last_answer"] = result
                else:
                    with results_area:
                        ui.spinner(size="lg").classes("self-center")
                        ui.label("🔍 正在搜索...").classes("text-sm text-gray-400")
                        await asyncio.sleep(0.1)

                    result = await asyncio.to_thread(
                        kb_query.search,
                        query,
                        top_k.value,
                        search_col.value,
                    )
                    with results_area:
                        results_area.clear()
                        ui.markdown("### 🔍 搜索结果")
                        for i, c in enumerate(result.get("chunks", [])):
                            render_chunk_card(c, i+1)
                    STATE["last_search"] = result

                refresh_system_state()
            except Exception as ex:
                with results_area:
                    results_area.clear()
                    ui.notify(f"搜索失败: {ex}", type="negative")

        search_btn.on_click(do_search)


# ═══════════════════════════════════════════
# 页面 3：知识中枢
# ═══════════════════════════════════════════

@ui.page("/hub")
def page_hub():
    build_left_drawer()

    with ui.column().classes("w-full p-6"):
        ui.markdown("# 🗂️ 知识中枢")
        ui.markdown("*知识库集合的指挥中心 — 创建、管理、切换、重建。*")

        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线，请先启动。", color="red")
            return

        # 集合列表卡片
        collections = STATE["collections"]
        current = STATE["active_collection"]
        stats = STATE.get("stats", {})

        with ui.row().classes("w-full gap-4"):
            with ui.card().classes("flex-1"):
                ui.markdown("### 📊 集合概览")
                ui.label(f"当前知识库：**{current}**")
                ui.label(f"集合数量：{len(collections)}")
                ui.label(f"文档块数：{stats.get('points', '--')}")
                ui.label(f"向量维度：{stats.get('dim', '--')}")

            with ui.card().classes("flex-1"):
                ui.markdown("### 🔧 操作")
                new_col_name = ui.input(label="新知识库名称", placeholder="输入名称...").classes("mb-2")

                def create_col():
                    name = (new_col_name.value or "").strip()
                    if not name:
                        ui.notify("请输入名称", type="warning")
                        return
                    try:
                        kb_query.create_collection(name)
                        ui.notify(f"✅ 知识库「{name}」已创建", type="positive")
                        refresh_system_state()
                        new_col_name.set_value("")
                    except Exception as ex:
                        ui.notify(f"创建失败: {ex}", type="negative")

                ui.button("➕ 创建知识库", on_click=create_col).props("color=blue").classes("mb-2")

                # 清空集合（带确认对话框）
                def do_clear_collection():
                    try:
                        result = kb_query.clear_collection(STATE["active_collection"])
                        if result.get("ok"):
                            ui.notify(f"✅ 已清空 {result.get('deleted', 0)} 条", type="positive")
                            refresh_system_state()
                        else:
                            ui.notify(f"清空失败: {result.get('error', '?')}", type="negative")
                    except Exception as ex:
                        ui.notify(f"清空失败: {ex}", type="negative")

                # 确认对话框（布局时创建，默认隐藏）
                clear_dialog = ui.dialog().props("persistent")
                with clear_dialog:
                    with ui.card().classes("p-4"):
                        clear_warn = ui.label("⚠️ 确认清空知识库？").classes("text-lg font-bold")
                        clear_detail = ui.label("").classes("text-sm text-gray-500")
                        with ui.row().classes("gap-2 mt-4"):
                            ui.button("取消", on_click=clear_dialog.close).props("flat")
                            ui.button(
                                "确认清空",
                                on_click=lambda: [do_clear_collection(), clear_dialog.close()],
                            ).props("color=red")

                clear_btn = ui.button("🗑️ 清空当前库").props("color=red flat")
                with clear_btn:
                    ui.tooltip("⚠️ 此操作不可撤销")

                def on_clear_click():
                    clear_detail.set_text(
                        f"知识库「{STATE['active_collection']}」中的所有数据将"
                        f"被删除，此操作不可撤销。"
                    )
                    clear_dialog.open()

                clear_btn.on_click(on_clear_click)

        # 切换集合
        if len(collections) > 1:
            ui.separator()
            ui.markdown("### 🔄 切换知识库")
            with ui.row().classes("w-full gap-2"):
                for c in collections:
                    color = "green" if c == current else "grey"
                    ui.button(c, on_click=lambda c=c: set_active_collection(c)).props(f"color={color} flat")


# ═══════════════════════════════════════════
# 页面 4：引擎配置
# ═══════════════════════════════════════════

@ui.page("/config")
def page_config():
    build_left_drawer()

    with ui.column().classes("w-full p-6"):
        ui.markdown("# ⚙️ 引擎配置")
        ui.markdown("*配置底层引擎参数。保存后写入 `.env` 文件。*")

        tabs = ui.tabs().props("align=left")
        with tabs:
            llm_tab = ui.tab("🤖 LLM")
            embed_tab = ui.tab("🧬 嵌入模型")
            sys_tab = ui.tab("⚙️ 系统")
        panels = ui.tab_panels(tabs, value=llm_tab).classes("w-full")

        # ── LLM 配置 ──
        with panels:
            with ui.tab_panel(llm_tab):
                ui.markdown("### 大语言模型配置")
                llm_key = ui.input(
                    label="API Key",
                    password=True,
                    password_toggle_button=True,
                    value=os.environ.get("KB_LLM_API_KEY", ""),
                ).classes("w-full")
                llm_base = ui.input(
                    label="API Base URL",
                    value=os.environ.get("KB_LLM_BASE_URL", "https://api.deepseek.com"),
                ).classes("w-full")
                llm_model = ui.input(
                    label="模型名称",
                    value=os.environ.get("KB_LLM_MODEL", "deepseek-chat"),
                ).classes("w-full")

                def save_llm():
                    data = {
                        "KB_LLM_API_KEY": llm_key.value or "",
                        "KB_LLM_BASE_URL": llm_base.value or "",
                        "KB_LLM_MODEL": llm_model.value or "",
                    }
                    _save_env(data)
                    ui.notify("✅ LLM 配置已保存", type="positive")

                ui.button("💾 保存 LLM 配置", on_click=save_llm).props("color=blue")

            # ── 嵌入模型 ──
            with ui.tab_panel(embed_tab):
                ui.markdown("### 嵌入模型管理")
                models = STATE["embed_models"]

                if models:
                    # Handle both dict and string format
                    rows = []
                    for m in models:
                        if isinstance(m, dict):
                            rows.append({"name": m.get("name", "?"), "size": m.get("size", "?"), "status": "✅"})
                        else:
                            rows.append({"name": str(m), "size": "-", "status": "✅"})
                    embed_table = ui.aggrid({
                        "columnDefs": [
                            {"headerName": "模型名", "field": "name", "width": 200},
                            {"headerName": "大小", "field": "size", "width": 100},
                            {"headerName": "状态", "field": "status", "width": 100},
                        ],
                        "rowData": rows,
                    }).classes("w-full h-64")

                ui.markdown("#### 预设模型")
                for preset_name, preset_full in EMBED_PRESETS.items():
                    with ui.row().classes("gap-2 items-center"):
                        ui.label(f"**{preset_name}** → `{preset_full}`")

                current_embed = ui.input(
                    label="当前嵌入模型",
                    value=os.environ.get("KB_EMBED_MODEL", kb_query.EMBED_MODEL),
                ).classes("w-full")

                def save_embed():
                    val = (current_embed.value or "").strip()
                    if val:
                        _save_env({"KB_EMBED_MODEL": val})
                        os.environ["KB_EMBED_MODEL"] = val
                        kb_query.EMBED_MODEL = val
                        ui.notify("✅ 嵌入模型已保存", type="positive")

                ui.button("💾 保存", on_click=save_embed).props("color=blue")

            # ── 系统配置 ──
            with ui.tab_panel(sys_tab):
                ui.markdown("### 系统设置")
                kb_root = ui.input(
                    label="知识库根目录",
                    value=os.environ.get("KB_ROOT_PATH", os.path.join(PROJECT_DIR, "local_data")),
                ).classes("w-full")

                def save_sys():
                    _save_env({"KB_ROOT_PATH": kb_root.value or ""})
                    ui.notify("✅ 系统配置已保存", type="positive")

                ui.button("💾 保存", on_click=save_sys).props("color=blue")

                ui.separator()
                ui.markdown("### 版本信息")
                ui.label(f"Citrinitas: v{kb_query.__version__}")
                ui.label(f"NiceGUI: 3.13.0")
                ui.label(f"Qdrant: {kb_query.QDRANT_URL}")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _save_env(kv: dict):
    """增量写入 .env 文件。"""
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

    for key, val in kv.items():
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0].strip() == key:
                lines[i] = f"{key}={val}\n"
                found = True
                break
        if not found:
            lines.append(f"{key}={val}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

def _auto_shutdown():
    """后台线程：当所有浏览器标签页关闭时自动退出。"""
    CHECK = 3
    IDLE_MAX = 3
    time.sleep(10)  # 等 NiceGUI 启动
    idle = 0
    while True:
        time.sleep(CHECK)
        try:
            # NiceGUI app.storage 和 WebSocket 连接检测
            import requests
            requests.get("http://localhost:8080", timeout=2)
            idle = 0
        except Exception:
            idle += 1
            if idle >= IDLE_MAX:
                print("\n[Citrinitas] 浏览器已关闭，自动退出。")
                os._exit(0)


@app.on_startup
def startup():
    refresh_system_state()
    threading.Thread(target=_auto_shutdown, daemon=True).start()


@app.get("/reports/{filename}")
def _serve_report(filename: str):
    """Serve report HTML/PDF files from local_data/reports/."""
    file_path = os.path.join(PROJECT_DIR, "local_data", "reports", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    from fastapi.responses import JSONResponse
    return JSONResponse({"error": "File not found"}, status_code=404)


# ═══════════════════════════════════════
# 页面 4：文档管理
# ═══════════════════════════════════════

@ui.page("/manage")
def page_manage():
    """文档管理页面：列表、查看、删除。"""
    build_left_drawer()

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
            def _on_filter_change():
                val = filter_select.value
                nr = None if val == '全部文档' else (True if val == '待审核' else False)
                page_state['needs_review'] = nr
                load_docs(1)
            filter_select.on('update:model-value', lambda e: _on_filter_change())


        if not STATE["qdrant_online"]:
            ui.badge("⚠️ Qdrant 离线，无法管理。", color="red")
            return

        # ── 状态 ──
        page_state = {"page": 1, "page_size": 20, "total": 0, "total_pages": 1}
        doc_list = ui.column().classes("w-full gap-2")
        pagination_row = ui.row().classes("w-full justify-center gap-2 mt-4")

        # ── 删除确认对话框 ──
        confirm_dlg = ui.dialog()
        dlg_doc_uid = {"val": ""}
        with confirm_dlg:
            with ui.card():
                ui.label("⚠️ 确认删除").classes("text-lg font-bold")
                ui.label("删除后不可恢复。确定要删除此文档吗？")
                with ui.row():
                    def _do_delete():
                        uid = dlg_doc_uid["val"]
                        confirm_dlg.close()
                        res = kb_query.delete_document(uid, STATE["active_collection"])
                        if res.get("ok"):
                            ui.notify(f"✅ 已删除 {res.get('deleted', 0)} 个分块", type="positive")
                            load_docs(page_state["page"])
                        else:
                            ui.notify(f"删除失败: {res.get('error', '')}", type="negative")
                    ui.button("确认删除", on_click=_do_delete, color="red")
                    ui.button("取消", on_click=lambda: confirm_dlg.close())

        # ── 查看详情对话框 ──
        detail_dlg = ui.dialog()
        with detail_dlg:
            with ui.card().classes("w-800 max-w-full"):
                dlg_title = ui.markdown("")
                dlg_content = ui.markdown("")

        def show_detail(doc_uid: str):
            """加载并显示文档详情。"""
            res = kb_query.get_document(doc_uid, STATE["active_collection"])
            if not res.get("ok"):
                ui.notify(f"加载失败: {res.get('error', '')}", type="negative")
                return
            chunks = res.get("chunks", [])
            dlg_title.set_content(f"## 📄 {chunks[0].get('title', '') if chunks else doc_uid}")
            preview = "\n\n---\n\n".join(
                f"**分块 {c['chunk_index']}**\n```\n{c['text'][:500]}\n```" for c in chunks[:5]
            )
            if len(chunks) > 5:
                preview += f"\n\n...（共 {len(chunks)} 个分块）"
            dlg_content.set_content(preview)
            detail_dlg.open()

        def load_docs(page: int):
            """加载指定页。"""
            page = max(1, page)
            nr = page_state.get("needs_review", None)
            res = kb_query.list_documents(
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
                    uid = d.get("doc_uid", "")
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
                                ui.button("👁️", on_click=lambda u=uid: show_detail(u), color="blue").props("flat dense")
                                def _del(u=uid):
                                    dlg_doc_uid["val"] = u
                                    confirm_dlg.open()
                                ui.button("🗑️", on_click=_del, color="red").props("flat dense")

            # 分页
            pagination_row.clear()
            with pagination_row:
                tp = page_state["total_pages"]
                p = page_state["page"]
                ui.button("◀ 上一页", on_click=lambda: load_docs(p - 1)).props("flat dense").set_enabled(p > 1)
                ui.label(f"第 {p} / {tp} 页（共 {page_state['total']} 篇）").classes("self-center")
                ui.button("下一页 ▶", on_click=lambda: load_docs(p + 1)).props("flat dense").set_enabled(p < tp)

        # 初次加载
        load_docs(1)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Citrinitas · 熔知",
        host="127.0.0.1",
        port=8080,
        reload=False,
        show=False,
        storage_secret="citrinitas-mindforge-secret",
        reconnect_timeout=120,  # 给 LLM/嵌入模型 充足加载时间
    )
