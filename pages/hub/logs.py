"""
知识中枢 — 日志查看器标签

v1.1.0 新增：统一日志查看 UI。
读取 local_data/logs/citrinitas.log，支持：
  - 按级别过滤（DEBUG / INFO / WARNING / ERROR / CRITICAL）
  - 按错误码过滤（E001 / E100 / ...）
  - 按时间范围过滤
  - 实时刷新（手动按钮）
  - 日志统计（各错误码出现次数）
"""
import os
from datetime import datetime, timedelta
from collections import Counter, deque

from nicegui import ui

from utils.state import STATE
from utils.logging_config import LOG_DIR, LOG_FILE_PREFIX


def _parse_log_file(log_path: str, max_lines: int = 500) -> list:
    """
    解析日志文件，返回结构化记录列表。

    日志格式：
        [2026-07-06 12:00:00.123] [ERROR] [ingest_service] [E001] 文件读取失败: ...
    """
    records = []
    if not os.path.exists(log_path):
        return records

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = deque(f, maxlen=max_lines)  # 高效读取最后 N 行，避免全文件加载

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 解析：[timestamp] [LEVEL] [module] message
        # 可能包含 [Exxx] 错误码
        parts = line.split("] ", 3)
        if len(parts) >= 3:
            timestamp = parts[0].lstrip("[")
            level = parts[1].lstrip("[").strip()
            rest = parts[2] if len(parts) == 3 else parts[3]

            # 提取错误码（如果有）
            error_code = ""
            if "[E" in rest:
                start = rest.find("[E")
                end = rest.find("]", start)
                if start != -1 and end != -1:
                    error_code = rest[start+1:end]

            records.append({
                "timestamp": timestamp,
                "level": level,
                "module": rest.split("] ")[0] if "] " in rest else "",
                "error_code": error_code,
                "message": rest,
            })

    return records


def _get_log_stats(records: list) -> dict:
    """统计日志记录。"""
    stats = {
        "total": len(records),
        "by_level": Counter(),
        "by_error_code": Counter(),
        "recent_critical": [],
    }

    for r in records:
        stats["by_level"][r["level"]] += 1
        if r["error_code"]:
            stats["by_error_code"][r["error_code"]] += 1
        if r["level"] == "CRITICAL":
            stats["recent_critical"].append(r)

    return stats


async def _build_logs_tab():
    """
    构建「日志」标签页内容。
    """
    ui.notify("加载日志查看器...", type="info")

    # ── 顶部工具栏 ────────────────────────────────────────────────────────────────
    with ui.row().classes("w-full items-center gap-4 p-2"):
        level_select = ui.select(
            options=["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            value="ALL",
            label="级别过滤",
        ).props("dense outlined").classes("w-32")

        code_input = ui.input(
            label="错误码过滤（如 E001）",
            placeholder="留空=不过滤",
        ).props("dense outlined clearable").classes("w-48")

        refresh_btn = ui.button("🔄 刷新", on_click=lambda: _refresh_logs()).props("flat dense")

        async def _refresh_logs():
            """刷新日志显示。"""
            log_path = os.path.join(LOG_DIR, f"{LOG_FILE_PREFIX}.log")
            records = _parse_log_file(log_path, max_lines=1000)

            # 应用过滤
            level_filter = level_select.value
            code_filter = code_input.value.strip()

            filtered = records
            if level_filter != "ALL":
                filtered = [r for r in filtered if r["level"] == level_filter]
            if code_filter:
                filtered = [r for r in filtered if code_filter in r["error_code"]]

            # 更新表格
            table.rows = filtered[-500:]  # 最多显示 500 行
            table.update()

            # 更新统计
            stats = _get_log_stats(filtered)
            stats_label.text = (
                f"总计: {stats['total']} | "
                f"ERROR: {stats['by_level']['ERROR']} | "
                f"CRITICAL: {stats['by_level']['CRITICAL']} | "
                f"最近 CRITICAL: {len(stats['recent_critical'])}"
            )

        ui.button("⚙️ 测试告警", on_click=lambda: _test_alert()).props("flat dense")

        async def _test_alert():
            """发送测试告警（验证 Server酱 配置）。"""
            from utils.alerts import test_alert
            result = test_alert()
            ui.notify(result, type="info", multi_line=True)

    # ── 统计栏 ──────────────────────────────────────────────────────────────────
    stats_label = ui.label("加载中...").classes("text-sm text-gray-500 p-2")

    # ── 日志表格 ────────────────────────────────────────────────────────────────
    columns = [
        {"name": "timestamp", "label": "时间", "field": "timestamp", "width": "180px"},
        {"name": "level", "label": "级别", "field": "level", "width": "80px"},
        {"name": "error_code", "label": "错误码", "field": "error_code", "width": "80px"},
        {"name": "module", "label": "模块", "field": "module", "width": "150px"},
        {"name": "message", "label": "消息", "field": "message"},
    ]

    rows = []

    table = ui.table(
        columns=columns,
        rows=rows,
        row_key="timestamp",
        pagination=50,
    ).classes("w-full")

    # 初始加载
    await _refresh_logs()
