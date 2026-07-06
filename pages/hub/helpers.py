"""
共享辅助函数 — 被所有 hub 子模块使用。
避免循环导入。
"""

import os
import json
import glob as glob_mod
from datetime import datetime, timezone

import kb_query

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DLQ_DIR = os.path.join(PROJECT_DIR, "local_data", "dead_letter")
INBOX_DIR = os.path.join(PROJECT_DIR, "data", "inbox")


def _load_dlq_files() -> list:
    """加载死信队列 JSON 文件列表。"""
    items = []
    if not os.path.isdir(DLQ_DIR):
        return items
    for fp in sorted(glob_mod.glob(os.path.join(DLQ_DIR, "*.json")), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                item = json.load(f)
                item["_file"] = fp
                items.append(item)
        except (json.JSONDecodeError, OSError):
            pass
    return items


def _delete_dlq_file(fp: str):
    """删除死信队列文件。"""
    try:
        os.remove(fp)
    except OSError:
        pass


def _ensure_inbox_dir():
    """确保收件箱目录存在。"""
    os.makedirs(INBOX_DIR, exist_ok=True)


def _load_inbox_files() -> list:
    """加载守望收件箱文件列表，并合并 file_state.jsonl 中的真实处理状态。"""
    items = []
    if not os.path.isdir(INBOX_DIR):
        return items
    # 合并 watcher 维护的真实状态（处理中 / 失败 / 需审核 / 已完成）
    try:
        from watcher.state import get_all_states
        states = get_all_states()
    except Exception:
        states = {}
    for filename in sorted(os.listdir(INBOX_DIR), reverse=True):
        fp = os.path.join(INBOX_DIR, filename)
        if not os.path.isfile(fp):
            continue
        if filename.startswith("~") or filename.startswith("."):
            continue
        stat = os.stat(fp)
        entry = states.get(filename, {})
        items.append({
            "_filename": filename,
            "_file": fp,
            "file": filename,
            "path": fp,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "state": entry.get("state", "pending"),
            "error": entry.get("error", ""),
            "step": entry.get("step", ""),
            "failure_type": entry.get("failure_type", ""),
            "retry_count": entry.get("retry_count", 0),
            "ts": entry.get("ts", ""),
        })
    return items


def _retry_inbox_file(filename: str) -> bool:
    """将收件箱文件重新提交给 watcher 处理。"""
    try:
        fp = os.path.join(INBOX_DIR, filename)
        if not os.path.isfile(fp):
            return False
        from watcher import retry_file
        return retry_file(filename)
    except Exception:
        return False


def _delete_inbox_file(filename: str) -> bool:
    """删除收件箱文件。"""
    try:
        fp = os.path.join(INBOX_DIR, filename)
        os.remove(fp)
        return True
    except OSError:
        return False


def _get_inbox_stats() -> dict:
    """获取收件箱统计信息。"""
    files = _load_inbox_files()
    return {
        "total": len(files),
        "total_size": sum(f["size"] for f in files),
    }
