"""
Citrinitas Watch Folder v2 — 统一收件箱 + 状态追踪

设计原则:
  - 统一收件箱 data/inbox/：所有文件放在一个目录，不移动
  - file_state.jsonl：记录所有状态（failed/needs_review/retry/done），done 防止重启后重复处理
  - 内容驱动保留策略：逐页分析内容，WLNK 决策是否保留原文件
  - 15 种故障 × 5 种策略：每个环节失败都有明确处理路径

状态机:
  pending → processing → done / failed / needs_review / retry

用法:
    from watcher_v2 import start_watcher_v2, stop_watcher_v2
    watcher_thread = start_watcher_v2()
    # ... app runs ...
    stop_watcher_v2()
"""

import os
import sys
import time
import json
import shutil
import fnmatch
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.settings import (
    PROJECT_DIR,
    WATCH_V2_INBOX_DIR,
    WATCH_V2_STATE_FILE,
    WATCH_V2_WRITE_COMPLETE_CHECKS,
    WATCH_V2_WRITE_CHECK_INTERVAL,
    WATCH_V2_MAX_FILE_SIZE_MB,
    WATCH_V2_PROCESSING_TIMEOUT,
    WATCH_V2_QUEUE_MAX_SIZE,
    WATCH_V2_MAX_AUTO_RETRIES,
    WATCH_V2_AUTO_RETRY_DELAY,
    WATCH_V2_DLQ_TTL_DAYS,
    WATCH_V2_NOTIFY_ON_FATAL,
    WATCH_V2_TEXT_DENSITY_THRESHOLD,
    WATCH_V2_OCR_CONF_THRESHOLD,
    WATCH_V2_TEMP_PATTERNS,
    WATCH_V2_QUEUE_PUT_TIMEOUT,
    WATCH_V2_CLEANUP_INTERVAL,
)
from text_pipeline import (
    analyze_page_content,
    ocr_image as _ocr_image,
    extract_text as _extract_text,
)
from classify_pipeline import classify_document
from qconst import QDRANT_URL, OLLAMA_URL, DEFAULT_COLLECTION, CONFIDENCE_LOW, CONFIDENCE_HIGH
from utils.activity_log import log_activity

# ═══════════════════════════════════════════
# 路径定义
# ═══════════════════════════════════════════

INBOX_DIR = os.path.join(PROJECT_DIR, WATCH_V2_INBOX_DIR)
STATE_FILE = os.path.join(PROJECT_DIR, WATCH_V2_STATE_FILE)
LOCK_FILE = os.path.join(os.path.dirname(STATE_FILE), ".watch_v2.lock")

# ═══════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════

_observer: Observer | None = None
_worker_thread: threading.Thread | None = None
_queue: Queue | None = None
_stop_event: threading.Event | None = None
_heartbeat_time: float = 0.0
_heartbeat_lock = threading.Lock()
_state_lock = threading.Lock()
_stats_lock = threading.Lock()
_pending_removals: set = set()  # 延迟删除集合（批量重写优化）
_watch_stats: dict = {
    "processed": 0,
    "failed": 0,
    "skipped": 0,
    "deleted": 0,
    "pending": 0,
    "needs_review": 0,
    "running": False,
    "infra_ok": True,
}


# ═══════════════════════════════════════════
# 状态文件操作（file_state.jsonl）
# ═══════════════════════════════════════════

def _load_state() -> dict:
    """加载 file_state.jsonl，返回 {filename: latest_entry} 映射。自动过滤 _pending_removals。"""
    state = {}
    if not os.path.isfile(STATE_FILE):
        return state
    # 读取状态文件（锁外 — append-only 读取安全，遗漏的新条目下次调用补上）
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    fname = entry.get("file", "")
                    if fname:
                        state[fname] = entry
                except json.JSONDecodeError:
                    pass
    except OSError as e:
        log_activity(
            action="watch_v2_state_load_failed",
            detail=f"读取状态文件失败: {e}",
        )
        return state
    # 快照待删除集合（锁内 — 避免与 _cleanup_expired_states 清除竞争）
    with _state_lock:
        removals_snapshot = _pending_removals.copy()
    # 过滤掉待删除的文件（锁外）
    for fname in removals_snapshot:
        state.pop(fname, None)
    return state


def _append_state(entry: dict):
    """追加一行到 file_state.jsonl。不修改入参 dict。"""
    try:
        with _state_lock:
            state_dir = os.path.dirname(STATE_FILE)
            os.makedirs(state_dir, exist_ok=True)
            entry_copy = dict(entry)
            entry_copy["ts"] = datetime.now(timezone.utc).isoformat()
            with open(STATE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry_copy, ensure_ascii=False) + "\n")
    except (OSError, ValueError) as e:
        log_activity(
            action="watch_v2_state_write_failed",
            detail=f"无法写入状态文件: {e}",
        )


def _remove_state(filename: str):
    """标记文件状态为待删除（延迟批量重写，避免每文件全量 I/O）。
    
    实际重写在 _cleanup_expired_states() 中批量执行。
    _load_state() 会自动过滤 _pending_removals 中的文件。
    """
    with _state_lock:
        _pending_removals.add(filename)


def _get_file_state(filename: str) -> dict | None:
    """获取某个文件的最新状态。"""
    state = _load_state()
    return state.get(filename)


def get_all_states() -> dict:
    """获取所有文件状态（供 UI 使用）。"""
    return _load_state()


def get_inbox_stats() -> dict:
    """获取收件箱统计信息。"""
    state = _load_state()
    stats = {
        "total": 0,
        "failed": 0,
        "needs_review": 0,
        "retry": 0,
        "pending": 0,
    }
    if os.path.isdir(INBOX_DIR):
        for filename in os.listdir(INBOX_DIR):
            filepath = os.path.join(INBOX_DIR, filename)
            if not os.path.isfile(filepath):
                continue
            if _is_temp_file(filename):
                continue
            stats["total"] += 1
            entry = state.get(filename)
            if entry:
                s = entry.get("state", "")
                if s == "failed":
                    stats["failed"] += 1
                elif s == "needs_review":
                    stats["needs_review"] += 1
                elif s == "retry":
                    stats["retry"] += 1
            else:
                stats["pending"] += 1
    return stats


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _is_temp_file(filename: str) -> bool:
    """检查是否为临时文件（Office ~$/下载中/系统文件）。"""
    for pattern in WATCH_V2_TEMP_PATTERNS:
        if fnmatch.fnmatch(filename.lower(), pattern.lower()):
            return True
    return False


def _is_write_complete(filepath: str) -> bool:
    """轮询文件大小，连续 N 次不变 → 认为写入完成。"""
    checks = WATCH_V2_WRITE_COMPLETE_CHECKS
    interval = WATCH_V2_WRITE_CHECK_INTERVAL
    last_size = -1
    stable_count = 0
    lock_retry_max = 3

    for _ in range(checks * 2):
        lock_retries = 0
        while lock_retries < lock_retry_max:
            try:
                current_size = os.path.getsize(filepath)
                break
            except PermissionError:
                lock_retries += 1
                if lock_retries >= lock_retry_max:
                    return False
                time.sleep(interval * 2)
            except OSError:
                return False

        if current_size == last_size:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            stable_count = 0
            last_size = current_size
        time.sleep(interval)

    return False


def _check_infra() -> dict:
    """检查基础设施健康状态。"""
    result = {"qdrant": False, "ollama": False}
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        result["qdrant"] = resp.status_code == 200
    except requests.RequestException:
        pass
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        result["ollama"] = resp.status_code == 200
    except requests.RequestException:
        pass
    return result


def _check_disk_space(min_free_mb: int = 100) -> dict:
    """检查 INBOX_DIR 所在磁盘的可用空间。
    
    Returns:
        {"ok": bool, "free_mb": float, "total_mb": float}
    """
    try:
        usage = shutil.disk_usage(INBOX_DIR)
        free_mb = usage.free / (1024 * 1024)
        total_mb = usage.total / (1024 * 1024)
        return {"ok": free_mb >= min_free_mb, "free_mb": free_mb, "total_mb": total_mb}
    except OSError:
        return {"ok": True, "free_mb": -1, "total_mb": -1}  # 无法检查时不阻塞


def _ensure_dir(path: str):
    """确保目录存在。"""
    os.makedirs(path, exist_ok=True)


# ── OCR 就绪状态 ──
_ocr_ready: bool | None = None
_ocr_lock = threading.Lock()


def _check_ocr_ready(force: bool = False) -> bool:
    """检查 OCR 引擎是否可用。加上线程锁和强制重检开关。"""
    global _ocr_ready
    with _ocr_lock:
        if _ocr_ready is not None and not force:
            return _ocr_ready
        try:
            from paddleocr import PaddleOCR
            _ocr_ready = True
        except ImportError:
            _ocr_ready = False
            log_activity(
                action="watch_v2_ocr_unavailable",
                detail="PaddleOCR 未安装，图片文件将标记为需要审核",
            )
    return _ocr_ready


# ═══════════════════════════════════════════
# 故障分类与处理策略（Task 5 集成）
# ═══════════════════════════════════════════

# 15 种故障类型
FAILURE_TYPES = {
    # 格式/大小检查
    "format_unsupported": {"step": "format_check", "strategy": "dlq_delete"},
    "file_too_large":     {"step": "size_check",    "strategy": "dlq_delete"},
    "temp_file":           {"step": "filter",        "strategy": "skip"},

    # 文件读取
    "read_error":          {"step": "extract",       "strategy": "auto_retry"},
    "corrupt_file":        {"step": "extract",       "strategy": "dlq_keep"},

    # 文本提取
    "extract_empty":       {"step": "extract",       "strategy": "needs_review"},
    "extract_error":       {"step": "extract",       "strategy": "auto_retry"},
    "ocr_failed":          {"step": "ocr",           "strategy": "needs_review"},
    "ocr_unavailable":     {"step": "ocr",           "strategy": "retry_later"},

    # AI 分类
    "classify_error":      {"step": "classify",      "strategy": "auto_retry"},
    "classify_low_conf":   {"step": "classify",      "strategy": "needs_review"},

    # 摄入
    "ingest_error":        {"step": "ingest",        "strategy": "auto_retry"},
    "ingest_duplicate":    {"step": "ingest",        "strategy": "skip"},

    # 基础设施
    "infra_down":          {"step": "infra",         "strategy": "retry_later"},
    "disk_full":           {"step": "any",           "strategy": "retry_later"},

    # 通用
    "timeout":             {"step": "any",           "strategy": "auto_retry"},
    "unknown":             {"step": "unknown",       "strategy": "dlq_keep"},
}

# 5 种处理策略说明（文档用途，非程序引用）:
#   auto_retry:   自动重试 N 次，全部失败后入 needs_review
#   retry_later:  等待基础设施恢复，不消耗重试次数
#   dlq_keep:     标记为 failed 保留原文件，等用户手动处理
#   dlq_delete:   标记为 failed 并删除原文件（无价值文件）
#   needs_review: 标记为 needs_review，等用户在 UI 审核
#   skip:         直接跳过，不记录状态


def _classify_failure(step: str, error_msg: str) -> str:
    """根据失败步骤和错误消息，映射到故障类型。"""
    # 格式检查
    if step == "format_check":
        return "format_unsupported"
    if step == "size_check":
        return "file_too_large"
    if step == "filter":
        return "temp_file"

    # 基础设施
    if "infra" in step:
        return "infra_down"
    if "disk" in error_msg.lower() or "space" in error_msg.lower():
        return "disk_full"

    # 文本提取
    if step == "extract":
        if "empty" in error_msg.lower() or "无文本" in error_msg:
            return "extract_empty"
        if "corrupt" in error_msg.lower() or "损坏" in error_msg:
            return "corrupt_file"
        return "extract_error"

    # OCR
    if step == "ocr":
        if "unavailable" in error_msg.lower() or "未安装" in error_msg:
            return "ocr_unavailable"
        return "ocr_failed"

    # 分类
    if step == "classify":
        if "conf" in error_msg.lower() or "置信度" in error_msg:
            return "classify_low_conf"
        return "classify_error"

    # 摄入
    if step == "ingest":
        if "duplicate" in error_msg.lower() or "重复" in error_msg:
            return "ingest_duplicate"
        return "ingest_error"

    # 超时
    if step == "timeout":
        return "timeout"

    # 文件读取
    if "permission" in error_msg.lower() or "权限" in error_msg:
        return "read_error"

    return "unknown"


def _get_strategy(failure_type: str) -> str:
    """获取故障类型对应的处理策略。"""
    return FAILURE_TYPES.get(failure_type, {}).get("strategy", "dlq_keep")


def _handle_failure(filepath: str, filename: str, step: str, error_msg: str, retry_count: int = 0) -> str:
    """
    统一故障处理入口。

    根据故障类型选择策略，执行后返回状态:
      - "retry": 应自动重试
      - "retry_later": 等待基础设施恢复
      - "needs_review": 需要人工审核
      - "failed": 已入失败记录
      - "skip": 已跳过
    """
    failure_type = _classify_failure(step, error_msg)
    strategy = _get_strategy(failure_type)

    # ── auto_retry ──
    if strategy == "auto_retry":
        if retry_count < WATCH_V2_MAX_AUTO_RETRIES:
            log_activity(
                action="watch_v2_retry",
                detail=f"[{step}] {error_msg} (重试 {retry_count + 1}/{WATCH_V2_MAX_AUTO_RETRIES})",
                source=filename,
            )
            return "retry"
        else:
            # 重试耗尽 → 降级为 needs_review
            _append_state({
                "file": filename,
                "state": "needs_review",
                "step": step,
                "error": f"{error_msg} (已重试{WATCH_V2_MAX_AUTO_RETRIES}次)",
                "retry_count": retry_count,
                "failure_type": failure_type,
            })
            with _stats_lock: _watch_stats["needs_review"] += 1
            log_activity(
                action="watch_v2_retry_exhausted",
                detail=f"[{step}] {error_msg} (重试耗尽)",
                source=filename,
            )
            return "needs_review"

    # ── retry_later（基础设施故障）──
    if strategy == "retry_later":
        _append_state({
            "file": filename,
            "state": "retry",
            "step": step,
            "error": error_msg,
            "retry_count": retry_count,
            "failure_type": failure_type,
        })
        log_activity(
            action="watch_v2_retry_later",
            detail=f"[{step}] {error_msg} (等待基础设施恢复)",
            source=filename,
        )
        return "retry_later"

    # ── needs_review ──
    if strategy == "needs_review":
        _append_state({
            "file": filename,
            "state": "needs_review",
            "step": step,
            "error": error_msg,
            "retry_count": retry_count,
            "failure_type": failure_type,
        })
        with _stats_lock: _watch_stats["needs_review"] += 1
        log_activity(
            action="watch_v2_needs_review",
            detail=f"[{step}] {error_msg}",
            source=filename,
        )
        return "needs_review"

    # ── dlq_keep ──
    if strategy == "dlq_keep":
        _append_state({
            "file": filename,
            "state": "failed",
            "step": step,
            "error": error_msg,
            "retry_count": retry_count,
            "failure_type": failure_type,
        })
        with _stats_lock: _watch_stats["failed"] += 1
        log_activity(
            action="watch_v2_failed",
            detail=f"[{step}] {error_msg}",
            source=filename,
        )
        return "failed"

    # ── dlq_delete ──
    if strategy == "dlq_delete":
        try:
            os.remove(filepath)
        except OSError:
            pass
        log_activity(
            action="watch_v2_deleted",
            detail=f"[{step}] {error_msg} (文件已删除)",
            source=filename,
        )
        with _stats_lock: _watch_stats["deleted"] += 1
        return "skip"

    # ── skip ──
    if strategy == "skip":
        with _stats_lock: _watch_stats["skipped"] += 1
        return "skip"

    return "failed"


# ═══════════════════════════════════════════
# WLNK 多页决策（Task 4）
# ═══════════════════════════════════════════

def decide_file_retention(page_analyses: list[dict]) -> dict:
    """
    文件级保留决策 — WLNK 原则：文件可删 = min(每页可删性)。

    任一页不可删 → 保留整个文件。

    返回:
        {
            "keep_file": bool,     # 是否保留原文件
            "reason": str,         # 决策理由
            "pages_deletable": int, # 可删除的页数
            "pages_total": int,     # 总页数
        }
    """
    if not page_analyses:
        return {"keep_file": True, "reason": "无页面数据，保守保留", "pages_deletable": 0, "pages_total": 0}

    total = len(page_analyses)
    deletable = sum(1 for p in page_analyses if p["deletable"])
    non_deletable = total - deletable

    # WLNK: 任一页不可删 → 保留整个文件
    if non_deletable > 0:
        reasons = []
        for i, p in enumerate(page_analyses):
            if not p["deletable"]:
                reasons.append(f"第{i+1}页: {p['summary']}")
        return {
            "keep_file": True,
            "reason": f"{non_deletable}/{total} 页含非文本元素 — " + "; ".join(reasons[:3]),
            "pages_deletable": deletable,
            "pages_total": total,
        }

    # 全部可删 → 删除原文件
    return {
        "keep_file": False,
        "reason": f"全部 {total} 页均为纯文本，内容已入库，可删除原文件",
        "pages_deletable": deletable,
        "pages_total": total,
    }


# ═══════════════════════════════════════════
# 逐页提取（PDF/多页文档支持）
# ═══════════════════════════════════════════

def _extract_pages(filepath: str, ext: str) -> list[dict]:
    """
    逐页提取文档内容。返回 [{"text": "...", "images": [...], "tables": [...], "ocr_conf": None}, ...]

    单页文件（txt/md/docx/图片）返回单元素列表。
    """
    pages = []

    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    page_images = []
                    page_tables = []

                    # 检测页面中的图片（pdfplumber page.images）
                    try:
                        img_list = getattr(page, 'images', []) or []
                        page_images = [f"pdf_img_{i}" for i in range(len(img_list))]
                    except Exception:
                        pass

                    # 检测表格
                    try:
                        tbl_list = page.extract_tables() or []
                        page_tables = [f"table_{i}" for i in range(len(tbl_list))]
                    except Exception:
                        pass

                    pages.append({
                        "text": page_text,
                        "images": page_images,
                        "tables": page_tables,
                        "ocr_conf": None,
                    })
        except ImportError:
            if not getattr(_extract_pages, "_pdfplumber_warned", False):
                _extract_pages._pdfplumber_warned = True
                log_activity(
                    action="watch_v2_pdfplumber_missing",
                    detail="pdfplumber 未安装，PDF 文件将无法提取文本。安装: pip install pdfplumber",
                )
            pages.append({"text": "", "images": [], "tables": [], "ocr_conf": None})
        except Exception:
            pages.append({"text": "", "images": [], "tables": [], "ocr_conf": None})

    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
        # 图片 OCR 后按结构分页（通常单页）
        try:
            ocr_result = _ocr_image(filepath)
            ocr_text = ocr_result.get("text", "") if ocr_result.get("ok") else ""
            ocr_conf = ocr_result.get("conf")
            has_images = bool(ocr_result.get("images", []))
            pages.append({
                "text": ocr_text,
                "images": ["ocr_image"] if has_images else [],
                "tables": [],
                "ocr_conf": ocr_conf,
            })
        except Exception:
            pages.append({"text": "", "images": [], "tables": [], "ocr_conf": None})

    else:
        # 文本类文件 → 单页
        try:
            result = _extract_text(filepath)
            text = result.get("text", "") if result.get("ok") else ""
        except Exception:
            text = ""
        pages.append({"text": text, "images": [], "tables": [], "ocr_conf": None})

    return pages


# ═══════════════════════════════════════════
# 文件处理主流程
# ═══════════════════════════════════════════

def _process_file(filepath: str, cancel_event: threading.Event = None):
    """处理单个文件：逐页提取 → WLNK 决策 → 分类 → 摄入 → 保留/删除。
    
    cancel_event: 可选的取消信号。超时线程会设置此事件，本函数在检查点轮询后退出。
    """
    import kb_query

    # 超时检查辅助函数
    def _cancelled():
        return cancel_event is not None and cancel_event.is_set()

    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    with _stats_lock: _watch_stats["infra_ok"] = True
    retry_count = 0
    max_retries = WATCH_V2_MAX_AUTO_RETRIES

    while retry_count <= max_retries:
        if _cancelled():
            log_activity(action="watch_v2_cancelled", source=filename,
                         detail="处理超时取消，由主线程接管")
            return
        # ── 格式检查 ──
        supported = {".txt", ".md", ".json", ".csv", ".log", ".pdf", ".docx",
                     ".pptx", ".epub", ".html", ".htm", ".xml", ".jpg", ".jpeg",
                     ".png", ".bmp", ".tiff", ".tif"}
        if ext not in supported:
            _handle_failure(filepath, filename, "format_check", f"不支持的文件格式: {ext}")
            return

        # ── 文件大小检查 ──
        if WATCH_V2_MAX_FILE_SIZE_MB > 0:
            try:
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                if size_mb > WATCH_V2_MAX_FILE_SIZE_MB:
                    _handle_failure(filepath, filename, "size_check",
                                    f"文件过大 ({size_mb:.1f}MB > {WATCH_V2_MAX_FILE_SIZE_MB}MB)")
                    return
            except OSError as e:
                result = _handle_failure(filepath, filename, "read_error", str(e), retry_count)
                if result == "retry":
                    retry_count += 1
                    time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                    continue
                return

        # ── 检查文件是否仍存在 ──
        if not os.path.isfile(filepath):
            _append_state({
                "file": filename, "state": "failed",
                "step": "read_error", "error": "文件在处理前已不存在",
                "failure_type": "read_error",
            })
            with _stats_lock: _watch_stats["failed"] += 1
            return

        # ── OCR 就绪检查（图片文件）──
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
        if ext in image_exts and not _check_ocr_ready():
            result = _handle_failure(filepath, filename, "ocr", "OCR 引擎未安装", retry_count)
            if result == "retry_later":
                return
            if result == "retry":
                retry_count += 1
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        # ── 逐页提取 + 内容分析 ──
        # _extract_pages 内部已 catch 所有 Exception，外层 try/except 是防御性兜底
        try:
            pages = _extract_pages(filepath, ext)
        except Exception as e:
            result = _handle_failure(filepath, filename, "extract", str(e), retry_count)
            if result == "retry":
                retry_count += 1
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        # 提取后检查取消信号（OCR 可能耗时很长）
        if _cancelled():
            return

        if not pages or not any(p.get("text", "").strip() for p in pages):
            # ── 文本提取为空？检查是否有图片可 OCR ──
            # 图片型 PDF / 扫描件：pdfplumber 可能提取到空文本，
            # 但页面实际包含图片，应尝试 OCR 而非直接失败
            has_images = any(p.get("images") for p in pages)
            if has_images and _check_ocr_ready():
                log_activity(
                    action="watch_v2_ocr_fallback",
                    detail=f"文本提取为空但存在图片，尝试 OCR: {filename}",
                    source=filename,
                )
                ocr_text_parts = []
                _ocr_cache = None  # OCR 结果缓存（避免多页重复调用）
                for p in pages:
                    if p.get("images"):
                        # 对图片型页面做 OCR（复用 _ocr_image 对页面截图的能力）
                        # 注：PDF 页面级 OCR 通过重读文件实现
                        try:
                            if _ocr_cache is None:
                                _ocr_cache = _ocr_image(filepath)  # 首次调用，缓存结果
                            ocr_result = _ocr_cache  # 后续页面复用缓存
                            if ocr_result.get("ok"):
                                page_text = ocr_result.get("text", "")
                                if page_text.strip():
                                    p["text"] = page_text
                                    p["ocr_conf"] = ocr_result.get("conf")
                                    ocr_text_parts.append(page_text)
                            elif not ocr_text_parts:
                                ocr_text_parts.append("")
                        except Exception:
                            if not ocr_text_parts:
                                ocr_text_parts.append("")
                    else:
                        ocr_text_parts.append(p.get("text", ""))

                # 如果 OCR 后仍为空 → 走原失败路径
                if not any(t.strip() for t in ocr_text_parts):
                    result = _handle_failure(filepath, filename, "extract",
                                             "所有页面提取为空（OCR 后仍无文本）", retry_count)
                    if result == "retry":
                        retry_count += 1
                        time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                        continue
                    return
                # OCR 成功提取到文本 → 继续正常处理流程
            else:
                result = _handle_failure(filepath, filename, "extract", "所有页面提取为空", retry_count)
                if result == "retry":
                    retry_count += 1
                    time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                    continue
                return

        page_analyses = []
        all_text_parts = []
        for p in pages:
            analysis = analyze_page_content(
                text=p.get("text", ""),
                page_images=p.get("images"),
                page_tables=p.get("tables"),
                ocr_conf=p.get("ocr_conf"),
                text_density_threshold=WATCH_V2_TEXT_DENSITY_THRESHOLD,
                ocr_conf_threshold=WATCH_V2_OCR_CONF_THRESHOLD,
            )
            page_analyses.append(analysis)
            all_text_parts.append(p.get("text", ""))

        full_text = "\n\n".join(all_text_parts)

        # ── WLNK 文件保留决策 ──
        retention = decide_file_retention(page_analyses)

        # ── AI 分类 ──
        if _cancelled():
            return
            
        try:
            classify_result = classify_document(full_text, file_metadata={"source_path": filepath})
        except Exception as e:
            result = _handle_failure(filepath, filename, "classify", str(e), retry_count)
            if result == "retry":
                retry_count += 1
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        if not classify_result.get("ok"):
            error_msg = classify_result.get("error", "分类失败")
            result = _handle_failure(filepath, filename, "classify", error_msg, retry_count)
            if result == "retry":
                retry_count += 1
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        annotated = classify_result.get("annotated", {})
        classification = classify_result.get("classification", {})
        field_sources = annotated.get("field_sources", {})
        overall_conf = annotated.get("overall_confidence", 0.0)

        # ── 置信度路由 ──
        metadata = dict(classification)
        metadata["source_path"] = filepath
        metadata["ingestion_source"] = "watch_v2"

        if overall_conf < CONFIDENCE_LOW:
            # 低置信度 → needs_review（不入库）
            _handle_failure(filepath, filename, "classify",
                            f"置信度过低 ({overall_conf:.2f} < {CONFIDENCE_LOW})", retry_count)
            return

        needs_review = overall_conf < CONFIDENCE_HIGH

        # ── 摄入 ──
        if _cancelled():
            return
            
        try:
            ingest_result = kb_query.ingest(
                text=full_text,
                metadata=metadata,
                collection=DEFAULT_COLLECTION,
                field_sources=field_sources,
                overall_confidence=overall_conf,
            )
        except Exception as e:
            result = _handle_failure(filepath, filename, "ingest", str(e), retry_count)
            if result == "retry":
                retry_count += 1
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        if not ingest_result.get("ok"):
            error_msg = ingest_result.get("error", "摄入失败")
            # 重复内容 → 删除原文件（已入库）+ 标记 done
            if "duplicate" in error_msg.lower() or "重复" in error_msg:
                log_activity(
                    action="watch_v2_duplicate_skipped",
                    detail=f"文件已存在于知识库: {error_msg}",
                    source=filename,
                )
                _append_state({"file": filename, "state": "done"})
                with _stats_lock: _watch_stats["processed"] += 1
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                return
            else:
                result = _handle_failure(filepath, filename, "ingest", error_msg, retry_count)
                if result == "retry":
                    retry_count += 1
                    time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                    continue
            return

        # ── 成功处理 ──
        # 最后一次取消检查：子线程可能在摄入完成后才收到取消信号
        # 此时主线程 timeout handler 已接管，不应再写状态或删文件
        if _cancelled():
            return
        with _stats_lock: _watch_stats["processed"] += 1

        # 如果 needs_review，记录状态
        if needs_review:
            _append_state({
                "file": filename,
                "state": "needs_review",
                "step": "classify",
                "error": f"置信度 ({overall_conf:.2f}) 低于高阈值 ({CONFIDENCE_HIGH})",
                "confidence": overall_conf,
            })
            with _stats_lock: _watch_stats["needs_review"] += 1

        # ── 文件保留/删除 ──
        if retention["keep_file"]:
            log_activity(
                action="watch_v2_kept",
                detail=f"保留原文件: {retention['reason']}",
                source=filename,
            )
        else:
            try:
                os.remove(filepath)
                log_activity(
                    action="watch_v2_deleted",
                    detail=f"删除原文件: {retention['reason']}",
                    source=filename,
                )
            except OSError as e:
                log_activity(
                    action="watch_v2_delete_failed",
                    detail=f"无法删除原文件: {e}",
                    source=filename,
                )

        log_activity(
            action="watch_v2_processed",
            detail=f"成功处理" + (" [待审核]" if needs_review else ""),
            source=filename,
        )

        # ── 处理成功，清理/保留状态记录 ──
        if needs_review:
            # needs_review 状态已在上面写入，补充文件保留信息
            # 如果文件被删，UI 可据此隐藏"查看文件"按钮
            if not retention["keep_file"]:
                _append_state({
                    "file": filename,
                    "state": "needs_review",
                    "file_deleted": True,
                    "step": "classify",
                    "confidence": overall_conf,
                })
        else:
            # 清理旧状态（retry/failed 等），但不写 done：
            # 文件会被删除（keep_file=false），Qdrant content_hash 负责去重
            _remove_state(filename)
            if retention["keep_file"]:
                # 文件保留 → 标记 done 防止重启后被重复处理
                _append_state({"file": filename, "state": "done"})
        return  # 成功退出


def _process_file_with_timeout(filepath: str):
    """带超时保护的文件处理。
    
    超时后: 发送取消信号给子线程 → 标记 retry → 回写入队。
    子线程收到取消信号后在检查点退出，避免状态冲突。
    """
    filename = os.path.basename(filepath)
    cancel_event = threading.Event()

    def target():
        try:
            _process_file(filepath, cancel_event=cancel_event)
        except Exception as e:
            # 如果已被取消，状态由主线程 timeout handler 负责
            if cancel_event.is_set():
                return
            log_activity(
                action="watch_v2_internal_error",
                detail=f"处理异常: {e}",
                source=filename,
            )
            # 写入 failed 状态，防止文件被静默丢失
            failure_type = _classify_failure("unknown", str(e))
            _append_state({
                "file": filename,
                "state": "failed",
                "step": "unknown",
                "error": f"内部异常: {e}",
                "failure_type": failure_type,
            })
            with _stats_lock: _watch_stats["failed"] += 1

    # daemon=True: 主进程崩溃时子线程自动终止。
    # 安全性由 content_hash 去重保证——文件下次重启会被重新处理，
    # 不会因线程被强制终止而产生重复数据。
    thread = threading.Thread(target=target, daemon=True, name=f"watcher-{filename[:20]}")
    thread.start()
    thread.join(timeout=WATCH_V2_PROCESSING_TIMEOUT)

    if thread.is_alive():
        # 发送取消信号，让子线程在检查点退出
        cancel_event.set()

        # 从状态中读取已有 retry_count（防止 timeout 无限重试循环）
        existing_state = _get_file_state(filename)
        existing_retry_count = existing_state.get("retry_count", 0) if existing_state else 0

        # 标记失败并检查策略
        failure_result = _handle_failure(
            filepath, filename, "timeout",
            f"处理超时（>{WATCH_V2_PROCESSING_TIMEOUT}秒）",
            retry_count=existing_retry_count,
        )

        # 根据策略决定是否重新入队
        if failure_result in ("retry", "retry_later"):
            if _queue is not None:
                try:
                    _queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
                except Empty:
                    log_activity(
                        action="watch_v2_requeue_failed",
                        detail=f"超时后重新入队失败: {filename}",
                        source=filename,
                    )

        # 等待子线程响应取消信号（最长 30 秒，给 LLM/Qdrant 等长阻塞调用足够时间到达检查点）
        POST_CANCEL_WAIT = 30
        thread.join(timeout=POST_CANCEL_WAIT)


# ═══════════════════════════════════════════
# 文件监控 + 处理循环
# ═══════════════════════════════════════════

class WatchHandlerV2(FileSystemEventHandler):
    """watchdog 事件处理器 v2 — 文件创建时入队。"""

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

        if _is_temp_file(filename):
            with _stats_lock: _watch_stats["skipped"] += 1
            return

        try:
            self.queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
        except Empty:
            with _stats_lock: _watch_stats["skipped"] += 1
            log_activity(
                action="watch_v2_queue_full",
                detail=f"队列已满，丢弃文件: {filename}",
                source=filename,
            )


def _processing_loop_v2(queue: Queue, stop_event: threading.Event):
    """后台处理循环 v2：从队列取文件，逐个处理。"""
    global _heartbeat_time

    log_activity(action="watch_v2_started", detail="守望文件夹 v2 处理循环启动")

    # 启动时扫描 inbox 中已有文件
    _scan_existing_files_v2(queue)

    # 恢复 retry 状态的文件
    _recover_retry_files(queue, stop_event)

    with _stats_lock: _watch_stats["running"] = True

    loop_count = 0
    while not stop_event.is_set():
        with _heartbeat_lock:
            _heartbeat_time = time.time()

        try:
            filepath = queue.get(timeout=2.0)
        except Empty:
            _cleanup_expired_states()
            # 定期救援扫描：救回因队列溢出被丢弃的文件
            loop_count += 1
            # 定期重检基础设施：infra 可能已恢复
            # 避免 infra_ok 维持 False 导致 _rescue_orphaned_files 跳过救援
            if loop_count % 15 == 0:  # ~30 秒一次
                infra = _check_infra()
                with _stats_lock:
                    _watch_stats["infra_ok"] = (infra["qdrant"] and infra["ollama"])
            if loop_count % 30 == 0:  # ~60 秒一次
                _rescue_orphaned_files(queue)
            continue

        loop_count += 1
        filename = os.path.basename(filepath)

        if not os.path.isfile(filepath):
            continue

        if _is_temp_file(filename):
            with _stats_lock: _watch_stats["skipped"] += 1
            continue

        # 检查已有状态（跳过 failed/needs_review 的文件，除非手动触发重试）
        existing_state = _get_file_state(filename)
        if existing_state:
            existing_status = existing_state.get("state", "")
            if existing_status in ("failed", "needs_review"):
                # 不自动重试，等用户手动操作
                continue

        # 基础设施检查
        infra = _check_infra()
        if not (infra["qdrant"] and infra["ollama"]):
            with _stats_lock: _watch_stats["infra_ok"] = False
            log_activity(
                action="watch_v2_infra_down",
                detail=f"基础设施不可用 (qdrant={infra['qdrant']}, ollama={infra['ollama']})",
            )
            # 标记为 retry，不阻塞处理循环
            # _recover_retry_files + _rescue_orphaned_files 会在恢复时重新入队
            _append_state({
                "file": filename,
                "state": "retry",
                "step": "infra_check",
                "error": f"基础设施不可用 (qdrant={infra['qdrant']}, ollama={infra['ollama']})",
            })
            continue

        with _stats_lock: _watch_stats["infra_ok"] = True

        # 磁盘空间检查
        disk = _check_disk_space(min_free_mb=100)
        if not disk["ok"]:
            log_activity(
                action="watch_v2_disk_full",
                detail=f"磁盘空间不足: {disk['free_mb']:.0f}MB 可用",
            )
            result = _handle_failure(filepath, filename, "any", "disk_full")
            if result == "retry_later":
                continue
            return

        # 写入完成检测
        if not _is_write_complete(filepath):
            time.sleep(1)
            # 文件可能在等待期间被删除（竞态保护）
            if os.path.isfile(filepath):
                try:
                    queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
                except Empty:
                    pass
            continue

        # 处理文件
        _process_file_with_timeout(filepath)

    with _stats_lock: _watch_stats["running"] = False
    log_activity(action="watch_v2_stopped", detail="守望文件夹 v2 处理循环已停止")


def _scan_existing_files_v2(queue: Queue):
    """扫描 inbox 中已有的文件并加入队列。"""
    if not os.path.isdir(INBOX_DIR):
        return

    files = []
    for filename in os.listdir(INBOX_DIR):
        filepath = os.path.join(INBOX_DIR, filename)
        if os.path.isfile(filepath) and not _is_temp_file(filename):
            files.append(filepath)

    for fp in sorted(files):
        try:
            queue.put(fp, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
        except Empty:
            with _stats_lock: _watch_stats["skipped"] += 1


def _rescue_orphaned_files(queue: Queue):
    """定期扫描 inbox，救回因队列溢出被丢弃的文件。
    
    基础设施宕机时跳过 — 避免 retry 文件被反复入队→检查→标记 retry 的死循环。
    """
    if not os.path.isdir(INBOX_DIR):
        return
    
    # 基础设施检查 — infra down 时不救援，等恢复后 _recover_retry_files 会处理
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
        if _is_temp_file(filename):
            continue
        entry = state.get(filename)
        if entry and entry.get("state") in ("failed", "needs_review", "done"):
            continue
        try:
            queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
            rescued += 1
        except Empty:
            break  # 队列满，下次循环再试
    if rescued > 0:
        log_activity(
            action="watch_v2_rescue",
            detail=f"救回 {rescued} 个遗漏文件",
        )


def _recover_retry_files(queue: Queue, stop_event: threading.Event):
    """恢复 retry 状态的文件——基础设施恢复后自动重试。
    
    启动时检查基础设施，不满足条件则跳过恢复（等 _rescue_orphaned_files 救援）。
    """
    # 基础设施检查 — 避免 retry 文件入队后被 infra_check 再次标记 retry
    infra = _check_infra()
    if not (infra["qdrant"] and infra["ollama"]):
        log_activity(
            action="watch_v2_retry_recovery_skipped",
            detail=f"基础设施不可用，跳过 retry 文件恢复 (qdrant={infra['qdrant']}, ollama={infra['ollama']})",
        )
        return

    state = _load_state()
    retry_files = [fname for fname, entry in state.items() if entry.get("state") == "retry"]
    if not retry_files:
        return

    log_activity(
        action="watch_v2_retry_recovery",
        detail=f"发现 {len(retry_files)} 个待重试文件",
    )

    for fname in retry_files:
        if stop_event.is_set():
            break
        filepath = os.path.join(INBOX_DIR, fname)
        if os.path.isfile(filepath):
            try:
                queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
            except Empty:
                pass


def _cleanup_expired_states():
    """清理过期的状态记录 + 去重（仅保留每文件最后一条）+ 应用延迟删除 + 文件过大时压缩。

    频率控制：每 WATCH_V2_CLEANUP_INTERVAL 秒最多一次，避免频繁全量重写。
    有 pending removals 或压缩触发时强制运行。

    流式处理：两遍扫描（只存行号不存内容），防止大文件 OOM。
    锁粒度：读取/构建在锁外，仅原子替换时持锁。
    """
    if not os.path.isfile(STATE_FILE):
        return

    # ── 频率控制 ──
    # CLEANUP_INTERVAL = 300  # 已移至配置项 WATCH_V2_CLEANUP_INTERVAL
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    now = time.time()

    if not hasattr(_cleanup_expired_states, "_last_run"):
        _cleanup_expired_states._last_run = 0.0

    elapsed = now - _cleanup_expired_states._last_run
    try:
        file_size = os.path.getsize(STATE_FILE)
    except OSError:
        return
    force = file_size > MAX_FILE_SIZE

    # 快照 pending removals（锁内）
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
        # ── Pass 1: 扫描所有行，记录每文件最后有效行的行号 ──
        # 不存储行内容，只存行号 → 内存 O(unique_files)
        last_line_nums = {}  # filename → line_number (0-based)
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

                # 应用 pending removals
                if fname in removals_snapshot:
                    continue

                # TTL 过期检查
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

                # 记录行号（后续的同名条目覆盖 → 自动去重）
                if fname in last_line_nums:
                    dedup_saved += 1
                last_line_nums[fname] = line_num

        # ── Pass 2: 只写保留行号的对应行到临时文件 ──
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

        # ── 原子替换（锁内 — 防止与 _append_state 竞争）──
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
                action="watch_v2_state_cleanup",
                detail=f"清理 {' + '.join(parts)} 条 ({reason}, {file_size//1024} KB)",
            )
    except OSError as e:
        log_activity(
            action="watch_v2_state_cleanup_failed",
            detail=f"清理状态文件失败: {e}",
        )
        if WATCH_V2_NOTIFY_ON_FATAL:
            print(f"[watcher_v2] ⚠️ 清理状态文件失败: {e}", file=sys.stderr)


# ═══════════════════════════════════════════
# 旧版迁移（v1 → v2）
# ═══════════════════════════════════════════

def _migrate_from_v1():
    """从旧版守望（v1，6 目录模型）迁移到 v2（统一收件箱 + JSONL）。

    迁移内容:
      1. data/watch/             → data/inbox/ （待处理文件）
      2. data/watch_staging/     → data/inbox/ （正在处理中的文件）
      3. data/watch_dead_letter/ → data/inbox/ + state.jsonl （DLQ 条目）
      4. data/watch_processed/   → 跳过（已成功处理，无需迁移）
      5. 删除旧目录，创建 .watch_v2_migrated 标记文件

    幂等：已迁移则跳过（通过标记文件检测）。
    """
    marker = os.path.join(PROJECT_DIR, "data", ".watch_v2_migrated")
    if os.path.isfile(marker):
        return

    old_dirs = {
        "watch":          os.path.join(PROJECT_DIR, "data", "watch"),
        "watch_staging":  os.path.join(PROJECT_DIR, "data", "watch_staging"),
        "watch_dead_letter": os.path.join(PROJECT_DIR, "data", "watch_dead_letter"),
        "watch_processed":   os.path.join(PROJECT_DIR, "data", "watch_processed"),
    }

    # 只有旧目录存在时才执行迁移
    if not any(os.path.isdir(d) for d in old_dirs.values()):
        _ensure_dir(os.path.dirname(marker))
        with open(marker, "w", encoding="utf-8") as f:
            f.write(datetime.now(timezone.utc).isoformat())
        return

    migrated_files = 0
    migrated_dlq = 0

    # ── 1. data/watch/ → inbox/ ──
    if os.path.isdir(old_dirs["watch"]):
        for filename in os.listdir(old_dirs["watch"]):
            if filename == ".gitkeep":
                continue
            src = os.path.join(old_dirs["watch"], filename)
            if os.path.isfile(src):
                dst = os.path.join(INBOX_DIR, filename)
                shutil.move(src, dst)
                migrated_files += 1

    # ── 2. data/watch_staging/ → inbox/ ──
    if os.path.isdir(old_dirs["watch_staging"]):
        for filename in os.listdir(old_dirs["watch_staging"]):
            if filename == ".gitkeep":
                continue
            src = os.path.join(old_dirs["watch_staging"], filename)
            if os.path.isfile(src):
                dst = os.path.join(INBOX_DIR, filename)
                shutil.move(src, dst)
                migrated_files += 1

    # ── 3. data/watch_dead_letter/ → inbox/ + state 条目 ──
    if os.path.isdir(old_dirs["watch_dead_letter"]):
        for filename in sorted(os.listdir(old_dirs["watch_dead_letter"])):
            if filename == ".gitkeep" or filename.endswith(".meta.json"):
                continue
            src = os.path.join(old_dirs["watch_dead_letter"], filename)
            if not os.path.isfile(src):
                continue

            # 读取旧版 .meta.json（如果存在）
            meta_path = src + ".meta.json"
            error = "从旧版 DLQ 迁移"
            step = "unknown"
            ts = datetime.now(timezone.utc).isoformat()

            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    error = meta.get("error", error)
                    step = meta.get("failed_step", step)
                    ts = meta.get("failed_at", ts)
                except (OSError, json.JSONDecodeError):
                    pass

            # 移动文件到 inbox
            dst = os.path.join(INBOX_DIR, filename)
            try:
                shutil.move(src, dst)
            except OSError:
                continue

            # 写入状态记录
            _append_state({
                "file": filename,
                "state": "failed",
                "step": step,
                "error": error,
                "failure_type": "migrated_from_v1",
            })
            migrated_dlq += 1

            # 删除 .meta.json
            if os.path.isfile(meta_path):
                try:
                    os.remove(meta_path)
                except OSError:
                    pass

    # ── 4. 清理旧目录 ——
    for dir_key in ["watch", "watch_staging", "watch_dead_letter", "watch_processed"]:
        old_dir = old_dirs[dir_key]
        if not os.path.isdir(old_dir):
            continue
        try:
            for item in os.listdir(old_dir):
                item_path = os.path.join(old_dir, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
            os.rmdir(old_dir)
        except OSError:
            pass

    # ── 5. 写入迁移标记 ──
    _ensure_dir(os.path.dirname(marker))
    with open(marker, "w", encoding="utf-8") as f:
        f.write(datetime.now(timezone.utc).isoformat())

    if migrated_files > 0 or migrated_dlq > 0:
        log_activity(
            action="watch_v2_migration",
            detail=f"从 v1 迁移: {migrated_files} 文件, {migrated_dlq} DLQ 条目",
        )
        print(f"[watcher_v2] 旧版迁移完成: {migrated_files} 文件, {migrated_dlq} DLQ")


# ═══════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════

def _check_lock_file() -> bool:
    """检查是否已有 watcher v2 实例在运行。"""
    if not os.path.isfile(LOCK_FILE):
        return True
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        return True
    try:
        import ctypes
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
    except OSError:
        pass
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass
    return True


def _write_lock_file():
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        log_activity(
            action="watch_v2_lock_failed",
            detail="无法写入锁文件",
        )


def _remove_lock_file():
    try:
        if os.path.isfile(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def start_watcher_v2() -> threading.Thread | None:
    """启动守望文件夹 v2 守护进程。"""
    global _observer, _worker_thread, _queue, _stop_event

    if not _check_lock_file():
        log_activity(
            action="watch_v2_multiple_instance",
            detail="已有守望进程 v2 在运行，拒绝重复启动",
        )
        print("[watcher_v2] 已有守望进程在运行，跳过启动。")
        return None

    # 确保 inbox 目录存在
    _ensure_dir(INBOX_DIR)
    _ensure_dir(os.path.dirname(STATE_FILE))

    # 旧版迁移（v1 → v2）
    _migrate_from_v1()

    # 初始化队列和信号
    _queue = Queue(maxsize=WATCH_V2_QUEUE_MAX_SIZE)
    _stop_event = threading.Event()

    # 启动文件监控
    _observer = Observer()
    handler = WatchHandlerV2(_queue, _stop_event)
    _observer.schedule(handler, INBOX_DIR, recursive=False)
    _observer.start()

    # 启动处理线程
    _worker_thread = threading.Thread(
        target=_processing_loop_v2,
        args=(_queue, _stop_event),
        # daemon=True: 主进程退出时自动终止，无需显式 join。
        # Qdrant content_hash 去重确保重启后不会重复摄入已处理的文件。
        daemon=True,
        name="citrinitas-watcher-v2",
    )
    _worker_thread.start()

    with _stats_lock: _watch_stats["running"] = True
    _write_lock_file()

    log_activity(action="watch_v2_started", detail="守望文件夹 v2 已启动")
    print("[watcher_v2] 守望文件夹 v2 已启动，监控目录:", INBOX_DIR)

    return _worker_thread


def stop_watcher_v2():
    """停止守望文件夹 v2 守护进程。"""
    global _observer, _stop_event

    if _stop_event:
        _stop_event.set()

    if _observer:
        _observer.stop()
        _observer.join(timeout=5)

    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=10)

    with _stats_lock: _watch_stats["running"] = False
    _remove_lock_file()
    log_activity(action="watch_v2_stopped", detail="守望文件夹 v2 已停止")


def is_watcher_v2_alive() -> bool:
    """检查 watcher v2 线程是否存活（心跳检测）。"""
    with _heartbeat_lock:
        last_beat = _heartbeat_time
    if last_beat == 0:
        return False
    return (time.time() - last_beat) < 60


def get_watch_v2_stats() -> dict:
    """获取守望文件夹 v2 运行统计。"""
    inbox_stats = get_inbox_stats()
    with _stats_lock:
        _watch_stats["pending"] = inbox_stats["pending"]
        return _watch_stats.copy()


def retry_file_v2(filename: str) -> bool:
    """
    手动触发重试某个文件。
    清除其状态记录，然后放入队列。
    """
    filepath = os.path.join(INBOX_DIR, filename)
    if not os.path.isfile(filepath):
        return False

    # 清除状态
    _remove_state(filename)

    # 入队
    if _queue is not None:
        try:
            _queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
            log_activity(
                action="watch_v2_manual_retry",
                detail=f"手动重试: {filename}",
                source=filename,
            )
            return True
        except Empty as e:
            log_activity(
                action="watch_v2_manual_retry_failed",
                detail=f"手动重试入队失败 (队列满): {filename}",
                source=filename,
            )
    return False
