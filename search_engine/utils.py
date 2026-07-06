# flake8: noqa: E501
"""Search Engine 工具函数 — HTML 过滤 / 表格检测 / 去重 / 引用处理

从 search_engine.py 拆分（v1.0.2 代码质量清理）。
"""

import re
from collections import defaultdict


# ── O2 fix: 白名单标签/属性（替代黑名单，防御 XSS）──
_ALLOWED_TAGS = {
    # 结构
    "p", "br", "hr", "div", "span",
    # 标题
    "h1", "h2", "h3", "h4", "h5", "h6",
    # 文本格式
    "strong", "em", "b", "i", "u", "del", "ins", "sub", "sup", "mark",
    # 列表
    "ul", "ol", "li", "dl", "dt", "dd",
    # 代码/引用
    "code", "pre", "blockquote",
    # 表格
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    # 链接/媒体
    "a", "img",
    # 描述列表
    "details", "summary",
}

# 白名单属性（按标签）
_ALLOWED_ATTRS = {
    "*": {"class", "id", "title", "lang", "dir"},
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height", "loading"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

# 危险协议
_DANGEROUS_PROTOS = re.compile(r'(?i)\b(javascript|data)\s*:')

# 引用正则（兼容 [引用5] / [引用 5] / 引用5）
_CITATION_RE = re.compile(r'\[?引用\s*(\d+)\]?')


def _sanitize_html(text: str) -> str:
    """白名单过滤 HTML（防御 XSS）——只保留安全标签和属性。"""
    tag_pat = re.compile(r'</?([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)(/?)>')

    def _filter_tag(m: re.Match) -> str:
        tag = m.group(1).lower()
        attrs_raw = m.group(2)
        self_close = m.group(3)

        if tag not in _ALLOWED_TAGS:
            return ""

        allowed_set = _ALLOWED_ATTRS.get(tag, set()) | _ALLOWED_ATTRS["*"]
        safe_attrs = []
        if attrs_raw.strip():
            attr_pat = re.compile(r'([a-zA-Z][a-zA-Z0-9_-]*)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')
            for am in attr_pat.finditer(attrs_raw):
                aname = am.group(1).lower()
                aval = am.group(2).strip("'\"")
                if aname not in allowed_set:
                    continue
                if aname in ("href", "src") and _DANGEROUS_PROTOS.search(aval):
                    continue
                safe_attrs.append((aname, aval))

        attrs_str = " ".join(f'{k}="{v}"' for k, v in safe_attrs)
        if attrs_str:
            attrs_str = " " + attrs_str
        return f"<{tag}{attrs_str}{self_close}>"

    text = tag_pat.sub(_filter_tag, text)
    text = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', '', text, flags=re.IGNORECASE)
    text = re.sub(r"\s+on\w+\s*=\s*'[^']*'", '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', text, flags=re.IGNORECASE)
    return text


def _chunk_has_table(text: str) -> bool:
    """检测文本是否包含有效的 Markdown 管道表格。"""
    pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
    return len(pipe_lines) >= 3 and "---" in pipe_lines[1]


def _chunk_is_garbled(text: str) -> bool:
    """检测文本是否为 OCR 碎片（单字行、大量乱码）。"""
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return True
    short_count = sum(1 for l in lines if len(l.strip()) <= 3 and not any(
        c.isascii() and c.isprintable() and c not in "（）" for c in l))
    return short_count > len(lines) * 0.4


def _dedup_chunks(raw_chunks: list) -> list:
    """
    去重 + 质量过滤：
    - 同一 source 下，只要有管道表格版本，就丢弃同源的非表格版（OCR 降级碎片）
    - 同源同质量级别下，去重完全相同的文本
    - 保留原始得分排序
    """
    groups: dict[str, list] = {}
    for c in raw_chunks:
        src = c.get("source") or "未知"
        groups.setdefault(src, []).append(c)

    result = []
    for src, items in groups.items():
        tables = [c for c in items if _chunk_has_table(c["text"])]
        if tables:
            candidates = tables
        else:
            candidates = [c for c in items if not _chunk_is_garbled(c["text"])]

        if not candidates:
            continue

        seen_text = set()
        for c in sorted(candidates, key=lambda c: c.get("score", 0), reverse=True):
            key = c["text"].strip()
            if key not in seen_text:
                seen_text.add(key)
                result.append(c)

    result.sort(key=lambda c: c.get("score", 0), reverse=True)
    return result
