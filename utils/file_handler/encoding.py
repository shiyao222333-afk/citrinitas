"""
编码检测 + 文本文件读取（带编码兜底）
"""

import os
import logging

logger = logging.getLogger(__name__)


def detect_encoding(file_path: str, sample_bytes: int = 4096) -> str:
    """
    自动检测文件编码，使用 UTF-8 → GBK → GB2312 → latin-1 兜底链。

    Args:
        file_path: 文件路径
        sample_bytes: 采样字节数（前 N 字节用于检测）

    Returns:
        编码名称，如 "utf-8", "gbk", "latin-1"
    """
    # 编码检测链（按优先级）
    encoding_chain = ["utf-8", "gbk", "gb2312", "latin-1"]

    try:
        with open(file_path, "rb") as f:
            raw = f.read(sample_bytes)
    except Exception:
        return "utf-8"  # 兜底

    # 尝试 charset_normalizer（MIT 许可，可选依赖，未安装则跳过）
    try:
        from charset_normalizer import detect as chardet_detect
        detected = chardet_detect(raw)
        if detected and detected.get("encoding"):
            enc = detected["encoding"].lower()
            # 统一常见别名
            enc_map = {
                "gb2312": "gbk", "gb18030": "gbk",
                "iso-8859-1": "latin-1", "windows-1252": "latin-1",
            }
            enc = enc_map.get(enc, enc)
            # 验证检测结果是否真能解码
            try:
                raw.decode(enc)
                return enc
            except (UnicodeDecodeError, LookupError):
                pass  # 检测不准，走兜底链
    except ImportError:
        pass  # chardet 未安装

    # 兜底链：逐个尝试
    for enc in encoding_chain:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue

    return "latin-1"  # 最终兜底（永远不会抛异常）


def _read_text_with_fallback(file_path: str) -> str:
    """使用编码检测链读取整个文本文件。"""
    enc = detect_encoding(file_path)
    with open(file_path, "r", encoding=enc, errors="replace") as f:
        return f.read()
