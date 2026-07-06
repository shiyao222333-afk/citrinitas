"""
Citrinitas Watch Folder — 文件处理管线。

逐页提取 → WLNK 决策 → AI 分类 → 置信度路由 → 摄入 → 保留/删除。
依赖 state.py（全局状态）和 failures.py（故障处理）。
"""

import os
import time
import threading
from queue import Full

import requests

from config.settings import (
    WATCH_V2_MAX_FILE_SIZE_MB,
    WATCH_V2_MAX_AUTO_RETRIES,
    WATCH_V2_AUTO_RETRY_DELAY,
    WATCH_V2_TEXT_DENSITY_THRESHOLD,
    WATCH_V2_OCR_CONF_THRESHOLD,
    WATCH_V2_PROCESS_TIMEOUT,
    WATCH_V2_QUEUE_PUT_TIMEOUT,
)
from text_pipeline import (
    analyze_page_content,
    ocr_image as _ocr_image,
    extract_text as _extract_text,
)
from classify_pipeline import classify_document, route_by_confidence
from qconst import CONFIDENCE_LOW, CONFIDENCE_HIGH
from utils.activity_log import log_activity
from services.ingest_service import ingest

from watcher.state import (
    _watch_stats, _stats_lock,
    _append_state, _remove_state, _get_file_state,
    _queued_files, _in_flight, _queue,
)
from watcher.utils import (
    _check_ocr_ready, _check_infra, _check_disk_space, _is_write_complete,
)
from watcher.failures import _handle_failure, _classify_failure


# ═══════════════════════════════════════════
# WLNK 多页决策
# ═══════════════════════════════════════════

def decide_file_retention(page_analyses: list[dict]) -> dict:
    """
    文件级保留决策 — WLNK 原则：文件可删 = min(每页可删性)。

    任一页不可删 → 保留整个文件。

    返回:
        {
            "keep_file": bool,
            "reason": str,
            "pages_deletable": int,
            "pages_total": int,
        }
    """
    if not page_analyses:
        return {"keep_file": True, "reason": "无页面数据，保守保留", "pages_deletable": 0, "pages_total": 0}

    total = len(page_analyses)
    deletable = sum(1 for p in page_analyses if p["deletable"])
    non_deletable = total - deletable

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
    """逐页提取文档内容。返回 [{"text": "...", "images": [...], "tables": [...], "ocr_conf": None}, ...]"""
    pages = []

    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    page_images = []
                    page_tables = []

                    try:
                        img_list = getattr(page, 'images', []) or []
                        page_images = [f"pdf_img_{i}" for i in range(len(img_list))]
                    except (AttributeError, TypeError):
                        pass

                    try:
                        tbl_list = page.extract_tables() or []
                        page_tables = [f"table_{i}" for i in range(len(tbl_list))]
                    except (AttributeError, TypeError):
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
                    action="watch_pdfplumber_missing",
                    detail="pdfplumber 未安装，PDF 文件将无法提取文本。安装: pip install pdfplumber",
                )
            pages.append({"text": "", "images": [], "tables": [], "ocr_conf": None})
        except (OSError, ValueError):
            pages.append({"text": "", "images": [], "tables": [], "ocr_conf": None})

    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
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
        except (OSError, UnicodeDecodeError):
            pages.append({"text": "", "images": [], "tables": [], "ocr_conf": None})

    else:
        try:
            result = _extract_text(filepath)
            text = result.get("text", "") if result.get("ok") else ""
        except Exception:
            text = ""
        pages.append({"text": text, "images": [], "tables": [], "ocr_conf": None})

    return pages


# ═══════════════════════════════════════════
# 处理步骤
# ═══════════════════════════════════════════

def _do_prechecks(filepath: str, ext: str, filename: str, retry_count: int) -> tuple:
    """前置检查（格式/大小/存在/OCR）。返回 (ok, should_retry, new_retry_count)。"""
    supported = {".txt", ".md", ".json", ".csv", ".log", ".pdf", ".docx",
                 ".pptx", ".epub", ".html", ".htm", ".xml", ".jpg", ".jpeg",
                 ".png", ".bmp", ".tiff", ".tif"}
    if ext not in supported:
        _handle_failure(filepath, filename, "format_check", f"不支持的文件格式: {ext}")
        return False, False, retry_count

    if WATCH_V2_MAX_FILE_SIZE_MB > 0:
        try:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            if size_mb > WATCH_V2_MAX_FILE_SIZE_MB:
                _handle_failure(filepath, filename, "size_check",
                                f"文件过大 ({size_mb:.1f}MB > {WATCH_V2_MAX_FILE_SIZE_MB}MB)")
                return False, False, retry_count
        except OSError as e:
            result = _handle_failure(filepath, filename, "read_error", str(e), retry_count)
            if result == "retry":
                return False, True, retry_count + 1
            return False, False, retry_count

    if not os.path.isfile(filepath):
        _append_state({
            "file": filename, "state": "failed",
            "step": "read_error", "error": "文件在处理前已不存在",
            "failure_type": "read_error",
        })
        with _stats_lock: _watch_stats["failed"] += 1
        return False, False, retry_count

    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}
    if ext in image_exts and not _check_ocr_ready():
        result = _handle_failure(filepath, filename, "ocr", "OCR 引擎未安装", retry_count)
        if result == "retry_later":
            return False, False, retry_count
        if result == "retry":
            return False, True, retry_count + 1
        return False, False, retry_count

    return True, False, retry_count


def _do_ocr_fallback(pages: list, filepath: str, filename: str,
                      retry_count: int, cancel_event: threading.Event) -> tuple:
    """当文本提取为空时尝试 OCR 兜底。返回 (success, full_text, should_retry, new_retry_count)。"""
    has_images = any(p.get("images") for p in pages)
    if not has_images or not _check_ocr_ready():
        result = _handle_failure(filepath, filename, "extract", "所有页面提取为空", retry_count)
        if result == "retry":
            return False, None, True, retry_count + 1
        return False, None, False, retry_count

    log_activity(
        action="watch_ocr_fallback",
        detail=f"文本提取为空但存在图片，尝试 OCR: {filename}",
        source=filename,
    )
    ocr_text_parts = []
    _ocr_cache = None
    for p in pages:
        if p.get("images"):
            try:
                if _ocr_cache is None:
                    _ocr_cache = _ocr_image(filepath)
                ocr_result = _ocr_cache
                if ocr_result.get("ok"):
                    page_text = ocr_result.get("text", "")
                    if page_text.strip():
                        p["text"] = page_text
                        p["ocr_conf"] = ocr_result.get("conf")
                        ocr_text_parts.append(page_text)
                elif not ocr_text_parts:
                    ocr_text_parts.append("")
            except (OSError, requests.RequestException, ValueError):
                if not ocr_text_parts:
                    ocr_text_parts.append("")
        else:
            ocr_text_parts.append(p.get("text", ""))

    if not any(t.strip() for t in ocr_text_parts):
        result = _handle_failure(filepath, filename, "extract",
                                "所有页面提取为空（OCR 后仍无文本）", retry_count)
        if result == "retry":
            return False, None, True, retry_count + 1
        return False, None, False, retry_count

    return True, "\n\n".join(ocr_text_parts), False, retry_count


def _do_classify(full_text: str, filepath: str, filename: str,
                 retry_count: int, cancel_event: threading.Event) -> tuple:
    """AI 分类 + 置信度路由。返回 (metadata, field_sources, overall_conf, needs_review, should_retry, new_retry_count)。"""
    if cancel_event is not None and cancel_event.is_set():
        return None, None, 0.0, False, False, retry_count

    try:
        classify_result = classify_document(full_text, file_metadata={"source_path": filepath})
    except (requests.RequestException, ValueError, KeyError) as e:
        result = _handle_failure(filepath, filename, "classify", str(e), retry_count)
        if result == "retry":
            return None, None, 0.0, False, True, retry_count + 1
        return None, None, 0.0, False, False, retry_count

    if not classify_result.get("ok"):
        error_msg = classify_result.get("error", "分类失败")
        result = _handle_failure(filepath, filename, "classify", error_msg, retry_count)
        if result == "retry":
            return None, None, 0.0, False, True, retry_count + 1
        return None, None, 0.0, False, False, retry_count

    annotated = classify_result.get("annotated", {})
    classification = classify_result.get("classification", {})
    field_sources = annotated.get("field_sources", {})
    overall_conf = annotated.get("overall_confidence", 0.0)

    metadata = dict(classification)
    metadata["source_path"] = filepath
    metadata["ingestion_source"] = "watch"

    needs_review, should_dlq = route_by_confidence(
        overall_conf, CONFIDENCE_LOW, CONFIDENCE_HIGH)
    if should_dlq:
        _handle_failure(filepath, filename, "classify",
                        f"置信度过低 ({overall_conf:.2f} < {CONFIDENCE_LOW})", retry_count)
        return None, None, overall_conf, False, False, retry_count

    return metadata, field_sources, overall_conf, needs_review, False, retry_count


def _do_ingest(full_text: str, metadata: dict, field_sources: dict,
               overall_conf: float, filepath: str, filename: str,
               retry_count: int, cancel_event: threading.Event) -> tuple:
    """摄入知识库。返回 (ingest_result, should_retry, new_retry_count)。"""
    if cancel_event is not None and cancel_event.is_set():
        return None, False, retry_count

    try:
        ingest_result = ingest(
            text=full_text,
            metadata=metadata,
            collection="athanor_v1",
            field_sources=field_sources,
            overall_confidence=overall_conf,
        )
    except (requests.RequestException, ValueError) as e:
        result = _handle_failure(filepath, filename, "ingest", str(e), retry_count)
        if result == "retry":
            return None, True, retry_count + 1
        return None, False, retry_count

    if not ingest_result.get("ok"):
        error_msg = ingest_result.get("error", "摄入失败")
        if "duplicate" in error_msg.lower() or "重复" in error_msg:
            log_activity(
                action="watch_duplicate_skipped",
                detail=f"文件已存在于知识库: {error_msg}",
                source=filename,
            )
            _append_state({"file": filename, "state": "done"})
            with _stats_lock: _watch_stats["processed"] += 1
            try:
                os.remove(filepath)
            except OSError:
                pass
            return ingest_result, False, retry_count
        result = _handle_failure(filepath, filename, "ingest", error_msg, retry_count)
        if result == "retry":
            return None, True, retry_count + 1
        return None, False, retry_count

    return ingest_result, False, retry_count


def _do_post_ingest(filepath: str, filename: str, retention: dict,
                    needs_review: bool, overall_conf: float,
                    cancel_event: threading.Event) -> None:
    """处理摄入成功后的文件保留/删除和状态更新。"""
    if cancel_event is not None and cancel_event.is_set():
        return

    with _stats_lock: _watch_stats["processed"] += 1

    if needs_review:
        _append_state({
            "file": filename,
            "state": "needs_review",
            "step": "classify",
            "error": f"置信度 ({overall_conf:.2f}) 低于高阈值 ({CONFIDENCE_HIGH})",
            "confidence": overall_conf,
        })
        with _stats_lock: _watch_stats["needs_review"] += 1

    if retention["keep_file"]:
        log_activity(
            action="watch_kept",
            detail=f"保留原文件: {retention['reason']}",
            source=filename,
        )
    else:
        try:
            os.remove(filepath)
            log_activity(
                action="watch_deleted",
                detail=f"删除原文件: {retention['reason']}",
                source=filename,
            )
        except OSError as e:
            log_activity(
                action="watch_delete_failed",
                detail=f"无法删除原文件: {e}",
                source=filename,
            )

    log_activity(
        action="watch_processed",
        detail=f"成功处理" + (" [待审核]" if needs_review else ""),
        source=filename,
    )

    if needs_review:
        if not retention["keep_file"]:
            _append_state({
                "file": filename,
                "state": "needs_review",
                "file_deleted": True,
                "step": "classify",
                "confidence": overall_conf,
            })
    else:
        _remove_state(filename)
        if retention["keep_file"]:
            _append_state({"file": filename, "state": "done"})


# ═══════════════════════════════════════════
# 文件处理主流程
# ═══════════════════════════════════════════

def _process_file(filepath: str, cancel_event: threading.Event = None):
    """处理单个文件：逐页提取 → WLNK 决策 → 分类 → 摄入 → 保留/删除。"""
    def _cancelled():
        return cancel_event is not None and cancel_event.is_set()

    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()
    with _stats_lock: _watch_stats["infra_ok"] = True
    retry_count = 0
    max_retries = WATCH_V2_MAX_AUTO_RETRIES

    while retry_count <= max_retries:
        if _cancelled():
            log_activity(action="watch_cancelled", source=filename,
                         detail="处理超时取消，由主线程接管")
            return

        # 标记「处理中」，让收件箱 UI 实时显示进度（extract → classify → ingest）
        _append_state({
            "file": filename,
            "state": "processing",
            "step": "extract",
        })

        ok, should_retry, retry_count = _do_prechecks(filepath, ext, filename, retry_count)
        if not ok:
            if should_retry:
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        try:
            pages = _extract_pages(filepath, ext)
        except Exception as e:
            result = _handle_failure(filepath, filename, "extract", str(e), retry_count)
            if result == "retry":
                retry_count += 1
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        if _cancelled():
            return

        if not pages or not any(p.get("text", "").strip() for p in pages):
            success, ocr_text, should_retry, retry_count = _do_ocr_fallback(
                pages, filepath, filename, retry_count, cancel_event)
            if not success:
                if should_retry:
                    time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                    continue
                return
            full_text = ocr_text
        else:
            all_text_parts = [p.get("text", "") for p in pages]
            full_text = "\n\n".join(all_text_parts)

        page_analyses = []
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

        retention = decide_file_retention(page_analyses)

        _append_state({
            "file": filename,
            "state": "processing",
            "step": "classify",
        })
        metadata, field_sources, overall_conf, needs_review, should_retry, retry_count = _do_classify(
            full_text, filepath, filename, retry_count, cancel_event)
        if metadata is None:
            if should_retry:
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        metadata["needs_review"] = needs_review
        _append_state({
            "file": filename,
            "state": "processing",
            "step": "ingest",
        })
        ingest_result, should_retry, retry_count = _do_ingest(
            full_text, metadata, field_sources, overall_conf,
            filepath, filename, retry_count, cancel_event)
        if ingest_result is None:
            if should_retry:
                time.sleep(WATCH_V2_AUTO_RETRY_DELAY)
                continue
            return

        # 重复文件已在 _do_ingest 内部完成处理（标记 done / 删除文件 / 计数），
        # 此处不可再走 _do_post_ingest，否则会重复计数。
        if not ingest_result.get("ok"):
            return

        _do_post_ingest(filepath, filename, retention, needs_review, overall_conf, cancel_event)
        return


def _process_file_with_timeout(filepath: str):
    """带超时保护的文件处理。"""
    filename = os.path.basename(filepath)
    cancel_event = threading.Event()

    def target():
        try:
            _process_file(filepath, cancel_event=cancel_event)
        except Exception as e:
            if cancel_event.is_set():
                return
            log_activity(
                action="watch_internal_error",
                detail=f"处理异常: {e}",
                source=filename,
            )
            failure_type = _classify_failure("unknown", str(e))
            _append_state({
                "file": filename,
                "state": "failed",
                "step": "unknown",
                "error": f"内部异常: {e}",
                "failure_type": failure_type,
            })
            with _stats_lock: _watch_stats["failed"] += 1

    thread = threading.Thread(target=target, daemon=True, name=f"watcher-{filename[:20]}")
    thread.start()
    thread.join(timeout=WATCH_V2_PROCESS_TIMEOUT)

    if thread.is_alive():
        cancel_event.set()

        existing_state = _get_file_state(filename)
        existing_retry_count = existing_state.get("retry_count", 0) if existing_state else 0

        failure_result = _handle_failure(
            filepath, filename, "timeout",
            f"处理超时（>{WATCH_V2_PROCESS_TIMEOUT}秒）",
            retry_count=existing_retry_count,
        )

        if failure_result in ("retry", "retry_later"):
            if _queue is not None:
                try:
                    _queued_files.add(filepath)
                    _queue.put(filepath, timeout=WATCH_V2_QUEUE_PUT_TIMEOUT)
                except Full:
                    log_activity(
                        action="watch_requeue_failed",
                        detail=f"超时后重新入队失败: {filename}",
                        source=filename,
                    )

        POST_CANCEL_WAIT = 30
        thread.join(timeout=POST_CANCEL_WAIT)
