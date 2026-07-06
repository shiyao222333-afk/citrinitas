"""
Citrinitas · 熔知 — 引擎配置页面

此模块包含引擎配置页面（/config）的函数。
从 main.py 拆分出来以降低主文件复杂度。
"""

import os
from nicegui import ui

import kb_query
from qconst import EMBED_MODEL, QDRANT_URL
from utils.state import STATE
from utils.ui_shared import build_left_drawer, EMBED_PRESETS

# 嵌入模型预设（从 main.py 复制）

# .env 文件路径
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(PROJECT_DIR, ".env")


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


@ui.page("/config")
def page_config():
    """引擎配置页面（/config）—— 配置底层引擎参数"""

    build_left_drawer(active_page="config")

    with ui.column().classes("w-full p-6"):
        ui.markdown("# ⚙️ 引擎配置")
        ui.markdown("*配置底层引擎参数。保存后写入 `.env` 文件。*")

        tabs = ui.tabs().props("align=left")
        with tabs:
            llm_tab = ui.tab("🤖 LLM")
            embed_tab = ui.tab("🧬 嵌入模型")
            rerank_tab = ui.tab("🔀 重排序")
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
                    value=os.environ.get("KB_EMBED_MODEL", EMBED_MODEL),
                ).classes("w-full")

                def save_embed():
                    val = (current_embed.value or "").strip()
                    if val:
                        _save_env({"KB_EMBED_MODEL": val})
                        os.environ["KB_EMBED_MODEL"] = val
                        # 即时生效：ingest/embed 在调用时读取 os.environ["KB_EMBED_MODEL"]
                        # （见 services/ingest_service.py 与 text_pipeline/embed.py），无需重启即可切换。
                        ui.notify("✅ 嵌入模型已保存（即时生效）", type="positive")

                ui.button("💾 保存", on_click=save_embed).props("color=blue")

            # ── 重排序 ──
            with ui.tab_panel(rerank_tab):
                ui.markdown("### 搜索结果重排序")
                ui.markdown("*搜索后用嵌入模型对结果重新打分，提高精度。*")

                rerank_enabled = ui.switch(
                    "启用重排序",
                    value=os.environ.get("KB_RERANK_ENABLED", "true").lower() == "true",
                )

                rerank_model = ui.input(
                    label="重排序模型",
                    value=os.environ.get("KB_RERANK_MODEL", "qwen3-embedding:4b"),
                ).classes("w-full")

                rerank_top_n = ui.number(
                    label="取前 N 条结果重排序",
                    value=int(os.environ.get("KB_RERANK_TOP_N", "20")),
                    min=5,
                    max=50,
                    step=5,
                ).classes("w-32")

                ui.markdown("*重排序取搜索结果的前 N 条，用嵌入模型计算查询与文档的相似度，重新排序后返回。*")
                ui.markdown("*关闭后使用 Qdrant 原始排序（RRF 融合分数）。*")

                def save_rerank():
                    _save_env({
                        "KB_RERANK_ENABLED": "true" if rerank_enabled.value else "false",
                        "KB_RERANK_MODEL": rerank_model.value or "qwen3-embedding:4b",
                        "KB_RERANK_TOP_N": str(int(rerank_top_n.value or 20)),
                    })
                    os.environ["KB_RERANK_ENABLED"] = "true" if rerank_enabled.value else "false"
                    os.environ["KB_RERANK_MODEL"] = rerank_model.value or "qwen3-embedding:4b"
                    os.environ["KB_RERANK_TOP_N"] = str(int(rerank_top_n.value or 20))
                    ui.notify("✅ 重排序配置已保存", type="positive")

                ui.button("💾 保存重排序配置", on_click=save_rerank).props("color=blue")

            # ── 系统配置 ──
            with ui.tab_panel(sys_tab):
                from config.settings import CONFIDENCE_LOW, CONFIDENCE_HIGH

                ui.markdown("### 置信度路由阈值")
                ui.markdown("*AI 分析后按置信度分三档：≥高阈值直接入库 / 中间待审核 / <低阈值进死信队列。*")
                ui.markdown("**死信阈值**（低于此值进死信队列）")
                conf_low = ui.slider(
                    min=0.10,
                    max=0.60,
                    step=0.05,
                    value=CONFIDENCE_LOW,
                ).classes("w-64").props("label-always")

                ui.markdown("**入库阈值**（高于此值直接入库）")
                conf_high = ui.slider(
                    min=0.50,
                    max=0.95,
                    step=0.05,
                    value=CONFIDENCE_HIGH,
                ).classes("w-64").props("label-always")

                ui.separator()
                ui.markdown("### 系统设置")
                kb_root = ui.input(
                    label="知识库根目录",
                    value=os.environ.get("KB_ROOT_PATH", os.path.join(PROJECT_DIR, "local_data")),
                ).classes("w-full")

                def save_sys():
                    _save_env({
                        "KB_ROOT_PATH": kb_root.value or "",
                        "KB_CONFIDENCE_LOW": str(conf_low.value),
                        "KB_CONFIDENCE_HIGH": str(conf_high.value),
                    })
                    os.environ["KB_CONFIDENCE_LOW"] = str(conf_low.value)
                    os.environ["KB_CONFIDENCE_HIGH"] = str(conf_high.value)
                    ui.notify("✅ 系统配置已保存", type="positive")

                ui.button("💾 保存", on_click=save_sys).props("color=blue")

                ui.separator()
                ui.markdown("### 版本信息")
                ui.label(f"Citrinitas: v{kb_query.__version__}")
                ui.label("NiceGUI: 3.13.0")
                ui.label(f"Qdrant: {QDRANT_URL}")
