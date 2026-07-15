"""
Text Pipeline — 文本提取 & 编码检测

extract_text / detect_encoding / detect_language。
"""

import os
import re
import logging

from docx import Document
from bs4 import BeautifulSoup

from .ocr import ocr_image

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 编码检测
# ═══════════════════════════════════════════

def detect_encoding(file_path: str, sample_size: int = 10000) -> str:
    """
    检测文件编码。优先 chardet，失败后用 UTF-8 → GBK → latin-1 兜底链。
    sample_size: 用于检测的字节数（默认 10000，约 10KB）
    """
    with open(file_path, "rb") as f:
        raw = f.read(sample_size)
    if not raw:
        return "utf-8"  # 空文件，默认 UTF-8

    # 先试 charset_normalizer（如果已安装）
    try:
        from charset_normalizer import detect as chardet_detect
        result = chardet_detect(raw)
        enc = (result.get("encoding") or "").strip().lower()
        conf = result.get("confidence", 0)
        if enc and conf >= 0.6:
            enc_map = {
                "utf-8": "utf-8",
                "ascii": "utf-8",
                "gb2312": "gbk",
                "gbk": "gbk",
                "gb18030": "gb18030",
                "big5": "big5",
                "iso-8859-1": "latin-1",
                "windows-1252": "cp1252",
            }
            return enc_map.get(enc, enc)
    except ImportError:
        pass  # chardet 未安装，走兜底链

    # 兜底链：UTF-8 → GBK → latin-1
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gbk")
        return "gbk"
    except UnicodeDecodeError:
        pass
    # 最后兜底：latin-1 永不失败（但可能乱码）
    return "latin-1"


# ═══════════════════════════════════════════
# 语言检测
# ═══════════════════════════════════════════

def _detect_language(text: str) -> str:
    """通过 Unicode 区块统计检测语言（前 2000 字）。"""
    sample = text[:2000]
    if not sample.strip():
        return "zh"
    total = len(sample)
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    hiragana = sum(1 for c in sample if '\u3040' <= c <= '\u309f')
    katakana = sum(1 for c in sample if '\u30a0' <= c <= '\u30ff')
    hangul = sum(1 for c in sample if '\uac00' <= c <= '\ud7af')
    latin = sum(1 for c in sample if c.isascii() and c.isalpha())

    cjk_ratio = cjk / total
    ja_ratio = (hiragana + katakana) / total
    ko_ratio = hangul / total
    en_ratio = latin / total

    if cjk_ratio >= 0.30:
        return "zh"
    if ja_ratio >= 0.10:
        return "ja"
    if ko_ratio >= 0.10:
        return "ko"
    if en_ratio >= 0.60:
        return "en"
    return "zh"  # 兜底


def detect_language(text: str) -> str:
    """
    程序检测文本语言（中/英），不调用 LLM，确定性输出。

    逻辑：
        - 统计 CJK 统一汉字范围（\u4e00-\u9fff）字符占比
        - 占比 > 30% → "zh"
        - 否则 → "en"（默认英文）
        - 空文本 → "en"

    返回:
        "zh" | "en" | "ja" | "ko"  (远期可扩展)
    """
    if not text:
        return "en"
    total = len(text)
    if total == 0:
        return "en"
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cjk_count / total > 0.3:
        return "zh"
    return "en"


# ═══════════════════════════════════════════
# 文本提取
# ═══════════════════════════════════════════

def extract_text(file_path: str) -> dict:
    """
    统一文本提取入口。

    ⚠️ 实际提取已统一委托给 utils.file_handler.extract_text
    （全格式：txt/md/json/csv/docx/html/srt/pdf/epub/pptx/图片OCR 等）。
    本函数仅作为兼容包装层，保留旧调用方依赖的 chars / meta 字段，
    避免分散的多套提取实现再次出现「某条路径漏支持某格式」的问题。

    返回:
        {"ok": True, "text": "...", "chars": N, "meta": {}}
        {"ok": False, "error": "..."}
    """
    from utils.file_handler import extract_text as _impl_extract_text
    res = _impl_extract_text(file_path)
    # 兼容旧返回字段（部分旧调用方读取 chars / meta）
    if "chars" not in res:
        res["chars"] = len(res.get("text", "") or "")
    if "meta" not in res:
        res["meta"] = {}
    return res
