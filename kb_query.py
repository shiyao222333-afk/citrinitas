"""
KB Query Engine - 中文技术文档知识库问答系统
版本: v1.0.0 — 守望文件夹自动摄入 + 混合检索 + 待审核队列

架构:
  摄入: 图片/文本 → PaddleOCR/PPStructureV3 → 分块嵌入 → Qdrant
  查询: 自然语言 → 向量搜索 → LLM API合成 → 程序渲染HTML/PDF

用法:
  # 问答（端到端：搜索 → API合成 → HTML报告 → PDF）
  python kb_query.py "齿轮的失效形式有哪些" --answer
  
  # 纯搜索（不调用 LLM）
  python kb_query.py "齿轮的失效形式有哪些" --top 10
  
  # 摄入文档
  python kb_query.py --ingest "D:/Documents/KnowledgeBase/机械设计/原始文件/齿轮设计基础.txt"
  
  # OCR 图片（方案B：OCR → 质量检查 → WorkBuddy审核 → 入库）
  python kb_query.py --ocr "photo.jpg" --source "手册-P3"
  python kb_query.py --ocr "photo.jpg" --check-only          # 只识别不入库，先审核
  python kb_query.py --ocr "photo.jpg" --engine structured  # PPStructureV3 结构化识别（公式+表格+图表）

环境变量（问答模式需配置 API）:
  KB_LLM_BASE_URL    LLM API 地址（默认 https://api.deepseek.com/v1）
  KB_LLM_API_KEY      API Key（需自行申请）
  KB_LLM_MODEL        模型名（默认 deepseek-chat）
"""
import requests
import json
import sys
import os
import argparse
import re
import subprocess
import io
import base64
import math
from typing import Optional
from collections import defaultdict
import hashlib
import uuid
import threading
from datetime import datetime, timezone
import tempfile
from docx import Document
from bs4 import BeautifulSoup
from config.classifications import normalize_facet_values, CLASSIFY_RULES
from sparse_encoder import encode_sparse, encode_sparse_query
from utils.activity_log import log_activity

from qconst import (
    PROJECT_DIR, QDRANT_URL, DEFAULT_COLLECTION,
    IMAGES_DIR, INGEST_LOG_PATH, _check_qdrant,
    OLLAMA_URL, EMBED_MODEL, EMBED_DIM,
    INGEST_SKIP_DUPLICATES, CONFIDENCE_LOW, CONFIDENCE_HIGH,
)
from doc_manager import (
    _log_ingest, read_ingest_log,
    list_documents, get_document, delete_document, update_document,
    update_metadata, set_doc_relations, search_by_doc_id, get_doc_ids,
)
from qdrant_client import (
    _ensure_collection, create_collection, list_collections,
    clear_collection, delete_collection, get_embed_models, has_any_data,
)
def route_by_confidence(overall_conf: float, conf_low: float, conf_high: float) -> tuple:
    """
    置信度三档路由。
    返回 (needs_review, should_dlq)。
    """
    if overall_conf >= conf_high:
        return False, False
    elif overall_conf >= conf_low:
        return True, False
    else:
        return False, True


from text_pipeline import (
    _embed, _chunk_text, _text_hash, _extract_images, _ensure_images_dir,
    _detect_language, detect_language, detect_encoding,
    extract_text, ocr_image,
)
from search_engine import search, answer
from classify_pipeline import (
    classify_document, auto_classify,
    _make_field, match_rules, match_all_rules,
    extract_file_fields, call_llm_for_missing,
    merge_parallel, fill_defaults, calculate_confidence,
    SOURCE_CONFIDENCE, FIELD_WEIGHTS,
    REQUIRED_FACET_FIELDS, SMART_DEFAULTS,
)
from ingest_pipeline import build_payloads

__version__ = "1.0.2"


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
    """Step 6: 为每个块生成嵌入向量"""
    chunks = state["chunks"]
    model = state.get("model", EMBED_MODEL)

    try:
        vectors = _embed(chunks, model=model)
    except Exception as e:
        return {"ok": False, "error": f"嵌入失败: {e}"}

    if not vectors:
        return {"ok": False, "error": "所有块嵌入失败"}
    if len(vectors) < len(chunks) * 0.5:
        return {
            "ok": False,
            "error": f"嵌入成功率过低 ({len(vectors)}/{len(chunks)})，已中止"
        }
    if len(vectors) < len(chunks):
        print(f"  [WARN] {len(chunks) - len(vectors)}/{len(chunks)} 块嵌入失败，已跳过")
        state["chunks"] = chunks[:len(vectors)]

    state["vectors"] = vectors
    return {"ok": True}

def _step_generate_sparse_vectors(state: dict) -> dict:
    """Step 6.5: 为每个块生成稀疏向量（BM25）"""
    chunks = state['chunks']
    sparse_vectors = []
    
    try:
        for chunk in chunks:
            indices, values = encode_sparse(chunk, update_vocab=True)
            sparse_vectors.append((indices, values))
    except Exception as e:
        return {'ok': False, 'error': f'稀疏向量生成失败: {e}'}
    
    if not sparse_vectors:
        return {'ok': False, 'error': '所有块稀疏向量生成失败'}
    
    state['sparse_vectors'] = sparse_vectors
    return {'ok': True}




def _step_pre_store_hooks(state: dict) -> dict:
    """Step 7: 执行预存储钩子（Nigredo 等外部程序在此介入）

    钩子可从 config/hooks.py 注册表中获取。
    每个钩子是 callable(state) -> state 的函数。
    当前默认为空（无钩子），不阻塞管线。
    """
    from config.hooks import get_hooks
    for hook in get_hooks():
        try:
            state = hook(state)
        except Exception as e:
            print(f"  [WARN] 预存储钩子 {hook.__name__} 执行失败: {e}")
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
        # 日志写入失败不阻断摄入 — 数据已在 Qdrant 中
        import logging
        logging.getLogger(__name__).warning(f"[ingest] 摄入日志写入失败（数据已入库）: {e}")
    return {"ok": True}


# ── 步骤管线定义 ──
# 每个元素: (步骤名, 函数)
# 步骤名用于 skip_steps 参数
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


# ═══════════════════════════════════════════
# 核心 API
# ═══════════════════════════════════════════

# ── 摄入并发保护锁（watcher + 手动上传不能同时写入）──
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
        field_sources: 字段来源标记（阶段二新增）
        overall_confidence: 整体置信度（阶段二新增）

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
        # 中间结果（步骤中填充）
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






# ═════════════════════════════════════════
# CLI 入口 ═════════════════════════════════════════

if __name__ == "__main__":
    # 修复 Windows GBK 环境下 print 非 ASCII 字符崩溃问题
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description="WorkBuddy 知识库引擎")
    parser.add_argument("query", nargs="*", help="搜索查询")
    parser.add_argument("--top", type=int, default=None, help=f"返回结果数（默认 {SEARCH_TOP_K}）")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="集合名称")
    parser.add_argument("--ingest", default=None, help="摄入文件路径")
    parser.add_argument("--text", default=None, help="直接摄入文本内容（与 --source 配合）")
    parser.add_argument("--ocr", default=None, help="OCR 图片路径")
    parser.add_argument("--engine", default="paddle", choices=["paddle", "tesseract", "structured"], help="OCR 引擎")
    parser.add_argument("--check-only", action="store_true", help="只 OCR 不入库")
    parser.add_argument("--llm-optimize", action="store_true", help="用LLM优化OCR结果（自动修复错别字）")
    parser.add_argument("--source", default=None, help="来源标识")
    parser.add_argument("--answer", action="store_true", help="端到端问答")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名")
    parser.add_argument("--llm-base-url", default=None, help="LLM API 地址")
    parser.add_argument("--llm-api-key", default=None, help="LLM API Key")
    parser.add_argument("--threshold", type=float, default=None, help=f"相关度阈值（默认 {SEARCH_SCORE_THRESHOLD}）")
    parser.add_argument("--table-split-threshold", type=int, default=None, help="表格行拆分阈值（默认用 TABLE_SPLIT_THRESHOLD）")
    parser.add_argument("--model", default=EMBED_MODEL, help="嵌入模型")
    parser.add_argument("--output", default=None, help="输出目录")
    args = parser.parse_args()

    query_str = " ".join(args.query) if isinstance(args.query, list) else args.query

    if args.ocr:
        # 导入OCR工作流
        try:
            from ocr_workflow import do_ocr
            do_ocr(
                image_path=args.ocr,
                source=args.source or "",
                engine=args.engine,
                check_only=args.check_only,
                collection=args.collection,
                model=args.model,
                llm_optimize=args.llm_optimize,
                llm_api_key=args.llm_api_key or os.environ.get("KB_LLM_API_KEY", ""),
                llm_base_url=args.llm_base_url or os.environ.get("KB_LLM_BASE_URL", ""),
                llm_model=args.llm_model or os.environ.get("KB_LLM_MODEL", "deepseek-chat")
            )
        except ImportError:
            print("❌ 错误: ocr_workflow.py 未找到。请确保 ocr_workflow.py 在同一目录下。")
            sys.exit(1)
    elif args.ingest:
        result = ingest(file_path=args.ingest, metadata={"source": args.source or ""}, collection=args.collection, model=args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.text and args.source:
        result = ingest(text=args.text, metadata={"source": args.source}, collection=args.collection, model=args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif query_str and args.answer:
        result = answer(
            query_str,
            top_k=args.top,
            collection=args.collection,
            model=args.model,
            threshold=args.threshold,
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            llm_api_key=args.llm_api_key,
            output_dir=args.output,
            table_split_threshold=args.table_split_threshold
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif query_str:
        result = search(
            query_str,
            top_k=args.top,
            collection=args.collection,
            model=args.model,
            score_threshold=args.threshold
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()

def get_facet_stats(collection: str = None) -> dict:
    """获取分面统计分布（全量滚动统计）。"""
    if collection is None:
        collection = DEFAULT_COLLECTION

    try:
        import requests as _req

        facet_counts = {
            "content_type": {},
            "domain": {},
            "temporal_nature": {},
            "epistemic_status": {},
        }

        offset = None
        while True:
            payload = {"limit": 1000, "with_payload": True, "with_vectors": False}
            if offset is not None:
                payload["offset"] = offset

            resp = _req.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            points = data.get("result", {}).get("points", [])
            offset = data.get("result", {}).get("next_page_offset")

            if not points:
                break

            for point in points:
                payload = point.get("payload", {})
                for facet in facet_counts:
                    value = payload.get(facet, "unknown")
                    if isinstance(value, list):
                        for v in value:
                            facet_counts[facet][v] = facet_counts[facet].get(v, 0) + 1
                    else:
                        facet_counts[facet][value] = facet_counts[facet].get(value, 0) + 1

            if offset is None:
                break

        return {"ok": True, "facets": facet_counts}

    except Exception as e:
        return {"ok": False, "error": str(e)}
