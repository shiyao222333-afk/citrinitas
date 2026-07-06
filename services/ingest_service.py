"""
摄入服务 — 从 kb_query.py 拆出（v1.1.0 架构重构）

职责:
  - 摄入管线编排（_step_* 步骤函数）
  - ingest / ingest_batch 公共 API
  - 摄入并发锁

调用方:
  - kb_query.py (CLI 入口)
  - pages/ingest.py (Web UI 摄入页面)
  - watcher/processor.py (守望文件夹自动摄入)
"""
import requests
import json
import os
import sys
import re
import threading
import logging
from typing import Optional
from collections import defaultdict

from qconst import (
    PROJECT_DIR, QDRANT_URL, DEFAULT_COLLECTION,
    IMAGES_DIR, INGEST_LOG_PATH, _check_qdrant,
    OLLAMA_URL, EMBED_MODEL, EMBED_DIM,
    INGEST_SKIP_DUPLICATES, CONFIDENCE_LOW, CONFIDENCE_HIGH,
)
from doc_manager import _log_ingest
from qdrant_client import _ensure_collection
from text_pipeline import (
    _embed, _chunk_text, _text_hash, _extract_images, _ensure_images_dir,
    detect_encoding, extract_text,
)
from sparse_encoder import encode_sparse, flush_vocab
from ingest_pipeline import build_payloads
from utils.activity_log import log_activity

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 摄入管线 — 可编排的步骤流水线
# ═══════════════════════════════════════════

# ── 步骤函数 ──

def _step_qdrant_check(state: dict) -> dict:
    """Step 1: 确认 Qdrant 可连通，集合存在"""
    if not _ensure_collection(state["collection"]):
        return {"ok": False, "error": "Qdrant 未运行。请先启动 Qdrant（双击 run.bat）。"}
    return {"ok": True}


def _step_read_content(state: dict) -> dict:
    """Step 2: 从文件或参数中读取文本"""
    file_path = state.get("file_path")
    text = state.get("text")

    if file_path:
        if not os.path.exists(file_path):
            return {"ok": False, "error": f"文件不存在: {file_path}"}
        ext = os.path.splitext(file_path)[1].lower()
        text_formats = (".txt", ".md", ".json", ".csv", ".log")
        if ext in text_formats:
            enc = detect_encoding(file_path)
            try:
                with open(file_path, "r", encoding=enc) as f:
                    text = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="latin-1") as f:
                    text = f.read()
        else:
            result = extract_text(file_path)
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error", "文本提取失败")}
            text = result["text"]
        state["text"] = text
        state["source"] = os.path.basename(file_path)
    elif text:
        meta = state.get("metadata") or {}
        state["source"] = meta.get("source", "直接输入")
        state["text"] = text
    else:
        return {"ok": False, "error": "请提供 file_path 或 text"}

    state["source"] = state["source"] or "unknown"

    if not state["text"] or not state["text"].strip():
        return {"ok": False, "error": "文本内容为空"}

    return {"ok": True}


def _step_dedup(state: dict) -> dict:
    """Step 3: 检查内容哈希，防止重复入库"""
    if not state.get("skip_duplicates", True):
        return {"ok": True, "skipped": True}

    content_hash = _text_hash(state["text"])
    state["content_hash"] = content_hash

    try:
        resp = requests.post(
            f"{QDRANT_URL}/collections/{state['collection']}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "content_hash", "match": {"value": content_hash}}]
                },
                "limit": 1
            },
            timeout=10
        )
        if resp.status_code == 200 and resp.json().get("result", {}).get("points"):
            dup_source = resp.json()["result"]["points"][0]["payload"].get("source", "未知")
            return {
                "ok": False,
                "error": "内容重复，已跳过",
                "duplicate_of": dup_source,
                "content_hash": content_hash,
            }
    except Exception:
        pass  # 去重失败不阻断主流程

    return {"ok": True}


def _step_extract_images(state: dict) -> dict:
    """Step 4: 提取并验证文本中的图片引用"""
    _ensure_images_dir()
    image_refs = _extract_images(state["text"])
    valid_images = []
    for img_path in image_refs:
        if os.path.isfile(img_path):
            valid_images.append(os.path.relpath(os.path.abspath(img_path), PROJECT_DIR))
        elif os.path.isfile(os.path.join(IMAGES_DIR, os.path.basename(img_path))):
            valid_images.append(os.path.relpath(os.path.join(IMAGES_DIR, os.path.basename(img_path)), PROJECT_DIR))
    state["valid_images"] = valid_images
    return {"ok": True}


def _step_chunk(state: dict) -> dict:
    """Step 5: 将文本切成块"""
    chunks = _chunk_text(state["text"])
    if not chunks:
        return {"ok": False, "error": "切块后无内容"}
    state["chunks"] = chunks
    return {"ok": True}


def _step_embed(state: dict) -> dict:
    """Step 6: 为每个块生成嵌入向量（含重试机制）"""
    chunks = state["chunks"]
    model = state.get("model", EMBED_MODEL)
    max_retries = 3
    retry_delay = 5  # 秒

    vectors = []
    for attempt in range(max_retries):
        try:
            vectors = _embed(chunks, model=model)
            break  # 成功，退出重试循环
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"嵌入失败（尝试 {attempt+1}/{max_retries}）: {e}，"
                    f"{retry_delay}秒后重试..."
                )
                time.sleep(retry_delay)
            else:
                return {"ok": False, "error": f"嵌入失败（已重试{max_retries}次）: {e}"}

    if not vectors:
        return {"ok": False, "error": "所有块嵌入失败"}
    if len(vectors) < len(chunks) * 0.5:
        return {
            "ok": False,
            "error": f"嵌入成功率过低 ({len(vectors)}/{len(chunks)})，已中止"
        }
    if len(vectors) < len(chunks):
        logger.warning(f"{len(chunks) - len(vectors)}/{len(chunks)} 块嵌入失败，已跳过")
        state["chunks"] = chunks[:len(vectors)]

    state["vectors"] = vectors
    return {"ok": True}


def _step_generate_sparse_vectors(state: dict) -> dict:
    """Step 6.5: 为每个块生成稀疏向量（BM25）"""
    chunks = state["chunks"]
    sparse_vectors = []

    try:
        for chunk in chunks:
            indices, values = encode_sparse(chunk, update_vocab=False)
            sparse_vectors.append((indices, values))
    except Exception as e:
        return {"ok": False, "error": f"稀疏向量生成失败: {e}"}

    if not sparse_vectors:
        return {"ok": False, "error": "所有块稀疏向量生成失败"}

    flush_vocab()  # 批量摄入结束后一次性落盘（避免每块重写整个词典文件）
    state["sparse_vectors"] = sparse_vectors
    return {"ok": True}


def _step_pre_store_hooks(state: dict) -> dict:
    """Step 7: 执行预存储钩子（Nigredo 等外部程序在此介入）"""
    from config.hooks import get_hooks
    hook_failures = []
    for hook in get_hooks():
        try:
            result = hook(state)
            if result is not None:
                state = result
        except Exception as e:
            msg = f"预存储钩子 {getattr(hook, '__name__', str(hook))} 执行失败: {e}"
            logger.warning(msg)
            hook_failures.append(msg)
    if hook_failures:
        state["hook_failures"] = hook_failures
    return {"ok": True}


def _step_build_payloads(state: dict) -> dict:
    """Step 8: 构建 Qdrant points 列表"""
    base_meta = state.get("metadata") or {}

    if state.get("field_sources"):
        base_meta["field_sources"] = state["field_sources"]
    if state.get("overall_confidence") is not None:
        base_meta["confidence_overall"] = state["overall_confidence"]
    base_meta["_valid_images"] = state.get("valid_images", [])

    result = build_payloads(
        text=state["text"],
        chunks=state["chunks"],
        vectors=state["vectors"],
        sparse_vectors=state.get("sparse_vectors"),
        base_meta=base_meta,
        file_path=state.get("file_path") or "",
        source=state.get("source", "unknown"),
        model=state.get("model", EMBED_MODEL),
    )
    state["points"] = result["points"]
    state["doc_id"] = result["doc_id"]
    state["content_hash"] = result["content_hash"]
    state["valid_images"] = result["valid_images"]
    state["ingested_at"] = result["ingested_at"]
    return {"ok": True}


def _step_write_qdrant(state: dict) -> dict:
    """Step 9: 将 points 写入 Qdrant"""
    try:
        resp = requests.put(
            f"{QDRANT_URL}/collections/{state['collection']}/points",
            json={"points": state["points"]},
            timeout=30
        )
        resp.raise_for_status()
    except Exception as e:
        return {"ok": False, "error": f"写入 Qdrant 失败: {e}"}
    return {"ok": True}


def _step_log_ingest(state: dict) -> dict:
    """Step 10: 写入摄入日志（非阻断步骤 — 失败不导致摄入回滚）。"""
    try:
        _log_ingest({
            "source_file": state.get("file_path") or "",
            "source_text": state["text"][:500] if not state.get("file_path") else None,
            "collection": state["collection"],
            "doc_id": state["doc_id"],
            "content_hash": state.get("content_hash", ""),
            "embed_model": state.get("model", EMBED_MODEL),
            "ingested_at": state["ingested_at"],
        })
    except Exception as e:
        logger.warning(f"[ingest] 摄入日志写入失败（数据已入库）: {e}")
    return {"ok": True}


# ── 步骤管线定义 ──
PIPELINE = [
    ("qdrant_check",     _step_qdrant_check),
    ("read_content",     _step_read_content),
    ("dedup",            _step_dedup),
    ("images",           _step_extract_images),
    ("chunk",            _step_chunk),
    ("sparse_embed",    _step_generate_sparse_vectors),
    ("embed",            _step_embed),
    ("pre_store_hooks",  _step_pre_store_hooks),
    ("build_payloads",   _step_build_payloads),
    ("write_qdrant",     _step_write_qdrant),
    ("log_ingest",       _step_log_ingest),
]

# ── 摄入并发保护锁 ──
_ingest_lock = threading.Lock()


def ingest(
    file_path: str = None,
    text: str = None,
    collection: str = DEFAULT_COLLECTION,
    metadata: dict = None,
    model: str = EMBED_MODEL,
    skip_duplicates: bool = None,
    skip_steps: list = None,
    field_sources: dict = None,
    overall_confidence: float = None,
) -> dict:
    """
    摄入文档到知识库（可编排管线）。

    10 个步骤按序执行，可通过 skip_steps 跳过任意步骤。

    参数:
        file_path: 文件路径（与 text 二选一）
        text: 文本内容（与 file_path 二选一）
        collection: Qdrant 集合名
        metadata: 自定义元数据
        model: 嵌入模型名
        skip_duplicates: 是否跳过重复内容
        skip_steps: 要跳过的步骤名列表，如 ["dedup", "images", "log_ingest"]
        field_sources: 字段来源标记
        overall_confidence: 整体置信度

    返回:
        {"ok": true/false, "chunks": N, "collection": "...", "source": "...", ...}
    """
    skip = set(skip_steps or [])
    if skip_duplicates is None:
        skip_duplicates = INGEST_SKIP_DUPLICATES
    if not skip_duplicates:
        skip.add("dedup")

    state = {
        "file_path": file_path,
        "text": text,
        "collection": collection,
        "metadata": metadata or {},
        "model": model,
        "skip_duplicates": skip_duplicates,
        "field_sources": field_sources,
        "overall_confidence": overall_confidence,
        "source": "",
        "content_hash": "",
        "chunks": [],
        "vectors": [],
        "valid_images": [],
        "doc_id": "",
        "ingested_at": "",
        "points": [],
    }

    try:
        with _ingest_lock:
            for step_name, step_fn in PIPELINE:
                if step_name in skip:
                    continue
                result = step_fn(state)
                if not result.get("ok"):
                    log_activity(
                        action="ingest_failed",
                        doc_id=state.get("doc_id", ""),
                        detail=result.get("error", f"步骤 {step_name} 失败"),
                        collection=state["collection"],
                        source=state.get("source", ""),
                    )
                    return result
    except Exception as e:
        import traceback
        err_msg = f"摄入异常中断: {e}"
        log_activity(
            action="ingest_crash",
            doc_id=state.get("doc_id", ""),
            detail=f"{err_msg}\n{traceback.format_exc()}",
            collection=state["collection"],
            source=state.get("source", ""),
        )
        return {"ok": False, "error": err_msg, "source": state.get("source", ""), "file_path": file_path}

    ingestion_source = (metadata or {}).get("ingestion_source", "手动输入" if not state.get("file_path") else "文件上传")
    log_activity(
        action="ingest_success",
        doc_id=state["doc_id"],
        detail=state.get("source", ""),
        collection=state["collection"],
        source=ingestion_source,
    )
    return {
        "ok": True,
        "chunks": len(state["chunks"]),
        "collection": state["collection"],
        "source": state["source"],
        "doc_id": state["doc_id"],
        "content_hash": state.get("content_hash", ""),
        "images": state["valid_images"],
        "hook_failures": state.get("hook_failures", []),
    }


def ingest_batch(
    items: list,
    collection: str = DEFAULT_COLLECTION,
    metadata: dict = None,
    model: str = EMBED_MODEL,
    skip_duplicates: bool = None,
    skip_steps: list = None,
    field_sources: dict = None,
    overall_confidence: float = None,
) -> dict:
    """
    批量摄入：多个文件/文本依次走同一管线。

    参数:
        items: 列表，每个元素是 {"file_path": "..."} 或 {"text": "..."}
        其余参数同 ingest()

    返回:
        {
            "ok": True,
            "total": N,
            "succeeded": M,
            "failed": F,
            "results": [{"ok": true/false, "source": "...", ...}, ...]
        }
    """
    results = []
    succeeded = 0
    failed = 0

    for item in items:
        file_path = item.get("file_path")
        text = item.get("text")
        item_meta = item.get("metadata", {})
        merged_meta = {**(metadata or {}), **item_meta}

        result = ingest(
            file_path=file_path,
            text=text,
            collection=collection,
            metadata=merged_meta,
            model=model,
            skip_duplicates=skip_duplicates,
            skip_steps=skip_steps,
            field_sources=field_sources,
            overall_confidence=overall_confidence,
        )
        results.append(result)
        if result.get("ok"):
            succeeded += 1
        else:
            failed += 1

    return {
        "ok": True,
        "total": len(items),
        "succeeded": succeeded,
        "failed": failed,
        "results": results,
    }
