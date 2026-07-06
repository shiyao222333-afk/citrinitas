"""
File Handler — 文件类型检测 + 文本提取 + 自动元数据提取

公共 API（与旧 utils/file_handler.py 完全兼容）：
  from utils.file_handler import detect_file_type, detect_encoding, extract_text, extract_auto_metadata, merge_metadata
"""

from .registry import (
    detect_file_type,
    FILE_TYPE_REGISTRY,
    SIZE_LIMIT_MB,
    SIZE_LIMIT_BYTES,
    FORMAT_DISPLAY_NAMES,
    TIER_NAMES,
)
from .encoding import detect_encoding
from .extract import extract_text
from .metadata import extract_auto_metadata, merge_metadata

__all__ = [
    # 核心 API
    "detect_file_type",
    "detect_encoding",
    "extract_text",
    "extract_auto_metadata",
    "merge_metadata",
    # 常量（兼容旧代码可能直接引用的）
    "FILE_TYPE_REGISTRY",
    "SIZE_LIMIT_MB",
    "SIZE_LIMIT_BYTES",
    "FORMAT_DISPLAY_NAMES",
    "TIER_NAMES",
]
