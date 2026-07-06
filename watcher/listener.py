"""
Citrinitas Watch Folder — 文件监听 + 后台处理循环。

依赖 state.py（全局状态）、processor.py（文件处理）、failures.py（故障处理）。
"""

import os
import sys
import time
import json
import threading
from queue import Queue, Empty, Full

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.settings import (
    WATCH_V2_QUEUE_MAX_SIZE,
    WATCH_V2_QUEUE_PUT_TIMEOUT,
    WATCH_V2_DLQ_TTL_DAYS,
    WATCH_V2_CLEANUP_INTERVAL,
    WATCH_V2_INFRA_RETRY_INTERVAL,
    WATCH_V2_NOTIFY_ON_FATAL,
)
from utils.activity_log import log_activity

from watcher.state import (
    _observer, _worker_thread, _queue, _stop_event,
    _heartbeat_time, _heartbeat_lock,
    _state_lock, _stats_lock,
    _pending_removals, _watch_stats,
    _queued_files, _in_flight,
    _append_state, _load_state, _get_file_state,
    _check_lock_file, _write_lock_file, _remove_lock_file,
)
from watcher.utils import (
    INBOX_DIR, STATE_FILE,
    _is_temp_file, _ensure_dir,
    _check_infra, _check_disk_space, _is_write_complete,
)
from watcher.failures import _handle_failure, _classify_failure
from watcher.processor import _process_file_with_timeout


# ═══════════════════════════════════════════
# Watchdog 事件处理器
# ═══════════════════════════════════════════

class WatchHandler(FileSystemEventHandler):
    """watchdog 事件处理器 — 文件创建时入队。"""

    def __init__(self, queue: Queue, stop_event: threading.Event):
        super().__init__()
        self.queue = queue
        self.stop_event = stop_event

    def on_created(self, event):
        if event.is_directory:
            return
        if self.stop_event.is_set():
            return

        filepath = event.src_path
        filename = os.path.basename(filepath)

        if _is_temp_file(filename) or filename.startswith("."):
            with _stats_lock: _watch_stats["skipped"] += 1
            return

        try:
            _queued_files.add(filepath)
            self.queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
        except Full:
            with _stats_lock: _watch_stats["skipped"] += 1
            log_activity(
                action="watch_queue_full",
                detail=f"队列已满，丢弃文件: {filename}",
                source=filename,
            )

    def on_moved(self, event):
        """处理文件剪切粘贴到 inbox/ 的事件。"""
        if event.is_directory:
            return
        if self.stop_event.is_set():
            return
        filepath = event.dest_path
        filename = os.path.basename(filepath)
        if _is_temp_file(filename) or filename.startswith("."):
            with _stats_lock: _watch_stats["skipped"] += 1
            return
        try:
            _queued_files.add(filepath)
            self.queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
        except Full:
            with _stats_lock: _watch_stats["skipped"] += 1
            log_activity(
                action="watch_queue_full",
                detail=f"队列已满，丢弃文件: {filename}",
                source=filename,
            )


# ═══════════════════════════════════════════
# 后台处理循环
# ═══════════════════════════════════════════

def _processing_loop(queue: Queue, stop_event: threading.Event):
    """后台处理循环：从队列取文件，逐个处理。"""
    global _heartbeat_time

    log_activity(action="watch_started", detail="守望文件夹 处理循环启动")

    _scan_existing_files(queue)
    _recover_retry_files(queue, stop_event)

    with _stats_lock: _watch_stats["running"] = True

    loop_count = 0
    while not stop_event.is_set():
        with _heartbeat_lock:
            _heartbeat_time = time.time()

        try:
            filepath = queue.get(timeout=2.0)
            _queued_files.discard(filepath)
            _in_flight.add(filepath)
        except Empty:
            _cleanup_expired_states()
            loop_count += 1
            if loop_count % WATCH_V2_INFRA_RETRY_INTERVAL == 0:
                infra = _check_infra()
                with _stats_lock:
                    _watch_stats["infra_ok"] = (infra["qdrant"] and infra["ollama"])
            if loop_count % 30 == 0:
                _rescue_orphaned_files(queue)
            continue

        loop_count += 1
        try:
            filename = os.path.basename(filepath)

            if not os.path.isfile(filepath):
                continue

            if _is_temp_file(filename) or filename.startswith("."):
                with _stats_lock: _watch_stats["skipped"] += 1
                continue

            existing_state = _get_file_state(filename)
            if existing_state:
                existing_status = existing_state.get("state", "")
                if existing_status in ("failed", "needs_review"):
                    continue

            infra = _check_infra()
            if not (infra["qdrant"] and infra["ollama"]):
                with _stats_lock: _watch_stats["infra_ok"] = False
                log_activity(
                    action="watch_infra_down",
                    detail=f"基础设施不可用 (qdrant={infra['qdrant']}, ollama={infra['ollama']})",
                )
                _append_state({
                    "file": filename,
                    "state": "retry",
                    "step": "infra_check",
                    "error": f"基础设施不可用 (qdrant={infra['qdrant']}, ollama={infra['ollama']})",
                })
                continue

            with _stats_lock: _watch_stats["infra_ok"] = True

            disk = _check_disk_space(min_free_mb=100)
            if not disk["ok"]:
                log_activity(
                    action="watch_disk_full",
                    detail=f"磁盘空间不足: {disk['free_mb']:.0f}MB 可用",
                )
                result = _handle_failure(filepath, filename, "any", "disk_full")
                if result == "retry_later":
                    continue
                return

            if not _is_write_complete(filepath):
                time.sleep(1)
                if os.path.isfile(filepath):
                    try:
                        _queued_files.add(filepath)
                        queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
                    except Full:
                        pass
                continue

            _process_file_with_timeout(filepath)
        finally:
            _in_flight.discard(filepath)

    _fix_incomplete_states()

    with _stats_lock: _watch_stats["running"] = False
    log_activity(action="watch_stopped", detail="守望文件夹 处理循环已停止")


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _scan_existing_files(queue: Queue):
    """扫描 inbox 中已有的文件并加入队列。"""
    if not os.path.isdir(INBOX_DIR):
        return

    files = []
    for filename in os.listdir(INBOX_DIR):
        filepath = os.path.join(INBOX_DIR, filename)
        if os.path.isfile(filepath) and not _is_temp_file(filename) and not filename.startswith("."):
            files.append(filepath)

    for fp in sorted(files):
        try:
            _queued_files.add(fp)
            queue.put(fp, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
        except Full:
            with _stats_lock: _watch_stats["skipped"] += 1


def _rescue_orphaned_files(queue: Queue):
    """定期扫描 inbox，救回因队列溢出被丢弃的文件。"""
    if not os.path.isdir(INBOX_DIR):
        return

    with _stats_lock:
        infra_ok = _watch_stats.get("infra_ok", True)
    if not infra_ok:
        return

    state = _load_state()
    rescued = 0
    for filename in os.listdir(INBOX_DIR):
        filepath = os.path.join(INBOX_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        if _is_temp_file(filename) or filename.startswith("."):
            continue
        entry = state.get(filename)
        if entry and entry.get("state") in ("failed", "needs_review", "done"):
            continue
        if filepath in _queued_files or filepath in _in_flight:
            continue
        try:
            _queued_files.add(filepath)
            queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
            rescued += 1
        except Full:
            break
    if rescued > 0:
        log_activity(
            action="watch_rescue",
            detail=f"救回 {rescued} 个遗漏文件",
        )


def _fix_incomplete_states():
    """优雅退出时，把所有非终态改成 retry，下次启动时自动恢复。"""
    FINAL_STATES = {"done", "failed", "needs_review"}
    state = _load_state()
    fixed = 0
    for fname, entry in state.items():
        if entry.get("state") in FINAL_STATES:
            continue
        _append_state({
            "file": fname,
            "state": "retry",
            "step": "graceful_exit",
            "error": "优雅退出时状态未完，标记为重试",
        })
        fixed += 1
    if fixed > 0:
        log_activity(
            action="watch_fixed_incomplete",
            detail=f"优雅退出时修复 {fixed} 个未完成状态",
        )


def _recover_retry_files(queue: Queue, stop_event: threading.Event):
    """恢复 retry 状态的文件——基础设施恢复后自动重试。"""
    infra = _check_infra()
    if not (infra["qdrant"] and infra["ollama"]):
        log_activity(
            action="watch_retry_recovery_skipped",
            detail=f"基础设施不可用，跳过 retry 文件恢复 (qdrant={infra['qdrant']}, ollama={infra['ollama']})",
        )
        return

    state = _load_state()
    retry_files = [fname for fname, entry in state.items() if entry.get("state") == "retry"]
    if not retry_files:
        return

    log_activity(
        action="watch_retry_recovery",
        detail=f"发现 {len(retry_files)} 个待重试文件",
    )

    for fname in retry_files:
        if stop_event.is_set():
            break
        filepath = os.path.join(INBOX_DIR, fname)
        if os.path.isfile(filepath):
            try:
                _queued_files.add(filepath)
                queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
            except Full:
                pass


def _cleanup_expired_states():
    """清理过期的状态记录 + 去重（仅保留每文件最后一条）+ 应用延迟删除 + 文件过大时压缩。"""
    if not os.path.isfile(STATE_FILE):
        return

    MAX_FILE_SIZE = 10 * 1024 * 1024
    now = time.time()

    if not hasattr(_cleanup_expired_states, "_last_run"):
        _cleanup_expired_states._last_run = 0.0

    elapsed = now - _cleanup_expired_states._last_run
    try:
        file_size = os.path.getsize(STATE_FILE)
    except OSError:
        return
    force = file_size > MAX_FILE_SIZE

    with _state_lock:
        removals_snapshot = _pending_removals.copy()
    has_pending = len(removals_snapshot) > 0

    if not force and not has_pending and elapsed < WATCH_V2_CLEANUP_INTERVAL:
        return

    _cleanup_expired_states._last_run = now

    ttl_seconds = WATCH_V2_DLQ_TTL_DAYS * 86400 if WATCH_V2_DLQ_TTL_DAYS > 0 else 0
    expired_removed = 0
    dedup_saved = 0
    pending_applied = len(removals_snapshot)

    try:
        last_line_nums = {}
        from datetime import datetime, timezone as _tz
        line_num = -1
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                try:
                    entry = json.loads(line_stripped)
                except json.JSONDecodeError:
                    continue

                fname = entry.get("file", "")
                if not fname:
                    continue

                if fname in removals_snapshot:
                    continue

                ts_str = entry.get("ts", "")
                expired = False
                if ts_str and ttl_seconds > 0:
                    try:
                        ts = datetime.fromisoformat(ts_str).timestamp()
                        if now - ts > ttl_seconds:
                            expired = True
                    except ValueError:
                        pass
                if expired:
                    expired_removed += 1
                    continue

                if fname in last_line_nums:
                    dedup_saved += 1
                last_line_nums[fname] = line_num

        keep_lines = set(last_line_nums.values())
        temp_file = STATE_FILE + ".tmp"
        line_num = -1
        with open(temp_file, "w", encoding="utf-8") as out:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line_num += 1
                    if line_num in keep_lines:
                        if line.endswith("\n"):
                            out.write(line)
                        else:
                            out.write(line + "\n")

        with _state_lock:
            os.replace(temp_file, STATE_FILE)
            _pending_removals.clear()

        reason = "force" if force else "scheduled"
        total_cleaned = expired_removed + dedup_saved + pending_applied
        if total_cleaned > 0:
            parts = []
            if expired_removed > 0:
                parts.append(f"过期 {expired_removed}")
            if dedup_saved > 0:
                parts.append(f"去重 {dedup_saved}")
            if pending_applied > 0:
                parts.append(f"移除 {pending_applied}")
            log_activity(
                action="watch_state_cleanup",
                detail=f"清理 {' + '.join(parts)} 条 ({reason}, {file_size//1024} KB)",
            )
    except OSError as e:
        log_activity(
            action="watch_state_cleanup_failed",
            detail=f"清理状态文件失败: {e}",
        )
        if WATCH_V2_NOTIFY_ON_FATAL:
            print(f"[watcher] 清理状态文件失败: {e}", file=sys.stderr)
