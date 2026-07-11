"""
Citrinitas · 熔知 — 共享常量

被 doc_manager / qdrant_client / kb_query 等模块共同引用。
避免循环导入，内容保持最小化。

调参项从 config/settings.py 统一导入，本文件只保留真正的常量（路径 / 集合名 / 不可调参数）。
"""

import os
import requests

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
QDRANT_URL = os.environ.get("KB_QDRANT_URL", "http://127.0.0.1:6333")
# Windows 上 localhost 可能解析到 IPv6 ::1，但 Qdrant 只监听 IPv4
# 强制标准化为 127.0.0.1，避免连接失败
if "localhost" in QDRANT_URL:
    QDRANT_URL = QDRANT_URL.replace("localhost", "127.0.0.1")
DEFAULT_COLLECTION = "athanor_v1"

# ── 知识库大文件夹 library/（源文件 / 图片 / 状态集中于此，单一根目录）──
# 所有图片（书本插图 + OCR 抽取图）统一进 IMAGES_DIR，不分两处。
LIBRARY_DIR     = os.path.join(PROJECT_DIR, "library")
BOOKS_DIR       = os.path.join(LIBRARY_DIR, "books")            # 书籍源文件长期保留
INBOX_DIR       = os.path.join(LIBRARY_DIR, "inbox")           # 待摄入文件（知识库前厅）
IMAGES_DIR      = os.path.join(LIBRARY_DIR, "images")          # 所有图片统一一处
FILE_STATE_PATH = os.path.join(LIBRARY_DIR, "file_state.jsonl")  # 已保存内容状态索引

INGEST_LOG_PATH = os.path.join(PROJECT_DIR, "local_data", "ingest_log.jsonl")

# ── 从 pipe_cfg.yaml + .env 统一导入调参项 ──
from config.settings import (
    OLLAMA_URL,
    EMBED_MODEL,
    EMBED_DIM,
    CHUNK_MAX_CHARS,
    CHUNK_OVERLAP,
    SEARCH_TOP_K,
    SEARCH_SCORE_THRESHOLD,
    SEARCH_CHUNKS_PER_DOC,
    FACET_CACHE_TTL,
    RERANK_ENABLED,
    RERANK_MODEL,
    RERANK_TOP_N,
    INGEST_SKIP_DUPLICATES,
    CONFIDENCE_LOW,
    CONFIDENCE_HIGH,
    TABLE_SPLIT_THRESHOLD,
)


def _check_qdrant() -> bool:
    """检查 Qdrant 是否运行（纯检查，无副作用）。"""
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
