"""
自动元数据提取（EPUB/PDF/HTML）+ 元数据合并
"""

import os
import logging

logger = logging.getLogger(__name__)

from .encoding import _read_text_with_fallback
from .registry import detect_file_type


def extract_auto_metadata(file_path: str, file_info: dict = None) -> dict:
    """
    从文件中提取自动可获取的元数据。

    仅对层级1文件有效（EPUB/PDF/HTML）。
    返回的每条字段附带 metadata_source 标记。

    Args:
        file_path: 文件路径
        file_info: detect_file_type() 的结果

    Returns:
        {
            "ok": bool,
            "metadata": {
                "title": {"value": "...", "source": "file", "confidence": 1.0},
                "author": {"value": "...", "source": "file", "confidence": 1.0},
                ...
            },
            "flat": {  # 扁平版本，方便直接 merge
                "title": "...",
                "author": "...",
            },
            "source_count": int,  # 成功提取的字段数
        }
    """
    if file_info is None:
        file_info = detect_file_type(file_path)

    if not file_info.get("has_auto_metadata"):
        return {"ok": True, "metadata": {}, "flat": {}, "source_count": 0,
                "note": "此文件类型不支持自动元数据提取"}

    fmt = file_info["format"]

    extractors = {
        "epub": _metadata_epub,
        "pdf":  _metadata_pdf,
        "html": _metadata_html,
        "htm":  _metadata_html,
    }

    extractor = extractors.get(fmt)
    if extractor is None:
        return {"ok": False, "metadata": {}, "flat": {}, "source_count": 0,
                "error": f"不支持的元数据提取格式: {fmt}"}

    try:
        raw_meta = extractor(file_path)
    except Exception as e:
        return {"ok": False, "metadata": {}, "flat": {}, "source_count": 0,
                "error": f"元数据提取失败: {e}"}

    # 包装为 source-tagged 格式（三元组：value + source + confidence）
    tagged = {}
    flat = {}
    for key, value in raw_meta.items():
        if value and str(value).strip():
            tagged[key] = {
                "value": str(value).strip(),
                "source": "file",
                "confidence": 1.0,  # 文件自带元数据 — 确定性数据
            }
            flat[key] = str(value).strip()

    return {
        "ok": True,
        "metadata": tagged,
        "flat": flat,
        "source_count": len(tagged),
    }


# ── 各格式元数据提取函数 ─────────────────────────────────────────────────────

def _metadata_epub(file_path: str) -> dict:
    """从 EPUB 提取 Dublin Core 元数据"""
    try:
        from ebooklib import epub
    except ImportError:
        return {}

    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        logger.debug(f"[FileHandler] EPUB 元数据读取失败: {e}")
        return {}

    meta = {}
    # Dublin Core 字段映射
    dc_map = {
        "title":   ("title",),
        "creator": ("author",),
        "publisher": ("publisher",),
        "identifier": ("isbn",),
        "language": ("language",),
        "date":     ("date",),
        "description": ("description",),
    }

    for dc_key, target_keys in dc_map.items():
        values = book.get_metadata("DC", dc_key)
        if values:
            # values 是 [(value, attrs), ...] 的列表
            val = values[0][0] if isinstance(values[0], tuple) else str(values[0])
            for target_key in target_keys:
                if val:
                    meta[target_key] = val

    # ISBN 特殊处理：identifier 可能包含 "urn:isbn:" 前缀
    if meta.get("isbn"):
        meta["isbn"] = meta["isbn"].replace("urn:isbn:", "").strip()

    return meta


def _metadata_pdf(file_path: str) -> dict:
    """从 PDF 提取 Document Info 元数据"""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return {}

    try:
        reader = PdfReader(file_path)
        info = reader.metadata
        if info is None:
            return {}
    except Exception as e:
        logger.debug(f"[FileHandler] PDF 元数据读取失败: {e}")
        return {}

    meta = {}
    field_map = {
        "/Title":    "title",
        "/Author":   "author",
        "/Subject":  "subject",
        "/Creator":  "creator",
        "/Producer": "producer",
    }

    for pdf_key, meta_key in field_map.items():
        val = getattr(info, pdf_key.strip("/").lower(), None) or info.get(pdf_key, None)
        if val and str(val).strip():
            meta[meta_key] = str(val).strip()

    # 页数
    meta["page_count"] = str(len(reader.pages))

    return meta


def _metadata_html(file_path: str) -> dict:
    """从 HTML 提取 title + meta 标签"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return {}

    text = _read_text_with_fallback(file_path)
    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception as e:
        logger.debug(f"[FileHandler] HTML 元数据解析失败: {e}")
        return {}

    meta = {}

    # <title>
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        meta["title"] = title_tag.string.strip()

    # <meta name="description">
    desc = soup.find("meta", attrs={"name": "description"})
    if desc and desc.get("content"):
        meta["description"] = desc["content"].strip()

    # <meta name="keywords">
    kw = soup.find("meta", attrs={"name": "keywords"})
    if kw and kw.get("content"):
        meta["keywords"] = kw["content"].strip()

    # <meta name="author">
    author = soup.find("meta", attrs={"name": "author"})
    if author and author.get("content"):
        meta["author"] = author["content"].strip()

    return meta


# ══════════════════════════════════════
# 合并元数据（file > llm > manual）
# ══════════════════════════════════════

def merge_metadata(file_meta: dict, llm_meta: dict, manual_meta: dict = None) -> dict:
    """
    按优先级合并元数据：文件自带 > LLM 推断 > 手动默认值。

    每个字段返回 value + source + confidence 三元组。

    Args:
        file_meta: extract_auto_metadata() 返回的 flat 字典
        llm_meta:  auto_classify() 返回的分类结果
        manual_meta: 用户手动填写的值（可选）

    Returns:
        {"title": {"value": "...", "source": "file", "confidence": 1.0}, ...}
    """
    if manual_meta is None:
        manual_meta = {}

    # 需要合并的字段列表
    mergeable_fields = ["title", "author", "keywords", "description"]

    result = {}

    for field in mergeable_fields:
        if field in file_meta and file_meta[field]:
            result[field] = {"value": file_meta[field], "source": "file",
                             "confidence": 1.0}
        elif field in llm_meta and llm_meta[field]:
            result[field] = {"value": llm_meta[field], "source": "llm",
                             "confidence": 0.7}
        elif field in manual_meta and manual_meta[field]:
            result[field] = {"value": manual_meta[field], "source": "manual",
                             "confidence": 0.5}

    return result
