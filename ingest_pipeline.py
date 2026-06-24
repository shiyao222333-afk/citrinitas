"""
Ingest Pipeline — Qdrant payload builder.

Extracted from kb_query.py (v0.7.0 B1 refactor).

职责:
  build_payloads() — 将文本/块/向量/元数据组装为 Qdrant points 列表
  不负责: 文本提取、分块、嵌入计算、Qdrant 写入（由 kb_query.ingest() 协调）
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from qconst import QDRANT_URL
from text_pipeline import _text_hash, _detect_language
from config.classifications import normalize_facet_values


def _prepare_metadata(base_meta: dict, text: str, source: str, file_path: str) -> dict:
    """从 base_meta 提取并规范化所有元数据字段，返回单一字典。"""
    base_meta = base_meta or {}

    # 分面字段（枚举守卫）
    facet_raw = {
        "content_type":     base_meta.get("content_type", "knowledge"),
        "domain":           base_meta.get("domain", []),
        "temporal_nature":  base_meta.get("temporal_nature", "timeboxed"),
        "epistemic_status": base_meta.get("epistemic_status", "unverified"),
    }
    facet_norm = normalize_facet_values(facet_raw)

    # 时间线字段
    publish_date   = base_meta.get("publish_date", None)
    effective_date = base_meta.get("effective_date", None)
    expiry_date    = base_meta.get("expiry_date", None)

    # 来源字段
    author        = base_meta.get("author", "")
    source_url    = base_meta.get("source_url", "")
    file_type     = base_meta.get("file_type", "txt")
    ingest_method = base_meta.get("ingest_method", "manual")

    return {
        # 分面
        "content_type":    facet_norm["content_type"],
        "domain":          facet_norm["domain"] if isinstance(facet_norm["domain"], list) else [facet_norm["domain"]],
        "temporal_nature": facet_norm["temporal_nature"],
        "epistemic_status": facet_norm["epistemic_status"],
        # 生命周期
        "lifecycle":      base_meta.get("lifecycle", "published"),
        "project_source":  base_meta.get("project_source", ""),
        "udc_code":        base_meta.get("udc_code", ""),
        # 知识管理
        "knowledge_type":  base_meta.get("knowledge_type", ""),
        "is_personal":    base_meta.get("is_personal", False),
        "trust_score":    base_meta.get("trust_score", 3),
        "tags":           base_meta.get("tags", []),
        "is_canonical":   base_meta.get("is_canonical", True),
        "relations":      base_meta.get("relations", []),
        "keywords":       base_meta.get("keywords", []),
        "auto_summary":   base_meta.get("auto_summary", ""),
        # 时效 + 版本
        "title":          base_meta.get("title") or source,
        "publish_date":   publish_date,
        "effective_date": effective_date,
        "expiry_date":   expiry_date,
        "version":        base_meta.get("version", ""),
        # 来源
        "author":         author,
        "source_url":     source_url,
        "file_type":      file_type,
        "ingest_method":  ingest_method,
        "source_path":    file_path or "",
        # 内容创作
        "target_platform": base_meta.get("target_platform", "none"),
        "related_product": base_meta.get("related_product", ""),
        # 系统
        "language":       base_meta.get("language") or _detect_language(text),
        "access_level":   base_meta.get("access_level", "private"),
        "batch_id":       base_meta.get("batch_id", ""),
        "needs_review":   base_meta.get("needs_review", False),
        # 字段来源 + 置信度
        "field_sources":  base_meta.get("field_sources", {}),
        "confidence":     base_meta.get("confidence_overall", None),
        # 图片
        "valid_images":   base_meta.get("_valid_images", []),
    }


def _build_point(chunk: str, vec: list, i: int, total_chunks: int,
                doc_id: str, full_text_hash: str, metadata: dict,
                sparse_vec: Optional[tuple] = None) -> dict:
    """构建单个 Qdrant point。"""
    point_id = uuid.uuid4().int >> 64
    m = metadata  # 简写

    payload = {
        "text": chunk,
        "title": m["title"],
        "source": m.get("source", "unknown"),
        "chunk_index": i,
        "total_chunks": total_chunks,
        "doc_id": doc_id,
        "doc_uid": doc_id,
        "content_hash": full_text_hash,
        "images": m["valid_images"],
        # 分面
        "content_type":    m["content_type"],
        "domain":          m["domain"],
        "temporal_nature": m["temporal_nature"],
        "epistemic_status": m["epistemic_status"],
        # 生命周期
        "lifecycle":      m["lifecycle"],
        "project_source":  m["project_source"],
        "udc_code":        m["udc_code"],
        # 知识管理
        "knowledge_type":  m["knowledge_type"],
        "is_personal":    m["is_personal"],
        "trust_score":    m["trust_score"],
        "tags":           m["tags"] if isinstance(m["tags"], list) else [],
        "is_canonical":   m["is_canonical"],
        "relations":      m["relations"] if isinstance(m["relations"], list) else [],
        "keywords":       m["keywords"] if isinstance(m["keywords"], list) else [],
        "auto_summary":   m["auto_summary"],
        # timeline
        "timeline": {
            "published": m["publish_date"],
            "effective": m["effective_date"],
            "expiry":    m["expiry_date"],
            "ingested":  m["ingested_at"],
            "accessed":  None,
        },
        # origin
        "origin": {
            "author":         m["author"],
            "source_url":     m["source_url"],
            "file_type":      m["file_type"],
            "ingest_method":  m["ingest_method"],
            "source_path":    m["source_path"],
        },
        # stats
        "stats": {"access_count": 0, "starred": False},
        # 内容创作
        "target_platform": m["target_platform"],
        "related_product": m["related_product"],
        "version":        m["version"],
        # 系统
        "language":       m["language"],
        "access_level":   m["access_level"],
        "batch_id":       m["batch_id"],
        "is_archived":   False,
        "needs_review":   m["needs_review"],
        # 字段来源 + 置信度
        "field_sources":  m["field_sources"],
        "confidence":     m["confidence"],
        # 预留扩展
        "ext_text1": None, "ext_text2": None, "ext_text3": None,
        "ext_text4": None, "ext_text5": None,
        "ext_num1":  None, "ext_num2":  None, "ext_num3": None,
        "ext_bool1": None, "ext_bool2": None, "ext_bool3": None,
        "ext_date1": None, "ext_date2": None, "ext_date3": None,
    }

    point = {
        "id": point_id,
        "vector": {"dense": vec},
        "payload": payload,
    }
    if sparse_vec:
        point["vector"]["bm25"] = {"indices": sparse_vec[0], "values": sparse_vec[1]}
    return point


def build_payloads(
    text: str,
    chunks: list,
    vectors: list,
    sparse_vectors: Optional[list] = None,
    base_meta: Optional[dict] = None,
    file_path: str = "",
    source: str = "unknown",
    model: str = "",
) -> dict:
    """
    构建 Qdrant points 列表（含完整 payload）。

    参数:
        text:       原始全文（用于 content_hash 和语言检测）
        chunks:     已切块的文本列表
        vectors:    嵌入向量列表（与 chunks 一一对应）
        base_meta:  用户提供的元数据字典
        file_path:  原始文件路径
        source:     来源标识
        model:      嵌入模型名

    返回:
        {"ok": True, "points": [...], "doc_id": "...",
         "content_hash": "...", "valid_images": [...], "ingested_at": "..."}
    """
    base_meta = base_meta or {}
    doc_id = base_meta.get("doc_id") or str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc).isoformat()
    full_text_hash = _text_hash(text)

    # 准备元数据（注入 ingested_at）
    metadata = _prepare_metadata(base_meta, text, source, file_path)
    metadata["ingested_at"] = ingested_at
    metadata["source"] = source

    # 构建 points
    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        sparse_vec = None
        if sparse_vectors and i < len(sparse_vectors):
            sparse_vec = sparse_vectors[i]
        point = _build_point(
            chunk, vec, i, len(chunks), doc_id, full_text_hash, metadata, sparse_vec
        )
        points.append(point)

    return {
        "ok": True,
        "points": points,
        "doc_id": doc_id,
        "content_hash": full_text_hash,
        "valid_images": metadata["valid_images"],
        "ingested_at": ingested_at,
    }
