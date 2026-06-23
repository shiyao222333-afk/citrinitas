"""
Citrinitas — 操作活动日志（JSON Lines 格式）

写入 local_data/activity_log.jsonl，每行一条 JSON 记录。
D2 仪表盘从该文件读取最近操作渲染时间线。

v0.9.0: 新建模块
"""

import json
import os
import threading
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(PROJECT_DIR, "local_data", "activity_log.jsonl")
_LOCK = threading.Lock()


def log_activity(
    action: str,
    doc_id: str | None = None,
    detail: str = "",
    collection: str = "",
    source: str = "",
):
    """追加一条操作记录到活动日志。

    参数:
        action: 操作类型（ingest_success / ingest_dead_letter / ingest_skipped /
                delete / review_approve / review_drop / dlq_drop / dlq_reingest）
        doc_id: 文档/chunk ID（可选）
        detail: 人类可读的补充说明（文件名、原因等）
        collection: 知识库名称
        source: 来源描述（文件上传 / 批量导入 / 手动输入 / 守望文件夹等）
    """
    # 确保目录存在
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "doc_id": doc_id or "",
        "detail": detail,
        "collection": collection,
        "source": source,
    }

    with _LOCK:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 静默失败，不影响主流程


def read_recent_activities(limit: int = 20) -> list:
    """读取最近 N 条活动记录（最新在前）。"""
    if not os.path.exists(LOG_PATH):
        return []

    lines = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception:
        return []

    # 取最近 limit 条，倒序（最新在前）
    recent = lines[-limit:]
    activities = []
    for line in reversed(recent):
        try:
            activities.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return activities
