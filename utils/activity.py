"""
Citrinitas · 熔知 — 活动日志（审计 trail）

极简 JSON Lines 日志：每行一条事件，便于事后追溯"谁动了什么开关/配置"。
线程安全（锁保护），文件追加写，不进内存，不影响主流程性能。
落点：local_data/activity_log.jsonl

用法：
    from utils.activity import log_activity
    log_activity("debug_force_review_on", detail="系统配置页切换调试开关")
"""

import os
import json
import threading
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_DIR, "local_data")
LOG_PATH = os.path.join(LOG_DIR, "activity_log.jsonl")

# 文件追加写是共享资源，多页面/多摄入并发时要用锁护住，避免日志行交错损坏。
_lock = threading.Lock()


def log_activity(action: str, detail: str = "", level: str = "info") -> None:
    """记录一条活动事件（追加到 activity_log.jsonl，线程安全）。

    action: 事件类型，如 "debug_force_review_on" / "debug_force_review_off" /
            "config_save" 等（建议用下划线命名的稳定字符串，方便检索）
    detail: 人类可读的补充信息
    level:  "info" / "warn" / "error"
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "detail": detail,
            "level": level,
        }
        with _lock:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # 活动日志本身是"附加"功能，绝不能因为它的失败阻断主流程（如保存配置）
        print(f"[activity] WARNING: 活动日志记录失败: {e}")
