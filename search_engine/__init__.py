# flake8: noqa: E501
"""
Search Engine 包 — 语义搜索 / LLM 问答合成 / 分面统计

从 search_engine.py 拆分（v1.0.2 代码质量清理）。
外部调用方无需修改：``from search_engine import search, answer, get_facet_stats`` 保持不变。
"""

from .core import search, _build_qdrant_filter, _query_qdrant_rrf
from .answer import (
    answer, OUTPUT_DIR, _call_llm_api, _renumber_citations, _build_synthesis_prompt, _expand_chunks,
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
)
from .utils import _sanitize_html, _chunk_has_table, _chunk_is_garbled, _dedup_chunks
from .facets import get_facet_stats

__all__ = [
    # 公共 API
    "search",
    "answer",
    "get_facet_stats",
    "OUTPUT_DIR",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    # 内部辅助（测试/调试用）
    "_build_qdrant_filter",
    "_query_qdrant_rrf",
    "_call_llm_api",
    "_renumber_citations",
    "_build_synthesis_prompt",
    "_expand_chunks",
    "_sanitize_html",
    "_chunk_has_table",
    "_chunk_is_garbled",
    "_dedup_chunks",
]
