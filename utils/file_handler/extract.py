"""
文本提取（按格式分发到各提取函数）
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

from .registry import detect_file_type
from .encoding import _read_text_with_fallback


def extract_text(file_path: str, file_info: dict = None) -> dict:
    """
    从文件提取纯文本内容。

    Args:
        file_path: 文件路径
        file_info: detect_file_type() 的结果，可选（None 时自动检测）

    Returns:
        {"ok": bool, "text": str, "error": str|None, "extraction_method": str}
    """
    if file_info is None:
        file_info = detect_file_type(file_path)
        if not file_info["ok"]:
            return {"ok": False, "text": "", "error": file_info["error"],
                    "extraction_method": None}

    fmt = file_info["format"]

    # 映射格式 → 提取函数
    extractors = {
        "epub": _extract_epub,
        "pdf":  _extract_pdf,
        "html": _extract_html,
        "htm":  _extract_html,
        "txt":  _extract_text_file,
        "md":   _extract_text_file,
        "json": _extract_text_file,
        "csv":  _extract_text_file,
        "srt":  _extract_srt,
        "docx": _extract_docx,
        "pptx": _extract_pptx,
    }

    extractor = extractors.get(fmt)
    if extractor is None:
        # 图片格式：返回空文本（留给 OCR 页面处理）
        if file_info["tier"] == 3:
            return {
                "ok": True,
                "text": "",
                "error": None,
                "extraction_method": "ocr_required",
                "ocr_required": True,
            }
        # 未知格式：兜底尝试
        try:
            text = _read_text_with_fallback(file_path)
            return {"ok": True, "text": text, "error": None,
                    "extraction_method": "direct_read_fallback"}
        except Exception as e:
            return {"ok": False, "text": "", "error": str(e), "extraction_method": None}

    try:
        result = extractor(file_path)
        if isinstance(result, str):
            result = {"ok": True, "text": result, "error": None}
        result.setdefault("extraction_method", file_info["extraction"])
        result.setdefault("ok", True)
        result.setdefault("error", None)
        return result
    except Exception as e:
        return {"ok": False, "text": "", "error": str(e),
                "extraction_method": file_info["extraction"]}


# ── 各格式提取函数 ──────────────────────────────────────────────────────────

def _extract_text_file(file_path: str) -> dict:
    """纯文本格式：TXT / MD / JSON / CSV"""
    text = _read_text_with_fallback(file_path)
    return {"ok": True, "text": text, "error": None}


def _extract_srt(file_path: str) -> dict:
    """SRT 字幕：去掉序号和时间戳，保留纯文本"""
    text = _read_text_with_fallback(file_path)
    # 去掉序号行和时间戳行
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        # 跳过序号（纯数字）
        if line.isdigit():
            continue
        # 跳过时间戳行 "00:00:01,000 --> 00:00:04,000"
        if re.match(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}$", line):
            continue
        # 跳过 WEBVTT 头
        if line == "WEBVTT":
            continue
        if line:
            cleaned.append(line)
    return {"ok": True, "text": "\n".join(cleaned), "error": None}


def _extract_docx(file_path: str) -> dict:
    """Word 文档（.docx）"""
    try:
        import docx
        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return {"ok": True, "text": text, "error": None}
    except ImportError:
        return {"ok": False, "text": "", "error": "请安装 python-docx: pip install python-docx"}


def _extract_pptx(file_path: str) -> dict:
    """PowerPoint 幻灯片（.pptx）"""
    try:
        from pptx import Presentation
        prs = Presentation(file_path)
        slides_text = []
        for i, slide in enumerate(prs.slides, 1):
            slide_lines = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        t = paragraph.text.strip()
                        if t:
                            slide_lines.append(t)
            if slide_lines:
                slides_text.append(f"--- 幻灯片 {i} ---\n" + "\n".join(slide_lines))
        text = "\n\n".join(slides_text)
        return {"ok": True, "text": text, "error": None}
    except ImportError:
        return {"ok": False, "text": "", "error": "请安装 python-pptx: pip install python-pptx"}


def _extract_html(file_path: str) -> dict:
    """HTML 网页：提取标题 + meta + body 文本"""
    text = _read_text_with_fallback(file_path)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        # 去掉 script/style
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = soup.get_text(separator="\n")
        # 清理多余空行
        lines = [line.strip() for line in body_text.split("\n") if line.strip()]
        return {"ok": True, "text": "\n".join(lines), "error": None}
    except ImportError:
        # 无 BeautifulSoup，返回原始 HTML 文本
        return {"ok": True, "text": text, "error": None,
                "warning": "未安装 BeautifulSoup，HTML 标签未清理"}


def _extract_epub(file_path: str) -> dict:
    """EPUB 电子书：提取文本内容"""
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError:
        missing = []
        try:
            import ebooklib  # noqa: F811
        except ImportError:
            missing.append("ebooklib")
        try:
            from bs4 import BeautifulSoup  # noqa: F811
        except ImportError:
            missing.append("beautifulsoup4")
        return {"ok": False, "text": "",
                "error": f"请安装缺少的库: pip install {' '.join(missing)}"}

    try:
        book = epub.read_epub(file_path)
    except Exception as e:
        return {"ok": False, "text": "", "error": f"EPUB 读取失败: {e}"}

    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        try:
            soup = BeautifulSoup(item.get_content(), "html.parser")
            chapter_text = soup.get_text(separator="\n")
            lines = [line.strip() for line in chapter_text.split("\n") if line.strip()]
            if lines:
                chapters.append("\n".join(lines))
        except Exception:
            continue

    text = "\n\n".join(chapters)
    if not text:
        return {"ok": False, "text": "",
                "error": "未能从 EPUB 中提取到文本内容"}
    return {"ok": True, "text": text, "error": None}


def _extract_pdf(file_path: str) -> dict:
    """
    PDF 双路径提取:
    1. 先用 pypdf 提取文字层
    2. 文字层不足 → 标记为需要 OCR
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        # pypdf 可能叫 PyPDF2
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            return {"ok": False, "text": "",
                    "error": "请安装 pypdf: pip install pypdf"}

    try:
        reader = PdfReader(file_path)
    except Exception as e:
        return {"ok": False, "text": "", "error": f"PDF 文件无法打开: {e}"}

    # 提取所有页的文本
    pages_text = []
    for i, page in enumerate(reader.pages):
        try:
            pt = page.extract_text()
            if pt and pt.strip():
                pages_text.append(pt.strip())
        except Exception:
            continue

    text = "\n\n".join(pages_text)

    # 判断是否有足够的文字层
    # 规则：总字符数 < 100 且页数 > 1 → 可能是扫描版
    if len(text) < 100 and len(reader.pages) > 1:
        return {
            "ok": True,
            "text": text or "",
            "error": None,
            "warning": "此 PDF 文字层很少，可能是扫描版，建议使用 OCR 识别。",
            "ocr_recommended": True,
            "total_pages": len(reader.pages),
            "has_text_layer": False,
        }

    return {
        "ok": True,
        "text": text,
        "error": None,
        "total_pages": len(reader.pages),
        "has_text_layer": bool(text.strip()),
    }
