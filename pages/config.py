"""
Citrinitas · 熔知 — 引擎配置页面

此模块包含引擎配置页面（/config）的函数。
从 main.py 拆分出来以降低主文件复杂度。
"""

import os
from nicegui import ui

import kb_query
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
                ui.label("NiceGUI: 3.13.0")
                ui.label(f"Qdrant: {kb_query.QDRANT_URL}")
