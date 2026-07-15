"""
Citrinitas · 熔知 — 文本管线包

OCR / 文本提取 / 分块 / 嵌入 / 页面分析。
所有函数返回统一的 {"ok": bool, ...} 格式。

本包是 facade：所有子模块的公共函数在此重新导出，
外部 import text_pipeline 的使用方式完全不变。
"""

# OCR
from .ocr import (
    ocr_image,
    _ocr_paddle,
    _ocr_tesseract,
    _ocr_structured,
    _check_ocr_quality,
    _ensure_images_dir,
)

# 文本提取 & 编码检测
from .extract import (
    extract_text,
    detect_encoding,
    detect_language,
    _detect_language,
    parse_frontmatter,
)

# 嵌入
from .embed import _embed


def embed_text(texts: list[str]) -> list[list[float]]:
    """向量嵌入 — 将文本列表转换为向量列表。

    Args:
        texts: 待嵌入的文本列表，如 ["你好", "世界"]

    Returns:
        向量列表，每个向量 2560 维（qwen3-embedding:4b），
        与输入文本一一对应。
    """
    return _embed(texts)


# 切块
from .chunk import (
    _chunk_text,
    _text_hash,
    _extract_images,
    chunk_text_with_positions,
)


def chunk_text(text: str) -> list[str]:
    """文本切块 — 将长文本按语义边界切分为多个片段。

    Args:
        text: 待切分的原始文本

    Returns:
        切分后的文本片段列表。每个片段长度受
        pipe_cfg.yaml 中 chunk.max_chars 和 chunk.overlap 控制。
    """
    return _chunk_text(text)

# 页面分析
from .analyze import analyze_page_content
