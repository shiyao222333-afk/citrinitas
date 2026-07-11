"""
Text Pipeline — 文本切块

去重哈希 / 图片提取 / 安全切片 / 长段落切分 / 主切块函数。
"""

import re
import hashlib

from qconst import CHUNK_MAX_CHARS, CHUNK_OVERLAP


def _text_hash(text: str) -> str:
    """内容的去重哈希（规范化后 SHA256，取前 32 位）"""
    normalized = re.sub(r'\s+', ' ', text).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def _extract_images(text: str) -> list[str]:
    """提取文本中的图片引用（支持 3 种格式：[:image:] / Markdown / HTML）。"""
    images = []
    images.extend(re.findall(r'\[image:\s*([^\]]+)\]', text))
    images.extend(re.findall(r'!\[.*?\]\(([^\)]+)\)', text))
    images.extend(re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE))
    seen = set()
    unique = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    return unique


def _safe_slice_point(text: str, target: int) -> int:
    """
    寻找安全的切片点：优先在 target 附近找标点/空格，避免切断中文。
    向前搜索 50 字符，向后搜索 50 字符。
    找不到则返回 target（允许切断）。
    """
    if target <= 0 or target >= len(text):
        return target
    start = max(0, target - 50)
    end = min(len(text), target + 50)
    punctuation = set('。！？；;,.!? \n\t')
    for i in range(target, start, -1):
        if text[i] in punctuation:
            return i + 1
    for i in range(target, end):
        if text[i] in punctuation:
            return i + 1
    for i in range(target, start, -1):
        if text[i] == ' ':
            return i + 1
    for i in range(target, end):
        if text[i] == ' ':
            return i + 1
    return target


def _split_long_paragraph(text: str, max_chars: int, overlap: int) -> list[str]:
    """将长段落按句子切分，不切断内联公式 $...$。
    超长句（>max_chars）安全切片，避免切断中文。"""
    sentences = re.split(r'(?<=[。；;])\s*', text)
    chunks = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) < max_chars:
            current = (current + sent).strip()
        else:
            if current:
                chunks.append(current)
            if len(sent) > max_chars:
                while len(sent) > max_chars:
                    cut = _safe_slice_point(sent, max_chars)
                    chunks.append(sent[:cut])
                    sent = sent[cut:].strip()
                current = sent if sent else ""
            else:
                current = sent
    if current:
        chunks.append(current)
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i-1][-overlap:] if len(chunks[i-1]) >= overlap else chunks[i-1]
            overlapped.append(prev_tail + "\n\n" + chunks[i])
        return overlapped
    return chunks


def _chunk_text(text: str, max_chars: int = None, overlap: int = None) -> list[str]:
    """
    将文本切分为重叠的块。
    保护原子结构（公式/表格/图片引用）不被截断。
    """
    if max_chars is None:
        max_chars = CHUNK_MAX_CHARS
    if overlap is None:
        overlap = CHUNK_OVERLAP
    # ── 第1步：保护原子块（替换为占位符）──
    placeholders = {}
    counter = [0]

    def _protect(match):
        key = f"__ATOMIC_{counter[0]}__"
        placeholders[key] = match.group(0)
        counter[0] += 1
        return key

    text = re.sub(r'\$\$[\s\S]*?\$\$', _protect, text)
    text = re.sub(r'(?:^\|.+\|$\n?)+', _protect, text, flags=re.MULTILINE)
    text = re.sub(r'\[image:[^\]]+\]', _protect, text)
    text = re.sub(r'\[图表\][^\n]*', _protect, text)

    # ── 第2步：正常切分 ──
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) < max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            if len(para) > max_chars:
                sub_chunks = _split_long_paragraph(para, max_chars, overlap)
                chunks.extend(sub_chunks)
                current = ""
            else:
                current = para
    if current:
        chunks.append(current)

    # ── 第3步：还原占位符 ──
    restored = []
    for chunk in chunks:
        for key, val in placeholders.items():
            chunk = chunk.replace(key, val)
        restored.append(chunk)

    return restored


def _split_into_chapters(text: str) -> list[dict]:
    """将文本按标题行切分为章节。无标题则视为单章节（index=0, title=\"\"）。

    标题识别（两种，覆盖 #22 提取阶段产出的格式）:
      - Markdown 标题: 行首 `#`~`######` 后跟标题文字
      - 中文章节惯例: 行首「第X章/卷/部/篇/节/回」

    约定: 标题行本身计入新章节首行（保留标题文字可被检索），
    同时单独存入 chapter_title 字段供 UI 展示。
    """
    heading_pat = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
    cn_chapter_pat = re.compile(r'^第[一二三四五六七八九十百千0-9]+[章卷部篇节回]\b')
    lines = text.split('\n')
    chapters = []
    cur = None
    for raw in lines:
        line = raw.strip()
        m = heading_pat.match(line)
        is_cn = bool(cn_chapter_pat.match(line))
        if m or is_cn:
            title = m.group(2).strip() if m else line
            if cur is not None:
                chapters.append(cur)
            cur = {"index": len(chapters), "title": title, "content": raw + "\n"}
        else:
            if cur is None:
                cur = {"index": 0, "title": "", "content": ""}
            cur["content"] += raw + "\n"
    if cur is not None:
        chapters.append(cur)
    # 丢弃完全空白的章节
    chapters = [c for c in chapters if c["content"].strip()]
    if not chapters:
        chapters = [{"index": 0, "title": "", "content": text}]
    return chapters


def chunk_text_with_positions(text: str, max_chars: int = None, overlap: int = None) -> list[dict]:
    """切块并记录位置指针（章节序号 / 章节标题 / 章内段序）。

    返回 list[dict]，每元素:
      {
        "text":            str,    # 块正文（供嵌入/检索）
        "chapter_index":   int,    # 第几章（从 0 起）
        "chapter_title":   str,    # 该章标题（无则空串）
        "chunk_in_chapter":int,    # 该章内第几段（从 1 起）
      }

    每章内部复用 _chunk_text 的原子保护逻辑（公式/表格/图片引用不被切断）。
    无标题文本整体视为单章，所有块 chapter_index=0、chapter_title=\"\"。
    """
    if max_chars is None:
        max_chars = CHUNK_MAX_CHARS
    if overlap is None:
        overlap = CHUNK_OVERLAP
    chapters = _split_into_chapters(text)
    result = []
    for ch in chapters:
        sub = _chunk_text(ch["content"], max_chars, overlap)
        for j, sc in enumerate(sub, 1):
            result.append({
                "text": sc,
                "chapter_index": ch["index"],
                "chapter_title": ch["title"],
                "chunk_in_chapter": j,
            })
    return result
