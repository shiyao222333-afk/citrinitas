"""
文件类型注册表 + 文件类型检测
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════
# 常量
# ══════════════════════════════════════

SIZE_LIMIT_MB = 50
SIZE_LIMIT_BYTES = SIZE_LIMIT_MB * 1024 * 1024

# 文件类型注册表：扩展名 → {tier, extraction_method, mime, has_auto_metadata}
FILE_TYPE_REGISTRY = {
    # ── 层级1: 自带元数据的文件 ──
    ".epub": {"tier": 1, "extraction": "epub_reader", "mime": "application/epub+zip",
              "has_auto_metadata": True},
    ".html": {"tier": 1, "extraction": "bs4", "mime": "text/html",
              "has_auto_metadata": True},
    ".htm":  {"tier": 1, "extraction": "bs4", "mime": "text/html",
              "has_auto_metadata": True},
    # ── PDF: 双路径（pypdf 优先，失败转 OCR） ──
    ".pdf":  {"tier": "auto", "extraction": "pypdf_then_ocr", "mime": "application/pdf",
              "has_auto_metadata": True},
    # ── 层级2: 有文本但无元数据 ──
    ".txt":  {"tier": 2, "extraction": "direct_read", "mime": "text/plain",
              "has_auto_metadata": False},
    ".md":   {"tier": 2, "extraction": "direct_read", "mime": "text/markdown",
              "has_auto_metadata": False},
    ".json": {"tier": 2, "extraction": "direct_read", "mime": "application/json",
              "has_auto_metadata": False},
    ".csv":  {"tier": 2, "extraction": "direct_read", "mime": "text/csv",
              "has_auto_metadata": False},
    ".srt":  {"tier": 2, "extraction": "srt_parse", "mime": "text/plain",
              "has_auto_metadata": False},
    ".docx": {"tier": 2, "extraction": "python_docx", "mime":
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              "has_auto_metadata": False},
    ".pptx": {"tier": 2, "extraction": "python_pptx", "mime":
              "application/vnd.openxmlformats-officedocument.presentationml.presentation",
              "has_auto_metadata": False},
    # ── 层级3: 图片（需 OCR） ──
    ".jpg":  {"tier": 3, "extraction": "ocr", "mime": "image/jpeg",
              "has_auto_metadata": False},
    ".jpeg": {"tier": 3, "extraction": "ocr", "mime": "image/jpeg",
              "has_auto_metadata": False},
    ".png":  {"tier": 3, "extraction": "ocr", "mime": "image/png",
              "has_auto_metadata": False},
    ".tiff": {"tier": 3, "extraction": "ocr", "mime": "image/tiff",
              "has_auto_metadata": False},
    ".bmp":  {"tier": 3, "extraction": "ocr", "mime": "image/bmp",
              "has_auto_metadata": False},
    ".webp": {"tier": 3, "extraction": "ocr", "mime": "image/webp",
              "has_auto_metadata": False},
}

# 图片文件头魔数验证
IMAGE_HEADERS = {
    b'\xff\xd8\xff': 'jpeg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'GIF8': 'gif',
    b'RIFF': 'webp',        # 需要进一步验证 WEBP 子类型
    b'BM': 'bmp',
    b'MM\x00*': 'tiff',     # Big-endian TIFF
    b'II*\x00': 'tiff',     # Little-endian TIFF
}
PDF_HEADER = b'%PDF'

# 显示名称映射
FORMAT_DISPLAY_NAMES = {
    "epub": "EPUB 电子书",
    "pdf": "PDF 文档",
    "html": "HTML 网页",
    "txt": "纯文本",
    "md": "Markdown",
    "json": "JSON",
    "csv": "CSV 表格",
    "srt": "SRT 字幕",
    "docx": "Word 文档",
    "pptx": "PowerPoint 幻灯片",
    "jpeg": "JPEG 图片",
    "png": "PNG 图片",
    "tiff": "TIFF 图片",
    "bmp": "BMP 图片",
    "webp": "WebP 图片",
}

TIER_NAMES = {
    1: "自带元数据",
    2: "纯文本（需AI标注）",
    3: "需OCR识别",
    4: "手动输入",
}


# ══════════════════════════════════════
# 文件类型检测
# ══════════════════════════════════════

def detect_file_type(file_path: str) -> dict:
    """
    检测文件类型，返回处理信息。

    Args:
        file_path: 文件路径

    Returns:
        {
            "ok": bool,
            "tier": 1|2|3|4|"auto"|None,
            "format": "epub"|"pdf"|...,
            "extraction": "epub_reader"|"direct_read"|...,
            "has_auto_metadata": bool,
            "mime": "application/pdf"|...,
            "display_name": "PDF 文档"|...,
            "tier_name": "自带元数据"|...,
            "is_supported": bool,
            "warning": str|None,       # 提示信息（如超大小）
            "error": str|None,         # 致命错误
        }
    """
    result = {
        "ok": True,
        "tier": None,
        "format": None,
        "extraction": None,
        "has_auto_metadata": False,
        "mime": None,
        "display_name": None,
        "tier_name": None,
        "is_supported": False,
        "warning": None,
        "error": None,
    }

    if not os.path.exists(file_path):
        result["ok"] = False
        result["error"] = f"文件不存在: {file_path}"
        return result

    ext = os.path.splitext(file_path)[1].lower()
    file_size = os.path.getsize(file_path)

    # 文件大小检查
    if file_size > SIZE_LIMIT_BYTES:
        result["warning"] = (
            f"文件较大（{file_size / 1024 / 1024:.1f} MB），"
            f"建议控制在 {SIZE_LIMIT_MB} MB 以内，处理可能较慢。"
        )

    # 查找注册表
    registry_entry = FILE_TYPE_REGISTRY.get(ext)
    if registry_entry is None:
        result["tier"] = 2
        result["format"] = ext.lstrip(".") if ext else "unknown"
        result["extraction"] = "direct_read_fallback"
        result["has_auto_metadata"] = False
        result["is_supported"] = False
        result["warning"] = (
            f"未识别的文件格式（{ext}），将尝试以纯文本方式读取。"
            f"支持的格式：epub, pdf, txt, md, srt, docx, pptx, html, jpg, png"
        )
        result["display_name"] = f"未知格式 ({ext})"
        result["tier_name"] = "未知"
        return result

    result.update({
        "tier": registry_entry["tier"],
        "format": ext.lstrip("."),
        "extraction": registry_entry["extraction"],
        "has_auto_metadata": registry_entry["has_auto_metadata"],
        "mime": registry_entry["mime"],
        "is_supported": True,
    })

    # 显示名称
    fmt = result["format"]
    result["display_name"] = FORMAT_DISPLAY_NAMES.get(fmt, fmt.upper())

    # 层级名称
    tier = result["tier"]
    if tier != "auto":
        result["tier_name"] = TIER_NAMES.get(tier, "未知")
    else:
        result["tier_name"] = "自动判断"

    # 内容验证：检查文件头是否与扩展名一致
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
    except Exception as e:
        result["ok"] = False
        result["error"] = f"无法读取文件: {e}"
        return result

    # PDF 头部验证
    if ext == ".pdf" and not header.startswith(PDF_HEADER):
        result["warning"] = (result["warning"] or "") + " 文件头不是有效的 PDF 签名，可能损坏。"

    # 图片头部验证
    if ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp", ".webp"):
        matched = False
        for magic, img_type in IMAGE_HEADERS.items():
            if header.startswith(magic):
                matched = True
                if ext in (".jpg", ".jpeg") and img_type != "jpeg":
                    result["warning"] = (result["warning"] or "") + f" 扩展名与文件头不匹配。"
                if ext == ".png" and img_type != "png":
                    result["warning"] = (result["warning"] or "") + f" 扩展名与文件头不匹配。"
                break
        if not matched:
            result["warning"] = (result["warning"] or "") + " 文件头不是有效图片格式，OCR 可能失败。"

    return result
