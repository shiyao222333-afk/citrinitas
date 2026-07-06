"""
Services package — v1.1.0 架构重构中从 kb_query.py 拆出。

暴露公共 API，让调用方可以直接 from services import ingest_service。
"""
from .ingest_service import ingest, ingest_batch

__all__ = ["ingest", "ingest_batch", "ingest_service"]
