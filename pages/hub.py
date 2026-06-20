"""
Citrinitas · 熔知 — 知识中枢页面

此模块包含知识中枢页面（/hub）的函数。
从 main.py 拆分出来以降低主文件复杂度。
"""

from nicegui import ui

import kb_query
from utils.state import STATE
from utils.ui_shared import build_left_drawer, refresh_system_state, set_active_collection


@ui.page("/hub")
def page_hub():
    """知识中枢页面（/hub）—— 知识库集合的指挥中心"""

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
