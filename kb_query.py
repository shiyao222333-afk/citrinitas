"""
KB Query Engine - 中文技术文档知识库问答系统
版本: v0.4.6 — AI分析确认卡片 + 元数据预填

架构:
  摄入: 图片/文本 → PaddleOCR/PPStructureV3 → 分块嵌入 → Qdrant
  查询: 自然语言 → 向量搜索 → LLM API合成 → 程序渲染HTML/PDF

用法:
  # 问答（端到端：搜索 → API合成 → HTML报告 → PDF）
  python kb_query.py "齿轮的失效形式有哪些" --answer
  
  # 纯搜索（不调用 LLM）
  python kb_query.py "齿轮的失效形式有哪些" --top 10
  
  # 摄入文档
  python kb_query.py --ingest "D:/Documents/KnowledgeBase/机械设计/原始文件/齿轮设计基础.txt"
  
  # OCR 图片（方案B：OCR → 质量检查 → WorkBuddy审核 → 入库）
  python kb_query.py --ocr "photo.jpg" --source "手册-P3"
  python kb_query.py --ocr "photo.jpg" --check-only          # 只识别不入库，先审核
  python kb_query.py --ocr "photo.jpg" --engine structured  # PPStructureV3 结构化识别（公式+表格+图表）

环境变量（问答模式需配置 API）:
  KB_LLM_BASE_URL    LLM API 地址（默认 https://api.deepseek.com/v1）
  KB_LLM_API_KEY      API Key（需自行申请）
  KB_LLM_MODEL        模型名（默认 deepseek-chat）
"""
import requests
import json
import sys
import os
import argparse
import re
import subprocess
import io
import base64
import math
from typing import Optional
from collections import defaultdict
import hashlib
import uuid
from datetime import datetime, timezone
import tempfile
from docx import Document
from bs4 import BeautifulSoup
from config.classifications import normalize_facet_values

__version__ = "0.4.5"

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except ImportError:
    FPDF = None
    XPos = None
    YPos = None

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    PILImage = None
    HAS_PIL = False

# 图片存储目录
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "images")
# 摄入日志（每行一条 JSON，记录原始文件路径和集合，用于重建）
INGEST_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "ingest_log.jsonl")

# Tesseract 备选（可通过环境变量覆盖）
_TESSERACT_FALLBACK = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT = os.environ.get("KB_TESSERACT_PATH") or _TESSERACT_FALLBACK
os.environ.setdefault("TESSDATA_PREFIX", os.environ.get("KB_TESSDATA_PREFIX") or r"D:\Tesseract-OCR\tessdata")

# PaddleOCR 主力引擎（延迟初始化）
_paddle_ocr = None

OLLAMA_URL = "http://localhost:11434"
QDRANT_URL = os.environ.get("KB_QDRANT_URL", "http://127.0.0.1:6333")
EMBED_MODEL = os.environ.get("KB_EMBED_MODEL", "qwen3-embedding:4b")   # 主力：qwen3-embedding 2560维 40K上下文
EMBED_DIM = 2560                       # qwen3-embedding:4b 输出维度
DEFAULT_COLLECTION = "athanor_v1"   # 2560维 Qdrant 集合（分面分类单集合方案）

# 引用粒度：表格行数 > 此值时按行拆分为独立引用（--table-split-threshold 可覆盖）
TABLE_SPLIT_THRESHOLD = 4


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _get_paddle():
    """延迟初始化 PaddleOCR（首次调用才加载模型）"""
    global _paddle_ocr
    if _paddle_ocr is None:
        try:
            from paddleocr import PaddleOCR
            # PaddleOCR 3.7+: use_textline_orientation 替代 use_angle_cls
            # PP-OCRv4 兼容 paddlepaddle 3.0.0 (PP-OCRv6 需要 3.3.x 但有 Windows oneDNN bug)
            _paddle_ocr = PaddleOCR(lang='ch', ocr_version='PP-OCRv4', use_textline_orientation=True)
        except ImportError:
            raise ImportError(
                "PaddleOCR 未安装。运行: "
                "D:/uv/tools/private-gpt/Scripts/python.exe -m pip install paddlepaddle paddleocr"
            )
    return _paddle_ocr


def _ocr_paddle(image_path: str) -> dict:
    """
    PaddleOCR 识别（主力引擎，中文+公式优化）
    返回: {"ok": true, "text": "...", "chars": N, "conf": 0.95, "raw": [...]}
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")
    
    engine = _get_paddle()
    # PaddleOCR 3.7+: 使用 predict() 方法，返回 list[dict]
    result = engine.predict(image_path)
    
    if not result or not isinstance(result, list) or not result[0]:
        return {"ok": True, "text": "", "chars": 0, "conf": 0.0, "raw": []}
    
    page = result[0]
    # PaddleOCR 3.7 predict() 返回格式：{rec_texts: [...], rec_scores: [...], ...}
    texts = page.get('rec_texts', [])
    scores = page.get('rec_scores', [])
    
    lines = []
    confs = []
    for i, text in enumerate(texts):
        text = text.strip()
        if text:
            lines.append(text)
            conf = scores[i] if i < len(scores) else 0.0
            confs.append(float(conf))
    
    full_text = "\n".join(lines)
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    
    return {
        "ok": True,
        "text": full_text,
        "chars": len(full_text),
        "conf": round(float(avg_conf), 4),
        "lines": len(lines),
        "raw": [{"text": t, "conf": c} for t, c in zip(lines, confs)]
    }


def _ocr_tesseract(image_path: str, lang: str = "chi_sim+eng") -> dict:
    """
    Tesseract OCR（备选引擎）
    返回: {"ok": true, "text": "...", "chars": N, "conf": null}
    """
    if not os.path.exists(TESSERACT):
        raise FileNotFoundError(f"Tesseract 未找到: {TESSERACT}")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")
    
    outbase = image_path + "_ocr_tmp"
    result = subprocess.run(
        [TESSERACT, image_path, outbase, "-l", lang, "--psm", "6"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"Tesseract 失败: {result.stderr.strip()}")
    
    txt_path = outbase + ".txt"
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    os.remove(txt_path)
    
    return {
        "ok": True,
        "text": text,
        "chars": len(text),
        "conf": None,  # Tesseract batch 模式不返回置信度
        "lines": text.count("\n") + 1,
        "raw": []
    }


# PPStructureV3 引擎（延迟初始化）
_structure_engine = None


def _get_structure_engine():
    """延迟初始化 PPStructureV3（首次调用才加载模型）"""
    global _structure_engine
    if _structure_engine is None:
        try:
            from paddleocr import PPStructureV3
            _structure_engine = PPStructureV3(
                lang='ch',
                use_formula_recognition=True,
                use_table_recognition=True,
                use_chart_recognition=False,  # PP-Chart2Table 模型下载/加载极慢，暂关闭；layout 模型仍能检测 figure 区域
                format_block_content=True,
            )
        except ImportError as e:
            raise ImportError(
                f"PPStructureV3 初始化失败: {e}\n"
                f"请确保 paddlex[ocr] 已安装：\n"
                f"  D:/uv/tools/private-gpt/Scripts/python.exe -m pip install 'paddlex[ocr]==3.7.0'"
            )
    return _structure_engine


def _html_table_to_markdown(html_text: str) -> str:
    """将 HTML <table> 转换为 Markdown 表格（简化版，处理 PPStructureV3 输出）"""

    def _convert_table(match):
        table_html = match.group(0)
        rows = re.findall(r'<tr>(.*?)</tr>', table_html, re.DOTALL)
        md_rows = []
        for row_idx, row in enumerate(rows):
            cells = re.findall(r'<(?:td|th).*?>(.*?)</(?:td|th)>', row, re.DOTALL | re.IGNORECASE)
            # 清理单元格内的 HTML 标签（保留 $...$ 和图片标记）
            clean_cells = []
            for c in cells:
                c = re.sub(r'<img\s+src="([^"]+)"[^>]*>', r'[image: \1]', c)
                c = re.sub(r'<div[^>]*>', ' ', c)
                c = re.sub(r'</div>', '', c)
                c = re.sub(r'<[^>]+>', '', c)
                c = c.strip()
                # 管道符需要转义
                c = c.replace('|', '\\|')
                clean_cells.append(c)
            md_rows.append('| ' + ' | '.join(clean_cells) + ' |')
            if row_idx == 0:
                md_rows.append('|' + '|'.join([' --- ' for _ in clean_cells]) + '|')
        return '\n'.join(md_rows)

    html_text = re.sub(r'(?:<div[^>]*>\s*)?<html><body>\s*<table[^>]*>.*?</table>\s*</body></html>\s*(?:</div>)?',
                        _convert_table, html_text, flags=re.DOTALL)
    return html_text


def _ocr_structured(image_path: str) -> dict:
    """
    PPStructureV3 结构化识别（主力引擎）
    自动检测版面区域：文字/公式/表格/图表，分别用最优方式处理。

    PPStructureV3.predict() 返回 list[LayoutParsingResultV2]。
    使用内置 _to_markdown() 获取统一 Markdown，包含：
      - HTML 表格 → 转为 Markdown 表格
      - 内嵌 LaTeX 公式 ($...$)
      - <img> 图片引用 → 保存为 [image: path]

    返回: {
        "ok": true,
        "text": "...",
        "chars": N,
        "blocks": [...],
        "images": [...],
        "conf": 0.95,
    }
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"图片不存在: {image_path}")

    engine = _get_structure_engine()

    try:
        pages = engine.predict(image_path)
    except Exception as e:
        return {"ok": False, "error": f"PPStructureV3 识别失败: {e}"}

    if not pages:
        return {"ok": True, "text": "", "chars": 0, "blocks": [], "images": [], "conf": 0.0}

    all_text_parts = []
    all_images = []
    block_summary = []

    for page_idx, page in enumerate(pages):
        # ── LayoutParsingResultV2 对象 ──
        # 使用内置 _to_markdown() 获取格式化输出
        try:
            md_result = page._to_markdown(pretty=True, show_formula_number=False)
        except Exception:
            # 回退：手动拼接 layout blocks
            layout_blocks = page.get('parsing_res_list', [])
            page_text = _assemble_blocks_v2(layout_blocks, page_idx, all_images, image_path, page)
            all_text_parts.append(page_text)
            block_summary.append({"page": page_idx, "type": "fallback", "length": len(page_text)})
            continue

        md_text = md_result.get('markdown_texts', '')
        if not md_text:
            continue

        # ── 1. 收集并保存图片 ──
        # markdown 中图片以 <img src="imgs/...jpg"> 形式存在
        # 从 page.get('imgs_in_doc') 获取 PIL Image 对象，保存到 local_data/images/
        path_to_pil = {}
        imgs_in_doc = page.get('imgs_in_doc', [])
        for img_item in imgs_in_doc:
            if isinstance(img_item, dict):
                p = img_item.get('path', '')
                pil = img_item.get('img')
                if p and pil:
                    path_to_pil[p] = pil

        def _replace_img(match):
            src = match.group(1)
            _ensure_images_dir()
            dest_name = f"fig_p{page_idx}_{len(all_images)}.png"
            dest_path = os.path.join(IMAGES_DIR, dest_name)
            if src in path_to_pil:
                path_to_pil[src].save(dest_path)
            all_images.append(dest_path)
            return f"\n[image: {dest_path}]\n"

        md_text = re.sub(
            r'(?:<div[^>]*>\s*)?<img\s+src="([^"]+)"[^>]*>(?:\s*</div>)?',
            _replace_img, md_text
        )

        # ── 2. 转换 HTML 表格为 Markdown 表格 ──
        md_text = _html_table_to_markdown(md_text)

        # ── 3. 清理残余 HTML 标签 ──
        md_text = re.sub(r'<div[^>]*>', '\n', md_text)
        md_text = re.sub(r'</div>', '', md_text)
        md_text = re.sub(r'<html><body>', '', md_text)
        md_text = re.sub(r'</body></html>', '', md_text)
        # 清理连续空行
        md_text = re.sub(r'\n{3,}', '\n\n', md_text)

        all_text_parts.append(md_text.strip())
        block_summary.append({"page": page_idx, "type": "structured", "length": len(md_text)})

    full_text = "\n\n".join(all_text_parts)

    return {
        "ok": True,
        "text": full_text,
        "chars": len(full_text),
        "blocks": block_summary,
        "images": all_images,
        "conf": 0.95,
    }


def _assemble_blocks_v2(blocks: list, page_idx: int, image_list: list, source_image: str, page) -> str:
    """
    手动拼装 PPStructureV3 LayoutBlocks（_to_markdown 失败时的回退路径）。
    blocks 是 LayoutBlock 对象列表（label/content/bbox）。
    """
    if not blocks:
        return ""

    parts = []
    for b in blocks:
        label = getattr(b, 'label', 'text')
        content = getattr(b, 'content', '') or ''
        content = str(content)

        if label == 'table':
            parts.append(f"\n[表格] {content}\n")
        elif label in ('figure', 'figure_title', 'image'):
            # 尝试从 imgs_in_doc 匹配裁剪图
            imgs = page.get('imgs_in_doc', [])
            if imgs and hasattr(b, 'bbox'):
                bbox = b.bbox
                for img_item in imgs:
                    if isinstance(img_item, dict) and 'coordinate' in img_item:
                        coord = img_item['coordinate']
                        # 粗略匹配 bbox 和 coordinate
                        if (abs(bbox[0] - coord[0]) < 30 and abs(bbox[1] - coord[1]) < 30):
                            pil = img_item.get('img')
                            if pil:
                                _ensure_images_dir()
                                dest_name = f"fig_p{page_idx}_{len(image_list)}.png"
                                dest_path = os.path.join(IMAGES_DIR, dest_name)
                                pil.save(dest_path)
                                image_list.append(dest_path)
                                parts.append(f"[image: {dest_path}]")
                            break
            if not parts or parts[-1].startswith('[image') is False:
                parts.append(f"[图表] {content}")
        elif label == 'formula':
            content = content.strip()
            if content and not content.startswith('$$'):
                content = f"$${content}$$"
            parts.append(content)
        else:
            if content.strip():
                parts.append(content.strip())

    return "\n".join(parts)


def _check_ocr_quality(ocr_result: dict, image_path: str = None) -> dict:
    """
    检查 OCR 识别质量。
    
    检测信号:
    - 中文占比 < 10% → 可能图片模糊/纯英文/非文档
    - 字符数过少 → 可能图片模糊
    - 重复乱码 → 图片质量差
    - 平均置信度低 → RapidOCR 不确定
    
    返回: {"grade": "good|warn|bad", "score": 0-100, "issues": [...], "suggestion": "..."}
    """
    text = ocr_result.get("text", "")
    conf = ocr_result.get("conf")
    issues = []
    
    # 1. 中文占比
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    total_chars = len(text.strip())
    cjk_ratio = cjk_chars / max(total_chars, 1)
    
    if total_chars < 3:
        issues.append("识别文字过少（<3字符）")
    elif total_chars < 20:
        issues.append(f"识别文字较少（{total_chars}字符），可能图片模糊")
    
    if cjk_ratio < 0.05 and total_chars > 10:
        issues.append(f"中文占比极低（{cjk_ratio:.1%}），确认是否中文文档")
    
    # 2. 乱码检测（连续非打印字符）
    garbled = re.findall(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]{3,}', text)
    if garbled:
        issues.append("检测到乱码字符")
    
    # 3. 置信度
    if conf is not None:
        if conf < 0.5:
            issues.append(f"平均置信度低（{conf:.2f}），OCR 不确定")
        elif conf < 0.7:
            issues.append(f"平均置信度偏低（{conf:.2f}）")
    
    # 评分
    if not issues:
        score = 90
        grade = "good"
    elif len(issues) == 1 and ("偏低" in issues[0] or "较少" in issues[0]):
        score = 65
        grade = "warn"
    else:
        score = 30
        grade = "bad"
    
    return {
        "grade": grade,
        "score": score,
        "chars": total_chars,
        "cjk_ratio": round(cjk_ratio, 3),
        "issues": issues,
        "suggestion": "可直接入库" if grade == "good"
                       else "建议人工审核后入库" if grade == "warn"
                       else "图片可能模糊或非中文文档，建议重新拍摄"
    }

def ocr_image(image_path: str) -> dict:
    """
    公共 OCR 入口：自动选择最优引擎识别图片文字。

    优先使用 PPStructureV3（结构化识别：文字+表格+公式），
    回退到 PaddleOCR（基础文字识别）。

    返回:
        {
            "ok": true,
            "ocr_text": "识别出的文字...",
            "text": "识别出的文字...",
            "chars": N,
            "conf": 0.95,
            "needs_correction": false,
            "quality": {...}    # 质量评估结果
        }
    """
    if not os.path.exists(image_path):
        return {"ok": False, "error": f"图片不存在: {image_path}"}

    # 优先尝试 PPStructureV3
    try:
        result = _ocr_structured(image_path)
        if result.get("ok") and result.get("text"):
            quality = _check_ocr_quality(result, image_path)
            return {
                "ok": True,
                "ocr_text": result.get("text", ""),
                "text": result.get("text", ""),
                "chars": result.get("chars", len(result.get("text", ""))),
                "conf": result.get("conf", 0.0),
                "needs_correction": quality.get("grade") != "good",
                "quality": quality,
            }
    except Exception:
        pass  # 回退到 PaddleOCR

    # 回退到 PaddleOCR
    try:
        result = _ocr_paddle(image_path)
        if result.get("ok"):
            quality = _check_ocr_quality(result, image_path)
            return {
                "ok": True,
                "ocr_text": result.get("text", ""),
                "text": result.get("text", ""),
                "chars": result.get("chars", len(result.get("text", ""))),
                "conf": result.get("conf", 0.0),
                "needs_correction": quality.get("grade") != "good",
                "quality": quality,
            }
    except Exception as e:
        return {"ok": False, "error": f"OCR 引擎初始化失败: {e}"}

    return {"ok": False, "error": "无法加载任何 OCR 引擎"}

def extract_text(file_path: str) -> dict:
    """
    统一文本提取入口：根据文件扩展名调用对应解析器。
    
    支持格式：
      - .txt / .md / .json / .csv → 直接读取（自动检测编码）
      - .docx → python-docx 提取文本
      - .html / .htm → BeautifulSoup 提取文本（去除标签）
      - .srt → 解析 SRT 字幕格式（去除时间戳）
      - .pdf → 尝试 pdfplumber 提取文本
    
    返回:
        {"ok": True, "text": "...", "chars": N, "meta": {}}
        {"ok": False, "error": "..."}
    """
    if not os.path.exists(file_path):
        return {"ok": False, "error": f"文件不存在: {file_path}"}
    
    ext = os.path.splitext(file_path)[1].lower()
    
    # ── 纯文本格式：直接读取 ──
    if ext in (".txt", ".md", ".json", ".csv", ".log"):
        encoding = detect_encoding(file_path)
        try:
            with open(file_path, "r", encoding=encoding) as f:
                text = f.read()
            return {"ok": True, "text": text, "chars": len(text), "meta": {"encoding": encoding}}
        except Exception as e:
            return {"ok": False, "error": f"读取文件失败: {e}"}
    
    # ── DOCX 格式 ──
    if ext == ".docx":
        try:
            doc = Document(file_path)
            parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    parts.append(para.text)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            parts.append(cell.text)
            text = "\n\n".join(parts)
            return {"ok": True, "text": text, "chars": len(text), "meta": {"format": "docx"}}
        except Exception as e:
            return {"ok": False, "error": f"解析 DOCX 失败: {e}"}
    
    # ── HTML 格式 ──
    if ext in (".html", ".htm"):
        try:
            with open(file_path, "r", encoding=detect_encoding(file_path)) as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            return {"ok": True, "text": text, "chars": len(text), "meta": {"format": "html"}}
        except Exception as e:
            return {"ok": False, "error": f"解析 HTML 失败: {e}"}
    
    # ── SRT 字幕格式 ──
    if ext == ".srt":
        try:
            encoding = detect_encoding(file_path)
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            lines = []
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.isdigit():
                    continue
                if "-->" in line:
                    continue
                lines.append(line)
            text = "\n".join(lines)
            return {"ok": True, "text": text, "chars": len(text), "meta": {"format": "srt", "encoding": encoding}}
        except Exception as e:
            return {"ok": False, "error": f"解析 SRT 失败: {e}"}
    
    # ── PDF 格式 ──
    if ext == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        parts.append(page_text)
                text = "\n\n".join(parts)
            if not text.strip():
                return {"ok": False, "error": "PDF 无文本内容（可能是扫描件，需要 OCR）"}
            return {"ok": True, "text": text, "chars": len(text), "meta": {"format": "pdf", "pages": len(pdf.pages)}}
        except ImportError:
            return {"ok": False, "error": "需要安装 pdfplumber：pip install pdfplumber"}
        except Exception as e:
            return {"ok": False, "error": f"解析 PDF 失败: {e}"}
    
    # ── 不支持的格式 ──
    return {"ok": False, "error": f"不支持的文件格式: {ext}"}

def _embed(texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    """调用 Ollama 批量获取嵌入向量（优先批量，失败回退逐条）。单条查询失败 → 抛异常，批量摄入失败 → 跳过。"""
    if not texts:
        return []
    # 尝试批量 API（Ollama /api/embed 支持 input 数组）
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": model, "input": texts},
            timeout=120
        )
        resp.raise_for_status()
        embeddings = resp.json().get("embeddings", [])
        if embeddings and len(embeddings) == len(texts):
            return embeddings
    except Exception:
        pass  # 回退到逐条
    # 逐条回退 — 单条查询失败抛异常，批量摄入失败跳过
    vectors = []
    for i, text in enumerate(texts):
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
        except Exception:
            if len(texts) == 1:
                raise  # 单条查询：必须传播错误
            print(f"  [WARN] 块 #{i} 嵌入失败（{len(text)} 字符），已跳过")
    return vectors


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


def detect_encoding(file_path: str, sample_size: int = 10000) -> str:
    """
    检测文件编码。优先 chardet，失败后用 UTF-8 → GBK → latin-1 兜底链。
    sample_size: 用于检测的字节数（默认 10000，约 10KB）
    """
    # 读取文件前 N 字节作为样本
    with open(file_path, "rb") as f:
        raw = f.read(sample_size)
    if not raw:
        return "utf-8"  # 空文件，默认 UTF-8

    # 先试 chardet（如果已安装）
    try:
        import chardet
        result = chardet.detect(raw)
        enc = result.get("encoding", "").strip().lower()
        conf = result.get("confidence", 0)
        if enc and conf >= 0.6:
            # chardet 可能返回 "utf-8"、"gb2312"、"gbk"、"iso-8859-1" 等
            # 统一映射到 Python 编码名
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


def _check_qdrant() -> bool:
    """检查 Qdrant 是否运行（纯检查，无副作用）。"""
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def _ensure_collection(collection: str) -> bool:
    """确保指定集合存在，不存在则自动创建。"""
    if not _check_qdrant():
        return False
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        names = [c["name"] for c in resp.json()["result"]["collections"]]
        if collection not in names:
            requests.put(
                f"{QDRANT_URL}/collections/{collection}",
                json={"vectors": {"size": EMBED_DIM, "distance": "Cosine"}},
                timeout=10
            )
            # ── 创建 Payload Index（分面字段 + 常用过滤字段）──
            payload_index_fields = {
                "content_type":     "keyword",
                "domain":          "keyword",  # list of keywords
                "temporal_nature": "keyword",
                "epistemic_status": "keyword",
                "lifecycle":       "keyword",
                "is_personal":     "bool",
                "trust_score":      "integer",
                "knowledge_type":   "keyword",
                "language":        "keyword",
                "access_level":     "keyword",
            }
            for field, schema in payload_index_fields.items():
                try:
                    requests.put(
                        f"{QDRANT_URL}/collections/{collection}/index",
                        json={"field_name": field, "field_schema": schema},
                        timeout=5
                    )
                except Exception:
                    pass  # 索引已存在或创建失败，不影响主流程
        return True
    except Exception:
        return False


def create_collection(collection: str) -> dict:
    """
    创建新的知识库集合。如果集合已存在则报错。

    返回:
        {"ok": true, "collection": "...", "dim": N}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        existing = [c["name"] for c in resp.json()["result"]["collections"]]
        if collection in existing:
            return {"ok": False, "error": f"集合「{collection}」已存在"}
        requests.put(
            f"{QDRANT_URL}/collections/{collection}",
            json={"vectors": {"size": EMBED_DIM, "distance": "Cosine"}},
            timeout=10
        )
        return {"ok": True, "collection": collection, "dim": EMBED_DIM}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_collections() -> dict:
    """
    列出所有 Qdrant 知识库集合。

    返回:
        {"ok": true, "collections": [{"name": "...", "points": N, "dim": N}, ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}
    try:
        resp = requests.get(f"{QDRANT_URL}/collections", timeout=5)
        resp.raise_for_status()
        all_cols = resp.json()["result"]["collections"]
        result = []
        for c in all_cols:
            name = c["name"]
            try:
                info = requests.get(f"{QDRANT_URL}/collections/{name}", timeout=5).json()
                cfg = info.get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
                pts = info.get("result", {}).get("points_count", 0)
                result.append({
                    "name": name,
                    "points": pts,
                    "dim": cfg.get("size", "?") if cfg else "?",
                })
            except Exception:
                result.append({"name": name, "points": "?", "dim": "?"})
        return {"ok": True, "collections": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def clear_collection(collection: str = DEFAULT_COLLECTION) -> dict:
    """
    清空指定知识库集合（删除所有向量点，但保留集合结构）。

    参数:
        collection: 集合名称

    返回:
        {"ok": true, "deleted": N, "collection": "..."}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}
    try:
        # 获取当前点数
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5).json()
        points_count = info.get("result", {}).get("points_count", 0)

        if points_count == 0:
            return {"ok": True, "deleted": 0, "collection": collection, "message": "集合已为空"}

        # 分批删除所有点（scroll + delete）
        deleted_total = 0
        while True:
            scroll_resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": 1000, "with_payload": False, "with_vector": False},
                timeout=30
            )
            scroll_resp.raise_for_status()
            points = scroll_resp.json()["result"].get("points", [])
            if not points:
                break
            ids = [p["id"] for p in points]
            del_resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/delete",
                json={"points": ids},
                timeout=30
            )
            del_resp.raise_for_status()
            deleted_total += len(ids)

        return {"ok": True, "deleted": deleted_total, "collection": collection}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_collection(collection: str) -> dict:
    """
    完全删除一个知识库集合（包括集合结构）。

    参数:
        collection: 集合名称

    返回:
        {"ok": true, "collection": "..."}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}
    try:
        resp = requests.delete(f"{QDRANT_URL}/collections/{collection}", timeout=10)
        resp.raise_for_status()
        return {"ok": True, "collection": collection, "message": "集合已删除"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_embed_models() -> list[str]:
    """
    从 Ollama 获取本地可用的嵌入模型列表。

    返回:
        ["qwen3-embedding:4b", ...] 或空列表
    """
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # 常见嵌入模型关键词
        embed_keywords = ["embed", "e5", "bge", "gte", "jina"]
        models = []
        for m in data.get("models", []):
            name = m.get("name", "").lower()
            # 嵌入模型通常包含这些关键词，或者直接返回所有模型让用户选
            models.append(m["name"])
        return models
    except Exception:
        return []


# TODO: 函数 has_any_data 已废弃（无人调用），将在 v0.5.0 删除
def has_any_data() -> bool:
    """
    检查任意 Qdrant 集合中是否有数据（用于判断是否锁定分类法/嵌入模型选择）。
    """
    try:
        col_list = list_collections()
        if not col_list.get("ok"):
            return False
        for c in col_list.get("collections", []):
            if c.get("points", 0) > 0:
                return True
        return False
    except Exception:
        return False


# ═══════════════════════════════════════════
# 摄入日志（ingest_log.jsonl）
# 每行一条 JSON 记录，用于知识库重建
# ═══════════════════════════════════════════

def _log_ingest(entry: dict):
    """
    摄入成功后写一行日志到 ingest_log.jsonl。
    entry 格式:
    {
        "source_file": "D:/data/齿轮设计.txt",   # 原始文件路径（绝对路径）
        "source_text": null,                    # 手动输入时为文本内容（前 500 字）
        "collection": "TH",
        "doc_id": "a1b2c3d4",
        "content_hash": "f3e8a...",
        "embed_model": "qwen3-embedding:4b",
        "ingested_at": "2026-06-14T12:00:00Z"
    }
    """
    try:
        os.makedirs(os.path.dirname(INGEST_LOG_PATH), exist_ok=True)
        with open(INGEST_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 日志写入失败不影响主流程


# TODO: 函数 read_ingest_log 已废弃（无人调用），将在 v0.5.0 删除
def read_ingest_log() -> list[dict]:
    """
    读取摄入日志，返回所有记录列表。
    如果文件不存在或格式错误，返回空列表。
    """
    if not os.path.isfile(INGEST_LOG_PATH):
        return []
    entries = []
    try:
        with open(INGEST_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
        return entries
    except Exception:
        return []


# TODO: 函数 search_multi 已废弃（无人调用），将在 v0.5.0 删除
def search_multi(
    query: str,
    collections: list[str] = None,
    top_k: int = 5,
    score_threshold: float = 0.3,
    model: str = None,
) -> dict:
    """
    跨多个集合搜索，合并后用 z-score 归一化重排。

    参数:
        query: 搜索问题
        collections: 要搜索的集合列表，None 表示搜所有非空集合
        top_k: 每个集合取 top_k，合并后最终返回 top_k
        score_threshold: 最低相似度阈值
        model: 嵌入模型（默认用 EMBED_MODEL）

    返回:
        {
            "ok": true/false,
            "query": "...",
            "total": 合并后总数,
            "chunks": [...],           # 已按归一化分数重排
            "per_collection": {...}      # 每个集合的原始结果数
        }
    """
    if model is None:
        model = EMBED_MODEL

    # 确定要搜索的集合
    if collections is None:
        col_list = list_collections()
        if not col_list.get("ok"):
            return {"ok": False, "error": "无法列出集合"}
        collections = [c["name"] for c in col_list.get("collections", [])]

    if not collections:
        return {"ok": True, "query": query, "total": 0, "chunks": []}

    # 嵌入查询
    try:
        query_vec = _embed([query], model=model)[0]
    except Exception as e:
        return {"ok": False, "error": f"嵌入查询失败: {e}"}

    # 并行搜索所有集合（收集原始分数用于归一化）
    all_raw = []  # [(chunk_dict, original_score, collection_name)]
    per_col = {}

    for col in collections:
        try:
            resp = requests.post(
                f"{QDRANT_URL}/collections/{col}/points/search",
                json={
                    "vector": query_vec,
                    "limit": top_k,
                    "with_payload": True,
                    "score_threshold": score_threshold
                },
                timeout=30
            )
            resp.raise_for_status()
            results = resp.json()["result"]
            per_col[col] = len(results)

            for r in results:
                payload = r.get("payload", {})
                all_raw.append((
                    {
                        "text":            payload.get("text", ""),
                        "title":           payload.get("title", ""),
                        "source":          payload.get("source", "未知"),
                        "score":           round(r.get("score", 0), 4),
                        "chunk_index":     payload.get("chunk_index", 0),
                        "doc_id":          payload.get("doc_id", ""),
                        "images":          payload.get("images", []),
                        # v4.0 分面字段
                        "content_type":    payload.get("content_type", "knowledge"),
                        "domain":          payload.get("domain", []),
                        "lifecycle":       payload.get("lifecycle", ""),
                        "trust_score":     payload.get("trust_score", 3),
                        "keywords":        payload.get("keywords", []),
                        "relations":       payload.get("relations", []),
                        "timeline":        payload.get("timeline", {}),
                        "origin":          payload.get("origin", {}),
                        "_collection":     col,          # 标记来源集合
                    },
                    r.get("score", 0),              # 原始分数（用于归一化）
                    col
                ))
        except Exception:
            per_col[col] = 0

    if not all_raw:
        return {"ok": True, "query": query, "total": 0, "chunks": [], "per_collection": per_col}

    # z-score 归一化（每个集合内单独计算）
    # 分组：{col_name: [(chunk, raw_score)]}
    col_groups = defaultdict(list)
    for chunk, raw_score, col in all_raw:
        col_groups[col].append((chunk, raw_score))

    normalized = []
    for col, items in col_groups.items():
        scores = [s for _, s in items]
        if len(scores) <= 1:
            # 只有一个结果，无法计算标准差，直接用原始分数
            for chunk, s in items:
                chunk["score_normalized"] = round(s, 4)
                normalized.append(chunk)
            continue
        mean_s = sum(scores) / len(scores)
        std_s = (sum((s - mean_s) ** 2 for s in scores) / len(scores)) ** 0.5
        if std_s < 1e-9:
            # 分数几乎相同，归一化无意义
            for chunk, s in items:
                chunk["score_normalized"] = round(s, 4)
                normalized.append(chunk)
            continue
        for chunk, s in items:
            z = (s - mean_s) / std_s
            # 把 z-score 压缩到 0~1 范围（sigmoid 变换）
            norm = 1 / (1 + math.exp(-z))
            chunk["score_normalized"] = round(norm, 4)
            normalized.append(chunk)

    # 按归一化分数降序排列
    normalized.sort(key=lambda x: x["score_normalized"], reverse=True)

    # 取 top_k
    top = normalized[:top_k]
    for t in top:
        t["score"] = t.pop("score_normalized")   # 用归一化分数替换原始分数

    return {
        "ok": True,
        "query": query,
        "total": len(top),
        "chunks": top,
        "per_collection": per_col,
    }


# TODO: 函数 rebuild_from_log 已废弃（无人调用），将在 v0.5.0 删除
def rebuild_from_log(
    target_collections: list[str] = None,
    progress_callback=None,
) -> dict:
    """
    从摄入日志读取原始文件，用当前嵌入模型重新摄入到目标集合。

    参数:
        target_collections: 要重建的集合列表，None 表示重建日志中出现的所有集合
        progress_callback: 进度回调函数 callback(current, total, message)

    返回:
        {"ok": true, "rebuilt": N, "skipped": N, "errors": [...]}
    """
    entries = read_ingest_log()
    if not entries:
        return {"ok": False, "error": "摄入日志为空，无法重建"}

    total = len(entries)
    rebuilt = 0
    skipped = 0
    errors = []

    for i, entry in enumerate(entries):
        if progress_callback:
            progress_callback(i, total, f"处理 {entry.get('source_file', '未知文件')[:50]}...")

        src = entry.get("source_file", "")
        collection = entry.get("collection", DEFAULT_COLLECTION)
        doc_id = entry.get("doc_id", "")

        # 检查目标集合（如果指定了）
        if target_collections and collection not in target_collections:
            skipped += 1
            continue

        # 尝试从原始文件重新摄入
        if src and os.path.isfile(src):
            try:
                result = ingest(
                    file_path=src,
                    metadata={"source": os.path.basename(src), "doc_id": doc_id},
                    collection=collection,
                    skip_duplicates=True,
                )
                if result.get("ok"):
                    rebuilt += 1
                elif "重复" in result.get("error", ""):
                    skipped += 1   # 已存在，跳过
                else:
                    errors.append(f"{src}: {result.get('error', '')}")
            except Exception as e:
                errors.append(f"{src}: {e}")
        elif entry.get("source_text"):
            # 手动输入的文本，用日志里保存的片段重新摄入
            try:
                result = ingest(
                    text=entry["source_text"],
                    metadata={"source": "手动输入（重建）", "doc_id": doc_id},
                    collection=collection,
                    skip_duplicates=True,
                )
                if result.get("ok"):
                    rebuilt += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"手动输入({doc_id}): {e}")
        else:
            errors.append(f"{src}: 原始文件不存在，且无法从日志恢复文本内容")
            skipped += 1

    if progress_callback:
        progress_callback(total, total, "重建完成")

    return {
        "ok": True,
        "rebuilt": rebuilt,
        "skipped": skipped,
        "errors": errors,
        "total_entries": total,
    }


def _text_hash(text: str) -> str:
    """内容的去重哈希（规范化后 SHA256，取前 16 位）"""
    normalized = re.sub(r'\s+', ' ', text).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _extract_images(text: str) -> list[str]:
    """提取文本中的图片引用（支持 3 种格式：[:image:] / Markdown / HTML）。"""
    images = []
    # 格式1: [image: path]
    images.extend(re.findall(r'\[image:\s*([^\]]+)\]', text))
    # 格式2: Markdown ![alt](path)
    images.extend(re.findall(r'!\[.*?\]\(([^\)]+)\)', text))
    # 格式3: HTML <img src="path">
    images.extend(re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text, re.IGNORECASE))
    # 去重（保持顺序）
    seen = set()
    unique = []
    for img in images:
        if img not in seen:
            seen.add(img)
            unique.append(img)
    return unique


def _ensure_images_dir():
    """确保图片存储目录存在"""
    os.makedirs(IMAGES_DIR, exist_ok=True)


def _chunk_text(text: str, max_chars: int = 800, overlap: int = 60) -> list[str]:
    """
    将文本切分为重叠的块。
    保护原子结构（公式/表格/图片引用）不被截断。
    """
    # ── 第1步：保护原子块（替换为占位符）──
    placeholders = {}
    counter = [0]

    def _protect(match):
        key = f"__ATOMIC_{counter[0]}__"
        placeholders[key] = match.group(0)
        counter[0] += 1
        return key

    # 保护顺序很重要：多行先于单行
    # 保护 $$...$$ 公式（支持跨行）
    text = re.sub(r'\$\$[\s\S]*?\$\$', _protect, text)
    # 保护 Markdown 表格（连续的 |...| 行，含表头分隔行）
    text = re.sub(r'(?:^\|.+\|$\n?)+', _protect, text, flags=re.MULTILINE)
    # 保护 [image: ...] 引用
    text = re.sub(r'\[image:[^\]]+\]', _protect, text)
    # 保护 [图表] 描述行
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


def _safe_slice_point(text: str, target: int) -> int:
    """
    寻找安全的切片点：优先在 target 附近找标点/空格，避免切断中文。
    向前搜索 50 字符，向后搜索 50 字符。
    找不到则返回 target（允许切断）。
    """
    if target <= 0 or target >= len(text):
        return target
    # 搜索范围：[target-50, target+50]，但不超过文本边界
    start = max(0, target - 50)
    end = min(len(text), target + 50)
    # 优先找标点（中文+英文）
    punctuation = set('。！？；;,.!? \n\t')
    # 先向前找
    for i in range(target, start, -1):
        if text[i] in punctuation:
            return i + 1  # 标点后开始新 chunk
    # 再向后找
    for i in range(target, end):
        if text[i] in punctuation:
            return i + 1
    # 找不到标点，找空格
    for i in range(target, start, -1):
        if text[i] == ' ':
            return i + 1
    for i in range(target, end):
        if text[i] == ' ':
            return i + 1
    # 实在找不到，返回 target
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
            # 如果单句超长，安全切片
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
    # ── overlap：相邻 chunk 尾部 → 头部拼接 ──
    # 原子块已在上层 _chunk_text() 由占位符保护，overlap 不会破坏它们
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i-1][-overlap:] if len(chunks[i-1]) >= overlap else chunks[i-1]
            overlapped.append(prev_tail + "\n\n" + chunks[i])
        return overlapped
    return chunks


# ═══════════════════════════════════════════
# 核心 API
# ═══════════════════════════════════════════

def ingest(
    file_path: str = None,
    text: str = None,
    collection: str = DEFAULT_COLLECTION,
    metadata: dict = None,
    model: str = EMBED_MODEL,
    skip_duplicates: bool = True
) -> dict:
    """
    摄入文档到知识库。

    参数:
        file_path: 文件路径（与 text 二选一）
        text: 文本内容（与 file_path 二选一）
        collection: Qdrant 集合名
        metadata: 自定义元数据
        model: Ollama 嵌入模型名
        skip_duplicates: 是否跳过重复内容

    返回:
        {"ok": true/false, "chunks": N, "collection": "...", "source": "..."}
    """
    if not _ensure_collection(collection):
        return {"ok": False, "error": "Qdrant 未运行。请先启动 Qdrant（双击 run.bat）。"}

    # 读取内容
    if file_path:
        if not os.path.exists(file_path):
            return {"ok": False, "error": f"文件不存在: {file_path}"}
        # 根据文件扩展名选择读取方式
        ext = os.path.splitext(file_path)[1].lower()
        text_formats = (".txt", ".md", ".json", ".csv", ".log")
        if ext in text_formats:
            # 文本格式：直接读取（自动检测编码）
            enc = detect_encoding(file_path)
            try:
                with open(file_path, "r", encoding=enc) as f:
                    text = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", encoding="latin-1") as f:
                    text = f.read()
        else:
            # 二进制格式：调用 extract_text() 提取文本
            result = extract_text(file_path)
            if not result.get("ok"):
                return {"ok": False, "error": result.get("error", "文本提取失败")}
            text = result["text"]
        source = os.path.basename(file_path)
    elif text:
        source = metadata.get("source", "直接输入") if metadata else "直接输入"
    else:
        return {"ok": False, "error": "请提供 file_path 或 text"}
    source = source or "unknown"  # 防御性兜底

    if not text or not text.strip():
        return {"ok": False, "error": "文本内容为空"}

    # ── 去重检查 ──
    content_hash = _text_hash(text)
    if skip_duplicates:
        try:
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={
                    "filter": {
                        "must": [{"key": "content_hash", "match": {"value": content_hash}}]
                    },
                    "limit": 1
                },
                timeout=10
            )
            if resp.status_code == 200 and resp.json().get("result", {}).get("points"):
                return {
                    "ok": False,
                    "error": "内容重复，已跳过（使用 --no-dedup 强制入库）",
                    "duplicate_of": resp.json()["result"]["points"][0]["payload"].get("source", "未知"),
                    "content_hash": content_hash
                }
        except Exception:
            pass  # 去重检查失败不影响主流程

    # ── 提取图片引用并验证 ──
    _ensure_images_dir()
    image_refs = _extract_images(text)
    valid_images = []
    for img_path in image_refs:
        if os.path.isfile(img_path):
            valid_images.append(os.path.abspath(img_path))
        elif os.path.isfile(os.path.join(IMAGES_DIR, os.path.basename(img_path))):
            valid_images.append(os.path.join(IMAGES_DIR, os.path.basename(img_path)))

    # ── 切块 ──
    chunks = _chunk_text(text)
    if not chunks:
        return {"ok": False, "error": "切块后无内容"}

    # ── 嵌入 ──
    try:
        vectors = _embed(chunks, model=model)
    except Exception as e:
        return {"ok": False, "error": f"嵌入失败: {e}"}

    # ── 嵌入容错：至少 50% 成功才写入 ──
    if not vectors:
        return {"ok": False, "error": "所有块嵌入失败"}
    if len(vectors) < len(chunks) * 0.5:
        return {
            "ok": False,
            "error": f"嵌入成功率过低 ({len(vectors)}/{len(chunks)})，已中止"
        }
    # 对齐：vectors 可能少于 chunks（部分失败跳过），取前 N 个匹配
    if len(vectors) < len(chunks):
        print(f"  [WARN] {len(chunks) - len(vectors)}/{len(chunks)} 块嵌入失败，已跳过")
        chunks = chunks[:len(vectors)]

    # ── 构建 Qdrant points（v4.0 分组字段结构）──
    base_meta = metadata or {}
    # doc_id: 文档级唯一标识（完整 UUID，非截短）
    doc_id = base_meta.get("doc_id") or str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc).isoformat()
    full_text_hash = _text_hash(text)

    # ── 分面字段 ──
    content_type   = base_meta.get("content_type", "knowledge")
    domain         = base_meta.get("domain", [])
    temporal_nature = base_meta.get("temporal_nature", "timeboxed")
    epistemic_status = base_meta.get("epistemic_status", "unverified")

    # ── 生命周期（普通字段）──
    lifecycle      = base_meta.get("lifecycle", "published")
    project_source = base_meta.get("project_source", "")  # 降级为普通字段

    # ── 知识管理字段 ──
    knowledge_type = base_meta.get("knowledge_type", "")
    is_personal    = base_meta.get("is_personal", False)
    trust_score    = base_meta.get("trust_score", 3)
    tags           = base_meta.get("tags", [])
    is_canonical   = base_meta.get("is_canonical", True)
    relations      = base_meta.get("relations", [])
    keywords       = base_meta.get("keywords", [])
    auto_summary   = base_meta.get("auto_summary", "")

    # ── 时效性 + 版本 ──
    title          = base_meta.get("title") or source
    publish_date   = base_meta.get("publish_date", None)
    effective_date = base_meta.get("effective_date", None)
    expiry_date    = base_meta.get("expiry_date", None)
    version        = base_meta.get("version", "")

    # ── 来源元数据 ──
    author        = base_meta.get("author", "")
    source_url    = base_meta.get("source_url", "")
    file_type     = base_meta.get("file_type", "txt")
    ingest_method = base_meta.get("ingest_method", "manual")

    # ── 内容创作字段 ──
    target_platform = base_meta.get("target_platform", "none")
    related_product = base_meta.get("related_product", "")

    # ── 系统字段 ──
    language     = base_meta.get("language") or _detect_language(text)
    access_level = base_meta.get("access_level", "private")
    batch_id     = base_meta.get("batch_id", "")
    needs_review = base_meta.get("needs_review", False)  # 置信度路由标记

    points = []
    for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
        # 每个 chunk 用随机 64-bit ID（不依赖 Qdrant points_count，零并发冲突）
        point_id = uuid.uuid4().int >> 64
        points.append({
            "id": point_id,
            "vector": vec,
            "payload": {
                # ── 内容字段 ──
                "text": chunk,
                "title": title,
                "source": source,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "doc_id": doc_id,
                "doc_uid": doc_id,  # 稳定文档标识（= doc_id，未来去重键）
                "content_hash": full_text_hash,
                "images": valid_images,

                # ── 分面字段 ──
                "content_type": content_type,
                "domain": domain if isinstance(domain, list) else [domain],
                "temporal_nature": temporal_nature,
                "epistemic_status": epistemic_status,

                # ── 生命周期（普通字段）──
                "lifecycle": lifecycle,
                "project_source": project_source,
                "udc_code": base_meta.get("udc_code", ""),

                # ── 知识管理 ──
                "knowledge_type": knowledge_type,
                "is_personal": is_personal,
                "trust_score": trust_score,
                "tags": tags if isinstance(tags, list) else [],
                "is_canonical": is_canonical,
                "relations": relations if isinstance(relations, list) else [],
                "keywords": keywords if isinstance(keywords, list) else [],
                "auto_summary": auto_summary,

                # ── timeline（所有时间戳聚合）──
                "timeline": {
                    "published": publish_date,
                    "effective": effective_date,
                    "expiry": expiry_date,
                    "ingested": ingested_at,
                    "accessed": None,
                },

                # ── origin（来源追踪聚合）──
                "origin": {
                    "author": author,
                    "source_url": source_url,
                    "file_type": file_type,
                    "ingest_method": ingest_method,
                },

                # ── stats（使用统计聚合）──
                "stats": {
                    "access_count": 0,
                    "starred": False,
                },

                # ── 内容创作 ──
                "target_platform": target_platform,
                "related_product": related_product,
                "version": version,

                # ── 系统字段 ──
                "language": language,
                "access_level": access_level,
                "batch_id": batch_id,
                "is_archived": False,
                "needs_review": needs_review,

                # ── 预留扩展字段 ──
                "ext_text1": None, "ext_text2": None, "ext_text3": None,
                "ext_text4": None, "ext_text5": None,
                "ext_num1":  None, "ext_num2":  None, "ext_num3": None,
                "ext_bool1": None, "ext_bool2": None, "ext_bool3": None,
                "ext_date1": None, "ext_date2": None, "ext_date3": None,
            }
        })

    # 写入 Qdrant
    try:
        resp = requests.put(
            f"{QDRANT_URL}/collections/{collection}/points",
            json={"points": points},
            timeout=30
        )
        resp.raise_for_status()
    except Exception as e:
        return {"ok": False, "error": f"写入 Qdrant 失败: {e}"}

    # 写入摄入日志
    _log_ingest({
        "source_file": file_path or "",
        "source_text": text[:500] if not file_path else None,
        "collection": collection,
        "doc_id": doc_id,
        "content_hash": full_text_hash,
        "embed_model": model,
        "ingested_at": ingested_at,
    })

    return {
        "ok": True,
        "chunks": len(chunks),
        "collection": collection,
        "source": source,
        "doc_id": doc_id,
        "content_hash": full_text_hash,
        "images": valid_images
    }


def search(
    query: str,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
    score_threshold: float = 0.3,
    model: str = EMBED_MODEL,
    facet_filter: dict = None,
) -> dict:
    """
    向量搜索知识库（支持分面过滤）。

    参数:
        query: 搜索问题
        top_k: 返回结果数
        collection: 搜索的集合
        score_threshold: 最低相似度
        model: 嵌入模型
        facet_filter: 分面过滤条件，格式：
            {
                "content_type": ["knowledge"],           # 内容类型（任一匹配）
                "domain": ["0", "6"],                    # 主题域-UDC（任一匹配）
                "temporal_nature": "evergreen",          # 时效属性（单个值）
                "epistemic_status": "corroborated",      # 认知验证状态（单个值）
                "lifecycle": "published",               # 生命周期（单个值，普通字段）
                "is_personal": false,                  # 是否个人化
                "trust_score_min": 3,                  # 最低可信度
                "knowledge_type": ["formula"],          # 知识子类型
                "tags": ["齿轮"],                     # 标签（任一匹配）
            }

    返回结构:
    {
        "ok": true/false,
        "query": "原始查询",
        "total": 匹配数,
        "chunks": [{
            "text": "...", "title": "...", "source": "...",
            "score": 0.95, "chunk_index": 0, "doc_id": "...",
            "images": [...],
            # 分面字段
            "content_type": "knowledge", "domain": ["6"],
            "temporal_nature": "evergreen", "epistemic_status": "corroborated",
            # 普通字段
            "lifecycle": "published", "project_source": "",
            "udc_code": "621",
            # 知识管理
            "is_personal": false, "trust_score": 4,
            "knowledge_type": "formula", "tags": ["齿轮"],
            "is_canonical": true, "relations": [...],
            "keywords": [...], "auto_summary": "...",
            # 分组字段
            "timeline": {"published": ..., "ingested": ..., "accessed": ...},
            "origin": {"author": "...", "source_url": "...", ...},
            "stats": {"access_count": 0, "starred": false},
            # 其他
            "target_platform": "none", "version": "",
        }, ...]
    }
    """
    if not _ensure_collection(collection):
        return {"ok": False, "error": "Qdrant 未运行。请先启动 Qdrant（双击 run.bat）。"}

    # 嵌入查询
    try:
        query_vec = _embed([query], model=model)[0]
    except Exception as e:
        return {"ok": False, "error": f"嵌入查询失败: {e}"}

    # 构建过滤条件（分面过滤）
    qdrant_filter = None
    if facet_filter:
        must_conditions = []

        def _add_match(key, vals):
            """统一构建 match 条件（单值 or 多值 any）"""
            must_conditions.append({
                "key": key,
                "match": {"value": vals[0]} if len(vals) == 1 else {"any": vals}
            })

        # 多值匹配字段（content_type / domain / knowledge_type / tags）
        for key in ("content_type", "domain", "knowledge_type", "tags"):
            if facet_filter.get(key):
                _add_match(key, facet_filter[key])

        # 单值匹配字段（temporal_nature / epistemic_status / lifecycle）
        for key in ("temporal_nature", "epistemic_status", "lifecycle"):
            if facet_filter.get(key):
                must_conditions.append({
                    "key": key,
                    "match": {"value": facet_filter[key]}
                })

        # 布尔匹配（is_personal）
        if "is_personal" in facet_filter:
            must_conditions.append({
                "key": "is_personal",
                "match": {"value": facet_filter["is_personal"]}
            })

        # 范围匹配（trust_score_min）
        if facet_filter.get("trust_score_min") is not None:
            must_conditions.append({
                "key": "trust_score",
                "range": {"gte": facet_filter["trust_score_min"]}
            })

        if must_conditions:
            qdrant_filter = {"must": must_conditions}

    # 搜索 Qdrant
    try:
        search_body = {
            "vector": query_vec,
            "limit": top_k,
            "with_payload": True,
            "score_threshold": score_threshold
        }
        if qdrant_filter:
            search_body["filter"] = qdrant_filter

        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/search",
            json=search_body,
            timeout=30
        )
        resp.raise_for_status()
        results = resp.json()["result"]
    except Exception as e:
        return {"ok": False, "error": f"搜索失败: {e}"}

    # ── 整理结果（v4.0 分组字段）──
    chunks = []
    for r in results:
        payload = r.get("payload", {})
        chunks.append({
            "text":            payload.get("text", ""),
            "title":           payload.get("title", ""),
            "source":          payload.get("source", "未知"),
            "score":           round(r.get("score", 0), 4),
            "chunk_index":     payload.get("chunk_index", 0),
            "doc_id":          payload.get("doc_id", ""),
            "images":          payload.get("images", []),
            # 分面字段
            "content_type":    payload.get("content_type", "knowledge"),
            "domain":          payload.get("domain", []),
            "temporal_nature": payload.get("temporal_nature", "timeboxed"),
            "epistemic_status":payload.get("epistemic_status", "unverified"),
            # 普通字段
            "lifecycle":       payload.get("lifecycle", ""),
            "project_source":  payload.get("project_source", ""),
            "udc_code":        payload.get("udc_code", ""),
            # 知识管理
            "is_personal":     payload.get("is_personal", False),
            "trust_score":     payload.get("trust_score", 3),
            "knowledge_type":  payload.get("knowledge_type", ""),
            "tags":            payload.get("tags", []),
            "is_canonical":    payload.get("is_canonical", True),
            "relations":       payload.get("relations", []),
            "keywords":        payload.get("keywords", []),
            "auto_summary":    payload.get("auto_summary", ""),
            # 分组字段
            "timeline":        payload.get("timeline", {}),
            "origin":          payload.get("origin", {}),
            "stats":           payload.get("stats", {}),
            # 内容创作
            "target_platform": payload.get("target_platform", "none"),
            "related_product": payload.get("related_product", ""),
            "version":         payload.get("version", ""),
            # 系统字段
            "language":        payload.get("language", "zh"),
            "access_level":    payload.get("access_level", "private"),
            "batch_id":        payload.get("batch_id", ""),
            "is_archived":     payload.get("is_archived", False),
        })

    return {
        "ok": True,
        "query": query,
        "total": len(chunks),
        "chunks": chunks
    }


# ═══════════════════════════════════════════
# 报告输出（AI 综合回答 + 原始素材 → HTML → PDF）
# ═══════════════════════════════════════════

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_data", "reports")

# ── LLM API 配置（OpenAI 兼容接口）──
LLM_BASE_URL = os.environ.get("KB_LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY  = os.environ.get("KB_LLM_API_KEY", "")
LLM_MODEL    = os.environ.get("KB_LLM_MODEL", "deepseek-chat")


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _call_llm_api(messages: list, base_url: str = None, api_key: str = None, model: str = None) -> str:
    """调用 OpenAI 兼容 Chat API，返回模型回复文本。"""
    base_url = (base_url or LLM_BASE_URL).rstrip("/")
    resp = requests.post(
        f"{base_url}/chat/completions",
        json={
            "model": model or LLM_MODEL,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048
        },
        headers={"Authorization": f"Bearer {api_key or LLM_API_KEY}"},
        timeout=120
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json_block(text: str) -> dict:
    """
    从 LLM 返回文本中提取并解析 JSON 对象（支持嵌套）。
    
    策略：
      1. 先尝试直接 json.loads()（LLM 可能返回纯净 JSON）
      2. 失败则找第一个 '{'，然后匹配花括号（计数深度），提取最外层 JSON
      3. 对提取的块尝试 json.loads()
    
    返回:
        dict — 解析成功
        None — 无法提取/解析
    """
    text = text.strip()
    
    # 策略1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 策略2：提取 JSON 块（匹配花括号）
    start = text.find("{")
    if start == -1:
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    json_end = -1
    
    for i in range(start, len(text)):
        ch = text[i]
        
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if in_string:
            if ch == '"':
                in_string = False
            continue
        
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break
    
    if json_end == -1:
        return None
    
    json_str = text[start:json_end]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # 尝试修复常见错误：去掉尾部逗号
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*\]", "]", json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


def auto_classify(text: str, metadata: dict = None) -> dict:
    """
    使用 LLM 自动分析文本，推断分面字段。
    返回结构化的分类建议 dict，可直接传给 ingest() 的 metadata 参数。

    设计原则:
      - LLM 严格从给定选项中选取，禁止自由发挥
      - 输出经过字段合法性校验，非法值 fallback 到默认值
      - 文本过长时取前 5000 字符作为样本（分类不需要全文）

    返回:
      {
        "ok": true/false,
        "classification": {content_type, domain[], lifecycle, trust_score,
                           keywords[], title, author, knowledge_type,
                           temporal_nature, epistemic_status, udc_code,
                           auto_summary, is_personal, confidence},
        "raw_response": "LLM原始输出(调试用)"
      }
    """
    from config.classifications import (
        CONTENT_TYPES, DOMAINS, LIFECYCLE_STAGES, KNOWLEDGE_TYPES,
        TEMPORAL_NATURE, EPISTEMIC_STATUS,
        CONTENT_TYPE_OPTIONS, DOMAIN_OPTIONS, LIFECYCLE_OPTIONS,
        KNOWLEDGE_TYPE_OPTIONS, TRUST_SCORE_LABELS
    )

    # ── L1-L3 四层管道（简化版）──
    # L1（模板默认）：如果 metadata 已提供值，优先使用
    result = metadata.copy() if metadata else {}
    
    # L2（文件元数据）：无文件扩展名信息，跳过
    
    # L3（关键词匹配）：根据文本内容推断 domain
    text_lower = text.lower()
    keyword_domain_map = {
        "齿轮|模数|强度|公差|机械设计": ["6"],
        "ai|llm|模型|深度学习|神经网络": ["0"],
        "标准|国标|iso|gb/t": ["0", "6"],
        "公式|定理|数学": ["5"],
        "程序|代码|python|javascript": ["0"],
        "设计|ux|ui|排版": ["7"],
    }
    if "domain" not in result or not result["domain"]:
        for kw_pattern, domains in keyword_domain_map.items():
            if any(kw in text_lower for kw in kw_pattern.split("|")):
                result["domain"] = domains
                break
    
    # L4（LLM 推断）：只调用 LLM 推断 result 中缺失的字段
    # 如果 result 已包含所有必要字段，跳过 LLM 调用
    required_fields = ["content_type", "domain", "temporal_nature", "epistemic_status"]
    missing_fields = [f for f in required_fields if f not in result or not result[f]]
    if not missing_fields:
        # 所有必要字段已确定，跳过 LLM
        normalize_facet_values(result)
        return {"ok": True, "classification": result}
    
    api_key = os.environ.get("KB_LLM_API_KEY") or LLM_API_KEY
    if not api_key:
        return {"ok": False, "error": "未配置 LLM API Key，无法自动分类。请在引擎配置页面设置。"}

    # ── 截取样本（分类不需要全文）──
    sample = text[:5000].strip()
    if not sample:
        return {"ok": False, "error": "文本内容为空"}

    # ── 构建所有选项的可读列表（供 LLM 选择）──
    ct_list = "\n".join(f"  - {k}: {v}" for k, v in CONTENT_TYPES.items())
    domain_list = "\n".join(f"  - {k}: {v}" for k, v in DOMAINS.items())
    lifecycle_list = "\n".join(f"  - {k}: {v}" for k, v in LIFECYCLE_STAGES.items())
    temporal_list = "\n".join(f"  - {k}: {v}" for k, v in TEMPORAL_NATURE.items())
    epistemic_list = "\n".join(f"  - {k}: {v}" for k, v in EPISTEMIC_STATUS.items())
    ktype_list = "\n".join(f"  - {k}: {v}" for k, v in KNOWLEDGE_TYPES.items())
    trust_labels = "\n".join(f"  {k}: {v}" for k, v in TRUST_SCORE_LABELS.items())

    prompt = f"""你是一个知识分类专家。请分析以下文本内容，从给定选项中选择最合适的分类标签。你必须严格从选项中选择，不得自由发挥。

## 文本内容
{sample}

## 分类选项

### content_type（内容类型）— 必须单选，从以下选项中选择：
{ct_list}

### domain（主题域，UDC 国际十进分类法）— 可多选 0-3 个，不相关就空数组 []：
{domain_list}

### lifecycle（生命周期/工作流阶段）— 单选：
{lifecycle_list}

### temporal_nature（时效属性）— 单选，判断内容是否会随时间贬值：
{temporal_list}

### epistemic_status（认知验证状态，FPF L0-L2）— 单选：
{epistemic_list}

### trust_score（可信度）— 1-5 整数，评分依据：
{trust_labels}

### knowledge_type（知识子类型，仅 content_type=knowledge 时填，否则留空 ""）— 单选：
{ktype_list}

### keywords（关键词）— 3-8 个技术术语或关键概念，从文本内容中提取

### title（标题）— 从文本推断的简要标题，不超过 50 字。如果文本有明确标题则使用它

### author（作者）— 如果有明确出处/作者/标准号则提取，否则留空 ""

### udc_code（UDC 细分码，可选）— 如果有足够信息，输出更精确的 UDC 类号，如 "621.39"、"004.8"、复合码 "621:004.8"。无法确定则留空 ""

### auto_summary（自动摘要）— 用一句话（≤100字）概括本条内容的核心信息

### is_personal（是否个人化）— true 表示个人经验/笔记/主观观点，false 表示客观内容/标准/论文

### confidence（置信度）— 对你给出的每个分类字段的自信程度，0.0 完全不确定 ~ 1.0 非常确定。必须包含 overall 和每个字段的评分。

## 输出格式
严格输出以下 JSON，不要包含任何额外文字、不要用 ```json 包裹、不要加注释：
{{"content_type":"standard","domain":["0","6"],"lifecycle":"published","temporal_nature":"evergreen","epistemic_status":"corroborated","trust_score":4,"knowledge_type":"","keywords":["齿轮","模数","强度"],"title":"渐开线圆柱齿轮 模数系列","author":"GB/T 1357-2008","udc_code":"621","auto_summary":"中国国家标准 GB/T 1357-2008，规定渐开线圆柱齿轮的模数系列。","is_personal":false,"confidence":{{"overall":0.92,"fields":{{"content_type":0.95,"domain":0.88,"temporal_nature":0.90,"epistemic_status":0.98,"lifecycle":0.85,"trust_score":0.80,"knowledge_type":0.95,"title":0.97,"author":0.99,"udc_code":0.90}}}}}}"""

    try:
        raw = _call_llm_api(
            [{"role": "user", "content": prompt}],
            base_url=os.environ.get("KB_LLM_BASE_URL") or LLM_BASE_URL,
            api_key=api_key,
            model=os.environ.get("KB_LLM_MODEL") or LLM_MODEL,
        )
    except Exception as e:
        return {"ok": False, "error": f"LLM 调用失败: {e}"}

    # ── 解析 JSON ──
    result = _extract_json_block(raw)
    if result is None:
        return {"ok": False, "error": "LLM 返回格式无法解析", "raw_response": raw}

    classification = {
        "content_type": result.get("content_type", "knowledge"),
        "domain": result.get("domain", []),
        "lifecycle": result.get("lifecycle", "published"),
        "temporal_nature": result.get("temporal_nature", "timeboxed"),
        "epistemic_status": result.get("epistemic_status", "unverified"),
        "trust_score": result.get("trust_score", 3),
        "knowledge_type": result.get("knowledge_type", ""),
        "keywords": result.get("keywords", []),
        "title": result.get("title", ""),
        "author": result.get("author", ""),
        "udc_code": result.get("udc_code", ""),
        "auto_summary": result.get("auto_summary", ""),
        "is_personal": result.get("is_personal", False),
        "confidence": result.get("confidence", None),
    }

    # ── 枚举守卫：规范化分面字段值 ──
    normalize_facet_values(classification)

    if not isinstance(classification["keywords"], list):
        classification["keywords"] = []
    classification["keywords"] = [str(k).strip()[:50] for k in classification["keywords"] if k]

    # 校验 title/author（确保是 str）
    classification["title"] = str(classification["title"]).strip()[:100]
    classification["author"] = str(classification["author"]).strip()[:100]

    # 校验 auto_summary（确保是 str，截断到 200 字）
    classification["auto_summary"] = str(classification.get("auto_summary", "")).strip()[:200]

    # 校验 is_personal（确保是 bool）
    ip_val = classification.get("is_personal", False)
    if isinstance(ip_val, str):
        classification["is_personal"] = ip_val.strip().lower() in ("true", "yes", "1")
    else:
        classification["is_personal"] = bool(ip_val)

    # 校验 confidence（标准化结构，缺失则回退到默认值）
    conf = classification.get("confidence")
    if isinstance(conf, dict) and isinstance(conf.get("overall"), (int, float)):
        classification["confidence"] = {
            "overall": max(0.0, min(1.0, float(conf["overall"]))),
            "fields": conf.get("fields", {}),
        }
    else:
        # LLM 未返回置信度 → 默认整体 0.5，字段不标记
        classification["confidence"] = {"overall": 0.5, "fields": {}}

    return {
        "ok": True,
        "classification": classification,
        "raw_response": raw,
    }


def _renumber_citations(synthesis: str, citation_keys: list) -> tuple[str, list[int]]:
    """
    正则提取回答中实际使用的引用编号，重编号为连续 1~N。
    返回 (重编号后文本, 实际使用的原始引用索引列表(1-based))。
    """

    # 兼容多种格式：[引用5] [引用 5] 引用5 引用 5
    used_raw = re.findall(r'\[?引用\s*(\d+)\]?', synthesis)
    if not used_raw:
        return synthesis, []

    # 去重保持首次出现顺序
    seen = set()
    used = []
    for x in used_raw:
        nx = int(x)
        if nx not in seen:
            seen.add(nx)
            used.append(nx)

    # 建立映射：原编号 → 新编号（按出现顺序从1开始）
    mapping = {old: new for new, old in enumerate(used, 1)}

    # 替换全文（兼容 [引用5] 和 引用5 两种格式）
    def _replace(match):
        old_num = int(match.group(1))
        new_num = mapping.get(old_num)
        if new_num is None:
            return match.group(0)
        orig = match.group(0)
        if orig.startswith('['):
            return f"[引用{new_num}]"
        else:
            return f"引用{new_num}"

    new_text = re.sub(r'\[?引用\s*(\d+)\]?', _replace, synthesis)
    return new_text, used


def _chunk_has_table(text: str) -> bool:
    """检测文本是否包含有效的 Markdown 管道表格。"""
    pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
    return len(pipe_lines) >= 3 and "---" in pipe_lines[1]


def _chunk_is_garbled(text: str) -> bool:
    """检测文本是否为 OCR 碎片（单字行、大量乱码）。"""
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return True
    # 过半行是单字或短碎片（≤3 字符且无 ASCII）→ 乱码
    short_count = sum(1 for l in lines if len(l.strip()) <= 3 and not any(c.isascii() and c.isprintable() and c not in "（）" for c in l))
    return short_count > len(lines) * 0.4


def _dedup_chunks(raw_chunks: list) -> list:
    """
    去重 + 质量过滤：
    - 同一 source 下，只要有管道表格版本，就丢弃同源的非表格版（OCR 降级碎片）
    - 同源同质量级别下，去重完全相同的文本
    - 保留原始得分排序
    """
    # 按 source 分组
    groups: dict[str, list] = {}
    for c in raw_chunks:
        src = c.get("source", "未知") or "未知"
        groups.setdefault(src, []).append(c)

    result = []
    for src, items in groups.items():
        tables = [c for c in items if _chunk_has_table(c["text"])]
        if tables:
            # 该 source 有管道表格 → 只保留表格版，丢弃非表格碎片
            candidates = tables
        else:
            # 纯文本 source → 丢弃乱码
            candidates = [c for c in items if not _chunk_is_garbled(c["text"])]

        if not candidates:
            continue

        # 去重完全相同的文本
        seen_text = set()
        for c in sorted(candidates, key=lambda c: c.get("score", 0), reverse=True):
            key = c["text"].strip()
            if key not in seen_text:
                seen_text.add(key)
                result.append(c)

    # 按原始分数降序
    result.sort(key=lambda c: c.get("score", 0), reverse=True)
    return result


def _expand_chunks(chunks: list, threshold: int = None) -> list:
    """
    展开 chunks：表格行数 > threshold 时，按行拆分为虚拟 chunk。
    返回展开后的 chunks 列表（长度 >= len(chunks)）。
    """
    if threshold is None:
        threshold = TABLE_SPLIT_THRESHOLD

    expanded = []
    for c in chunks:
        text = c["text"]
        pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
        is_table = len(pipe_lines) >= 3 and "---" in pipe_lines[1]

        if is_table and len(pipe_lines) - 2 > threshold:
            # 拆分：为每一行创建虚拟 chunk（浅拷贝，仅替换 text）
            for dl in pipe_lines[2:]:
                vc = dict(c)  # 浅拷贝，保留 images/source 等
                vc["text"] = f"{pipe_lines[0]}\n{pipe_lines[1]}\n{dl}"
                expanded.append(vc)
        else:
            expanded.append(c)

    return expanded


def _build_synthesis_prompt(query: str, chunks: list, table_split_threshold: int = None) -> tuple[str, list[str]]:
    """
    根据搜索结果构建 LLM 合成提示词。
    输入 chunks 已去重。
    如果 table_split_threshold 非空且某个表格 chunk 的行数 > 阈值，
    则将该表格按行拆分为多个迷你表引用（每行一个 [引用N]）。

    返回 (prompt_text, citation_keys)。
    """

    if table_split_threshold is None:
        table_split_threshold = TABLE_SPLIT_THRESHOLD

    # ── 展开 chunks（表格按行拆分） ──
    expanded = []  # list of (ref_id, src, text)

    for c in chunks:
        text = c["text"]
        src = c.get("source", "未知") or "未知"

        # 检测是否为管道表格
        pipe_lines = [l for l in text.split("\n") if l.strip().startswith("|")]
        is_table = len(pipe_lines) >= 3 and "---" in pipe_lines[1]

        if is_table and len(pipe_lines) - 2 > table_split_threshold:
            # 拆分：每行生成一个迷你表引用
            header_line = pipe_lines[0]
            sep_line = pipe_lines[1]
            data_lines = pipe_lines[2:]

            for dl in data_lines:
                mini = f"{header_line}\n{sep_line}\n{dl}"
                expanded.append((None, src, mini))  # ref_id 稍后统一编号
        else:
            # 不拆分，整块作为一条引用
            if len(text) > 1500:
                text = text[:1500] + "…(省略)"
            expanded.append((None, src, text))

    # 统一编号
    materials = []
    citation_keys = []
    for i, (_, src, text) in enumerate(expanded):
        ref_id = f"[引用{i+1}]"
        citation_keys.append(ref_id)
        materials.append(f"{ref_id} 来源:{src}\n{text}")

    materials_text = "\n\n---\n\n".join(materials)

    prompt = f"""你是知识库助手。请根据下面的参考资料，用中文直接回答用户的问题。

要求：
1. 从参考资料中提取相关信息，用自己的语言组织答案
2. 必须使用所有提供的参考资料（共{len(materials)}条），每个论断后面标注引用编号
3. 引用编号必须使用提供的 [引用1] [引用2] 等格式，不要自行编造编号
4. 如果某部分内容不是来自参考资料，而是你自己的推理或补充知识，请在句末标注 [补充]
5. 禁止编造参考资料中不存在的公式、数据、结论。[补充] 内容除外
6. 公式用 LaTeX 语法（行内 $...$，独行 $$...$$）
7. 如果参考资料不足以回答问题，请诚实说明
8. 回答字数控制在 300-800 字

用户问题：{query}

参考资料：
{materials_text}"""

    return prompt, citation_keys


def _img_to_b64(img_path: str, max_w: int = 800) -> str:
    """
    将图片文件转为 base64 data URI，嵌入 HTML 使用。
    自动缩小到 max_w 像素以内（避免 HTML 文件过大）。
    失败返回空字符串。
    """
    if HAS_PIL:
        try:
            with PILImage.open(img_path) as im:
                w, h = im.size
                if w > max_w:
                    ratio = max_w / w
                    im = im.resize((int(w * ratio), int(h * ratio)), PILImage.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format=im.format or "PNG")
                data = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            try:
                with open(img_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
            except Exception:
                return ""
    else:
        try:
            with open(img_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()
        except Exception:
            return ""
    ext = os.path.splitext(img_path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(ext, "image/png")
    return f"data:{mime};base64,{data}"


# ── KaTeX 服务端渲染 ──
_KATEX_CSS = None
_NODE_BIN = os.environ.get("KB_NODE_BIN") or "node"
_NPM_ROOT = os.environ.get("KB_NPM_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_modules")
_KATEX_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_math.js")

def _katex_css() -> str:
    """返回 KaTeX CSS（惰性加载，只读一次）。"""
    global _KATEX_CSS
    if _KATEX_CSS is None:
        css_path = os.path.join(_NPM_ROOT, "katex", "dist", "katex.min.css")
        try:
            with open(css_path, "r", encoding="utf-8") as f:
                _KATEX_CSS = f.read()
        except FileNotFoundError:
            _KATEX_CSS = ""
    return _KATEX_CSS


def _katex_post_process(html: str) -> str:
    """将 HTML 中的 <span class="formula-block">... 和 <span class="formula-inline">...
    批量渲染为 KaTeX HTML。失败时保留原始 span作为兜底。"""
    # 收集所有公式
    formulas = []
    pattern = re.compile(
        r'<span class="formula-(block|inline)">(.*?)</span>',
        re.DOTALL
    )

    for m in pattern.finditer(html):
        display = (m.group(1) == "block")
        text = m.group(2).strip()
        if text:
            formulas.append({
                "text": text,
                "display": display,
                "start": m.start(),
                "end": m.end(),
                "original": m.group(0)
            })

    if not formulas:
        return html

    # 写入临时 JSON
    fd, tmp_in = tempfile.mkstemp(suffix=".json", prefix="katex_in_")
    os.close(fd)
    fd, tmp_out = tempfile.mkstemp(suffix=".json", prefix="katex_out_")
    os.close(fd)
    try:
        batch = [{"text": f["text"], "display": f["display"]} for f in formulas]
        with open(tmp_in, "w", encoding="utf-8") as f:
            json.dump({"formulas": batch}, f, ensure_ascii=False)

        env = os.environ.copy()
        env["NODE_PATH"] = _NPM_ROOT
        result = subprocess.run(
            [_NODE_BIN, _KATEX_SCRIPT, tmp_in, tmp_out],
            capture_output=True, text=True, timeout=30, env=env
        )
        if result.returncode != 0:
            return html  # Node.js 失败，保留原始 span

        with open(tmp_out, "r", encoding="utf-8") as f:
            output = json.load(f)

        # 替换：从后往前替换以保持位置正确
        results = output.get("results", [])
        if len(results) != len(formulas):
            return html  # 数量不匹配

        parts = []
        last_end = 0
        for i, fm in enumerate(formulas):
            r = results[i]
            parts.append(html[last_end:fm["start"]])
            if r.get("ok"):
                parts.append(r["html"])
            else:
                parts.append(fm["original"])  # 回退到原始 span
            last_end = fm["end"]
        parts.append(html[last_end:])
        return "".join(parts)

    finally:
        for p in (tmp_in, tmp_out):
            try:
                os.unlink(p)
            except OSError:
                pass


# ── 公式文本 → HTML span 工具函数 ──
FORMULA_BLOCK_RE = re.compile(r'\$\$([\s\S]+?)\$\$')
FORMULA_INLINE_RE = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')


def _formula_to_html_spans(text: str) -> str:
    """将 LaTeX 公式转为 <span class="formula-block/inline"> 标记，供 KaTeX 后处理。"""
    text = FORMULA_BLOCK_RE.sub(r'<span class="formula-block">\1</span>', text)
    text = FORMULA_INLINE_RE.sub(r'<span class="formula-inline">\1</span>', text)
    return text


def _render_report_html(query: str, synthesis: str, chunks: list, output_dir: str, used: list = None, citation_keys: list = None) -> str:
    """
    渲染两层报告 HTML：上层 AI 回答 + 下层原始素材。
    返回 HTML 文件路径。
    """
    import html as _html

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_query = re.sub(r'[\\/*?:"<>|]', '_', query)[:40]

    # ── 上层：AI 回答（引用编号高亮） ──
    # 注意：不对 synthesis 做 HTML 转义，保留 $...$ 供 MathJax 渲染
    # LLM 输出是可信的；若含 < > 等字符会被 MathJax/浏览器安全处理
    synthesis_html = synthesis
    # 双换行为段落
    synthesis_html = re.sub(r'\n\n+', '</p><p>', synthesis_html)
    synthesis_html = synthesis_html.replace('\n', '<br>')
    if not synthesis_html.startswith('<p>'):
        synthesis_html = '<p>' + synthesis_html
    if not synthesis_html.endswith('</p>'):
        synthesis_html = synthesis_html + '</p>'

    # 引用编号加样式→跳转锚点
    synthesis_html = re.sub(
        r'\[引用(\d+)\]',
        r'<a href="#ref\1" class="citation">[引用\1]</a>',
        synthesis_html
    )

    # 公式：先处理 $$..$$（多行），再处理 $..$（单行，排除 $$ 边界）
    synthesis_html = _formula_to_html_spans(synthesis_html)

    # ── 收集所有图片路径 ──
    all_images = []
    for c in chunks:
        for img in c.get("images", []):
            if img and os.path.isfile(img) and img not in all_images:
                all_images.append(img)

    # ── 下层：原始素材（每条 chunk 都展示，按 source+chunk_index 去重） ──

    def _img_tag(img_path: str, max_w: int = 700) -> str:
        """将图片路径转为 base64 <img> 标签，失败返回原路径 file:// 引用。"""
        b64 = _img_to_b64(img_path, max_w=max_w)
        if b64:
            return f'<br><img src="{b64}" class="evidence-img"><br>'
        # 降级：file:// 引用（桌面可能还能打开）
        return f'<br><img src="file://{_html.escape(img_path)}" class="evidence-img"><br>'


    def _format_evidence_text(text: str) -> str:
        """格式化原始素材文本为 HTML：表格自动转 <table>，公式/图片引用包裹。"""
        lines = text.split('\n')

        # —— 先尝试整个文本是否为管道表格（过滤所有以 | 开头的行） ——
        pipe_lines = [l for l in lines if l.strip().startswith('|')]
        if len(pipe_lines) >= 3 and '---' in pipe_lines[1]:
            # 有效表格：整个文本渲染为一张 HTML table
            return _pipe_table_to_html(pipe_lines)

        # 非表格文本：逐行处理
        result = []
        for line in lines:
            # 先转义 HTML（防 XSS），再还原公式和图片引用
            escaped = _html.escape(line)
            # 还原 [image: ...] → <img> 标签
            escaped = re.sub(
                r'\[image:\s*([^\]]+)\]',
                lambda m: _img_tag(m.group(1).strip()),
                escaped
            )
            # 还原 $...$ 和 $$...$$ → formula <span>
            escaped = _formula_to_html_spans(escaped)
            result.append(escaped)
        return '\n'.join(result)

    def _pipe_table_to_html(pipe_lines: list) -> str:
        """将 Markdown 管道表格行列表转为 HTML <table>。列宽由内容预计算。"""
        def _cell_html(raw: str) -> str:
            """处理 table cell: 先转义HTML防XSS，再还原公式和图片引用。"""
            s = _html.escape(raw)
            # 还原公式 $...$ 和 $$...$$
            s = _formula_to_html_spans(s)
            # 还原图片引用 [image: ...] → <img>
            s = re.sub(r'\[image:\s*(.+?)\]', lambda m: _img_tag(m.group(1).strip()), s)
            return s

        rows = []
        for pl in pipe_lines:
            cells = pl.strip().strip('|').split('|')
            rows.append([c.strip() for c in cells])
        data_rows = [rows[0]] + rows[2:]  # skip separator row

        # ── 预计算列宽百分比 ──
        ncols = max(len(r) for r in data_rows) if data_rows else 0
        if ncols > 0:
            col_widths_ch = [0.0] * ncols
            for row in data_rows:
                for i, cell in enumerate(row):
                    if i >= ncols:
                        break
                    w = sum(2.0 if ord(c) > 127 else 1.0 for c in cell)
                    if w > col_widths_ch[i]:
                        col_widths_ch[i] = w
            total_ch = sum(col_widths_ch)
            if total_ch > 0:
                col_pcts = [max(5.0, w / total_ch * 100.0) for w in col_widths_ch]
                pct_sum = sum(col_pcts)
                col_pcts = [p / pct_sum * 100.0 for p in col_pcts]
            else:
                col_pcts = [100.0 / ncols] * ncols
            colgroup = '<colgroup>' + ''.join(f'<col style="width:{p:.1f}%">' for p in col_pcts) + '</colgroup>'
        else:
            colgroup = ''

        html_parts = ['<div class="md-table-wrap"><table class="md-table">', colgroup]
        for ri, row in enumerate(data_rows):
            tag = 'th' if ri == 0 else 'td'
            html_parts.append('<tr>')
            for cell in row:
                html_parts.append(f'<{tag}>{_cell_html(cell)}</{tag}>')
            html_parts.append('</tr>')
        html_parts.append('</table></div>')
        return ''.join(html_parts)

    raw_sections = []
    for i, c in enumerate(chunks):
        # 计算 ref_id（锚点 ID）和 ref_tag（引用标签）
        orig_num = i + 1
        ref_id = f"ref{orig_num}"
        ref_tag = ""
        if used is not None:
            if orig_num in used:
                new_num = used.index(orig_num) + 1
                ref_id = f"ref{new_num}"
                ref_tag = f'<span class="ref-tag">[引用{new_num}]</span>'
            else:
                ref_id = f"ref{orig_num}-unused"
        else:
            ref_tag = f'<span class="ref-tag">[引用{orig_num}]</span>'

        src = c.get("source", "未知") or "未知"

        text_html = _format_evidence_text(c["text"])
        score = c.get("score", 0)
        images_list = c.get("images", [])

        images_html = ""
        if images_list:
            imgs_parts = []
            for img in images_list:
                if not (img and os.path.isfile(img)):
                    continue
                b64 = _img_to_b64(img, max_w=700)
                if b64:
                    imgs_parts.append(f'<div class="ev-img-wrap"><img src="{b64}" class="evidence-img"></div>')
            if imgs_parts:
                images_html = f'<div class="evidence-images">{"".join(imgs_parts)}</div>'

        raw_sections.append(f"""
        <div class="evidence-item" id="{ref_id}">
            <div class="evidence-header">
                {ref_tag}
                <span class="evidence-source">{_html.escape(src)}</span>
                <span class="evidence-score">相关度: {score:.0%}</span>
            </div>
            <div class="evidence-text">{text_html}</div>
            {images_html}
        </div>""")

    # ── 完整 HTML ──
    all_images_html = ""
    katex_css = _katex_css()
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
<title>知识库报告：{_html.escape(query[:60])}</title>
<style>
  :root {{ --bg: #f8f9fa; --card: #fff; --text: #222; --muted: #666; --accent: #1a6fb5; --border: #e0e0e0; --formula-bg: #f0f4f8; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #1a1a2e; --card: #16213e; --text: #e0e0e0; --muted: #999; --accent: #7ec8e3; --border: #333; --formula-bg: #0f1928; }} }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; font-size: 15px; -webkit-text-size-adjust: 100%; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 32px 20px 80px; }}

  .toolbar {{ position: sticky; top: 0; z-index: 100; background: var(--card); border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }}
  .toolbar span {{ color: var(--muted); font-size: 13px; }}
  .btn-download {{ background: var(--accent); color: #fff; border: none; padding: 8px 20px; border-radius: 6px; font-size: 14px; cursor: pointer; }}
  .btn-download:hover {{ opacity: 0.85; }}

  .query-title {{ font-size: 22px; font-weight: 700; margin: 24px 0 8px; }}
  .query-meta {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}

  .section {{ margin: 32px 0; }}
  .section h2 {{ font-size: 18px; color: var(--accent); border-bottom: 2px solid var(--border); padding-bottom: 8px; margin-bottom: 16px; }}

  .synthesis {{ background: var(--card); border-radius: 8px; padding: 24px; border: 1px solid var(--border); }}
  .synthesis p {{ margin: 8px 0; }}
  .citation {{ color: var(--accent); text-decoration: none; font-weight: 600; font-size: 13px; vertical-align: super; }}
  .citation:hover {{ text-decoration: underline; }}
  .formula-block {{ display: block; background: var(--formula-bg); padding: 10px 16px; border-radius: 4px; margin: 8px 0; font-family: "Times New Roman", serif; font-size: 16px; overflow-x: auto; }}
  .formula-inline {{ font-family: "Times New Roman", "Cambria Math", serif; font-style: italic; color: #1a5c8a; background: rgba(26,111,181,0.06); padding: 1px 4px; border-radius: 3px; word-break: keep-all; }}

  .evidence-item {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin: 16px 0; }}
  .evidence-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }}
  .ref-tag {{ background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; flex-shrink: 0; }}
  .evidence-source {{ color: var(--muted); font-size: 13px; }}
  .evidence-score {{ color: var(--muted); font-size: 12px; margin-left: auto; }}
  .evidence-text {{ font-size: 14px; line-height: 1.8; word-break: break-word; }}
  .evidence-images {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
  .evidence-images img, .evidence-img {{ max-width: 100%; max-height: 400px; object-fit: contain; border: 1px solid var(--border); border-radius: 4px; margin: 6px 0; display: block; }}

  .md-table-wrap {{ max-width: 100%; overflow-x: auto; margin: 10px 0; -webkit-overflow-scrolling: touch; }}
  .md-table {{ border-collapse: collapse; font-size: 13px; table-layout: fixed; width: 100%; }}
  .md-table th {{ background: var(--formula-bg); color: var(--text); padding: 8px 10px; border: 1px solid var(--border); text-align: left; font-weight: 600; overflow-wrap: break-word; }}
  .md-table td {{ padding: 8px 10px; border: 1px solid var(--border); vertical-align: top; word-break: break-word; overflow-wrap: break-word; }}
  .md-table tr:nth-child(even) td {{ background: rgba(128,128,128,0.04); }}

  @media (max-width: 600px) {{
    .container {{ padding: 16px 12px 60px; }}
    .evidence-item {{ padding: 14px; }}
    .md-table {{ font-size: 12px; }}
    .md-table th, .md-table td {{ padding: 6px 8px; }}
    .formula-block {{ padding: 8px 10px; font-size: 14px; }}
    .evidence-images img, .evidence-img {{ max-height: 280px; }}
    .query-title {{ font-size: 18px; }}
    .toolbar {{ padding: 10px 16px; }}
  }}

  @media print {{
    .toolbar {{ display: none; }}
    body {{ background: #fff; color: #000; font-size: 12px; }}
    .container {{ max-width: 100%; padding: 0; }}
    .evidence-item, .synthesis {{ box-shadow: none; break-inside: avoid; }}
    .md-table-wrap {{ overflow-x: visible; }}
    .md-table {{ width: 100%; font-size: 11px; }}
  }}
{katex_css}
</style>
</head>
<body>
<div class="toolbar">
  <span>生成时间: {now_str}</span>
  <button class="btn-download" onclick="window.print()">📥 下载 PDF / 打印</button>
</div>
<div class="container">
  <h1 class="query-title">{_html.escape(query)}</h1>
  <p class="query-meta">知识库检索 · {len(chunks)} 条匹配 · {now_str}</p>
  <div class="section">
    <h2>📝 综合回答</h2>
    <div class="synthesis">{synthesis_html}</div>
  </div>
  <div class="section">
    <h2>📚 原始素材</h2>
    {"".join(raw_sections)}
  </div>
  {all_images_html}
</div>
</body>
</html>"""

    # KaTeX 服务端渲染：批量转换所有 $...$ 公式
    html = _katex_post_process(html)

    _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{timestamp}.html"
    html_path = os.path.join(output_dir, filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path


def answer(
    query: str,
    top_k: int = 5,
    collection: str = DEFAULT_COLLECTION,
    model: str = EMBED_MODEL,
    threshold: float = 0.3,
    llm_model: str = None,
    llm_base_url: str = None,
    llm_api_key: str = None,
    output_dir: str = None,
    table_split_threshold: int = None,
    facet_filter: dict = None,
) -> dict:
    """
    端到端知识库问答：搜索 → LLM API 合成 → HTML 报告（KaTeX 公式渲染）。

    参数:
        facet_filter: 分面过滤条件（见 search() 函数说明）
    """
    output_dir = output_dir or OUTPUT_DIR
    # 从 os.environ 实时读取（避免 .env 加载顺序导致的空值）
    llm_model = llm_model or os.environ.get("KB_LLM_MODEL") or LLM_MODEL
    llm_base_url = llm_base_url or os.environ.get("KB_LLM_BASE_URL") or LLM_BASE_URL
    llm_api_key = llm_api_key or os.environ.get("KB_LLM_API_KEY") or LLM_API_KEY

    if not llm_base_url or not llm_api_key:
        return {
            "ok": False,
            "error": "未配置 LLM API。请设置环境变量 KB_LLM_BASE_URL/KB_LLM_API_KEY 或传入 --llm-base-url/--llm-api-key。"
        }

    # 1. 搜索（单集合方案）
    sr = search(query, top_k=top_k, collection=collection,
                 score_threshold=threshold, model=model,
                 facet_filter=facet_filter)
    raw_chunks = sr.get("chunks", [])

    if not sr.get("ok"):
        return {"ok": False, "error": sr.get("error", "搜索失败")}

    if not raw_chunks:
        return {"ok": True, "query": query, "synthesis": "知识库中未找到相关内容。", "chunks": [], "html": None}

    # 1.5 去重
    chunks = _dedup_chunks(raw_chunks)

    # 2. LLM 合成
    prompt_text, citation_keys = _build_synthesis_prompt(query, chunks, table_split_threshold=table_split_threshold)
    # 展开 chunks（表格按行拆分后与 citation_keys 一一对应）
    expanded_chunks = _expand_chunks(chunks, table_split_threshold)
    try:
        synthesis = _call_llm_api(
            [{"role": "user", "content": prompt_text}],
            base_url=llm_base_url, api_key=llm_api_key, model=llm_model
        )
    except Exception as e:
        synthesis = f"（LLM 调用失败：{e}。以下为原始检索结果。）"

    # 2.5 引用重编号（使编号连续不跳跃）
    synthesis, used = _renumber_citations(synthesis, citation_keys)

    # 3. 生成 HTML 报告
    try:
        html_path = _render_report_html(query, synthesis, expanded_chunks, output_dir, used=used, citation_keys=citation_keys)
    except Exception as e:
        return {"ok": False, "error": f"HTML 报告生成失败: {e}", "synthesis": synthesis, "chunks": chunks}

    return {"ok": True, "query": query, "synthesis": synthesis, "html": html_path, "chunks": expanded_chunks}


# ═══════════════════════════════════════════
# 知识管理函数 (v4.0)
# ═══════════════════════════════════════════

def get_facet_stats(collection: str = DEFAULT_COLLECTION) -> dict:
    """
    获取知识库的分面维度统计。

    返回:
        {
            "ok": true,
            "total_points": N,
            "facets": {
                "content_type": {"knowledge": 120, "standard": 15, ...},
                "domain":        {"0": 45, "6": 30, ...},
                "temporal_nature": {"evergreen": 80, "timeboxed": 12, ...},
                "epistemic_status":{"corroborated": 50, "unverified": 30, ...},
            },
            "meta": {
                "avg_trust": 3.2,
                "personal_count": 5,
                "archived_count": 0,
            }
        }
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 获取 points_count
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        if info.status_code != 200:
            return {"ok": False, "error": f"集合 {collection} 不存在"}

        total_pts = info.json()["result"]["points_count"]
        if total_pts == 0:
            return {"ok": True, "total_points": 0, "facets": {}, "meta": {}}

        facets = {}
        meta_stats = {}

        # ── 分面分布统计 ──
        # 分页 scroll 收集所有 points（避免超大集合单次请求过载）
        scroll_limit = 1000
        offset = 0
        all_points = []
        while offset < total_pts:
            try:
                resp = requests.post(
                    f"{QDRANT_URL}/collections/{collection}/points/scroll",
                    json={"limit": scroll_limit, "offset": offset,
                          "with_payload": True, "with_vector": False},
                    timeout=30
                )
                batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
                if not batch:
                    break
                all_points.extend(batch)
                offset += len(batch)
            except Exception:
                break

        # 聚合计数
        ct_count = defaultdict(int)
        domain_count = defaultdict(int)
        tn_count = defaultdict(int)
        ep_count = defaultdict(int)
        trust_sum = 0
        trust_n = 0
        personal_n = 0
        archived_n = 0

        for p in all_points:
            pl = p.get("payload", {})
            ct = pl.get("content_type", "unknown")
            ct_count[ct] += 1

            for d in pl.get("domain", []):
                domain_count[d] += 1

            tn = pl.get("temporal_nature", "")
            if tn:
                tn_count[tn] += 1

            ep = pl.get("epistemic_status", "")
            if ep:
                ep_count[ep] += 1

            ts = pl.get("trust_score")
            if ts is not None:
                trust_sum += ts
                trust_n += 1

            if pl.get("is_personal", False):
                personal_n += 1

            if pl.get("is_archived", False):
                archived_n += 1

        facets["content_type"] = dict(ct_count)
        facets["domain"] = dict(domain_count)
        facets["temporal_nature"] = dict(tn_count)
        facets["epistemic_status"] = dict(ep_count)

        meta_stats["avg_trust"] = round(trust_sum / trust_n, 1) if trust_n > 0 else 0
        meta_stats["personal_count"] = personal_n
        meta_stats["archived_count"] = archived_n

        return {
            "ok": True,
            "total_points": total_pts,
            "facets": facets,
            "meta": meta_stats,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# TODO: 函数 update_metadata 已废弃（无人调用），将在 v0.5.0 删除
def update_metadata(
    doc_id: str,
    updates: dict,
    collection: str = DEFAULT_COLLECTION,
) -> dict:
    """
    更新指定文档所有 chunk 的 Payload 字段。

    参数:
        doc_id: 文档 ID
        updates: 要更新的字段 dict，如 {"trust_score": 5, "is_archived": true}
        collection: 集合名

    返回:
        {"ok": true, "updated": N, "doc_id": "..."}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 1. 找出该 doc_id 的所有 point
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"搜索失败: {resp.status_code}"}

        points = resp.json()["result"]["points"]
        if not points:
            return {"ok": False, "error": f"未找到 doc_id={doc_id} 的记录"}

        # 2. 用 set_payload API 批量更新（key-level merge，不会覆盖其他字段）
        all_point_ids = [p["id"] for p in points]

        put_resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/payload",
            json={"payload": updates, "points": all_point_ids},
            timeout=10
        )
        if put_resp.status_code != 200:
            return {"ok": False, "error": f"更新失败: {put_resp.status_code}"}

        return {"ok": True, "updated": len(points), "doc_id": doc_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# TODO: 函数 set_doc_relations 已废弃（无人调用），将在 v0.5.0 删除
def set_doc_relations(
    doc_id: str,
    add_relations: list = None,
    remove_relations: list = None,
    collection: str = DEFAULT_COLLECTION,
) -> dict:
    """
    管理文档的关系字段。

    参数:
        doc_id: 文档 ID
        add_relations: 要添加的关系列表 [{"type": "similar", "doc_id": "xxx"}, ...]
        remove_relations: 要移除的关系列表（按 {"type": "x", "doc_id": "y"} 匹配）
        collection: 集合名

    返回:
        {"ok": true, "updated": N, "doc_id": "..."}
    """
    add_relations = add_relations or []
    remove_relations = remove_relations or []

    if not add_relations and not remove_relations:
        return {"ok": False, "error": "请提供 add_relations 或 remove_relations"}

    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 获取当前所有 chunk 的当前 relations
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"搜索失败: {resp.status_code}"}

        points = resp.json()["result"]["points"]
        if not points:
            return {"ok": False, "error": f"未找到 doc_id={doc_id} 的记录"}

        # 取第一个 chunk 的 relations 作为基准，做合并
        base_relations = list(points[0].get("payload", {}).get("relations", []))
        for ar in add_relations:
            if ar not in base_relations:
                base_relations.append(ar)
        for rr in remove_relations:
            if rr in base_relations:
                base_relations.remove(rr)

        # 用 set_payload API 批量更新所有该 doc 的 chunk
        all_ids = [p["id"] for p in points]
        put_resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/payload",
            json={"payload": {"relations": base_relations}, "points": all_ids},
            timeout=10
        )
        if put_resp.status_code != 200:
            return {"ok": False, "error": f"更新失败: {put_resp.status_code}"}

        return {"ok": True, "updated": len(points), "doc_id": doc_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def search_by_doc_id(
    doc_id: str,
    collection: str = DEFAULT_COLLECTION,
) -> dict:
    """
    按 doc_id 查找所有 chunk。

    返回:
        {"ok": true, "doc_id": "...", "chunks": [{...}, ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/scroll",
            json={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                "limit": 1000,
                "with_payload": True,
                "with_vector": False,
            },
            timeout=20
        )
        if resp.status_code != 200:
            return {"ok": False, "error": f"搜索失败: {resp.status_code}"}

        points = resp.json()["result"]["points"]
        chunks = []
        for p in points:
            payload = p.get("payload", {})
            chunks.append({
                "text":            payload.get("text", ""),
                "title":           payload.get("title", ""),
                "source":          payload.get("source", "未知"),
                "chunk_index":     payload.get("chunk_index", 0),
                "content_type":    payload.get("content_type", ""),
                "domain":          payload.get("domain", []),
                "temporal_nature": payload.get("temporal_nature", ""),
                "epistemic_status":payload.get("epistemic_status", ""),
                "lifecycle":       payload.get("lifecycle", ""),
                "project_source":  payload.get("project_source", ""),
                "udc_code":        payload.get("udc_code", ""),
                "trust_score":     payload.get("trust_score", 3),
                "is_canonical":    payload.get("is_canonical", True),
                "is_archived":     payload.get("is_archived", False),
                "relations":       payload.get("relations", []),
                "keywords":        payload.get("keywords", []),
                "auto_summary":    payload.get("auto_summary", ""),
                "timeline":        payload.get("timeline", {}),
                "origin":          payload.get("origin", {}),
                "stats":           payload.get("stats", {}),
            })

        return {"ok": True, "doc_id": doc_id, "total": len(chunks), "chunks": chunks}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_doc_ids(
    collection: str = DEFAULT_COLLECTION,
    limit: int = 200,
) -> dict:
    """
    获取集合中的去重 doc_id 列表（用于知识中枢管理）。

    返回:
        {"ok": true, "doc_ids": ["xxx", "yyy", ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 先获取总数
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        total_pts = info.json()["result"]["points_count"] if info.status_code == 200 else 0

        if total_pts == 0:
            return {"ok": True, "doc_ids": []}

        # 分页 scroll：每批 1000，取足去重 doc 或遍历完所有 points
        scroll_limit = 1000
        offset = 0
        seen = set()
        doc_ids = []
        while True:
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "with_payload": True, "with_vector": False},
                timeout=30
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break

            for p in batch:
                did = p.get("payload", {}).get("doc_id", "")
                if did and did not in seen:
                    seen.add(did)
                    doc_ids.append(did)
                    if len(doc_ids) >= limit:
                        break
            offset += len(batch)
            if len(doc_ids) >= limit:
                break
            if len(doc_ids) >= limit:
                break

        return {"ok": True, "doc_ids": doc_ids, "total_unique": len(doc_ids)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════
# ═════════════════════════════════════════
# 文档管理函数 (v4.0)
# ═════════════════════════════════════════

def list_documents(collection: str = DEFAULT_COLLECTION,
                  page: int = 1,
                  page_size: int = 20,
                  needs_review: bool = None) -> dict:
    """
    列出知识库中的去重文档（分页）。
    按 doc_uid 去重，每个文档取 chunk_index=0 的元数据作为代表。

    参数：
        needs_review: 如果为 True/False，只返回对应标记的文档；如果为 None，返回所有文档

    返回：
        {
            "ok": True,
            "documents": [...],
            "total": N,
            "page": 1,
            "page_size": 20,
            "total_pages": N,
        }
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 获取总数
        info = requests.get(f"{QDRANT_URL}/collections/{collection}", timeout=5)
        if info.status_code != 200:
            return {"ok": False, "error": f"集合 {collection} 不存在"}
        total_pts = info.json()["result"]["points_count"]

        if total_pts == 0:
            return {
                "ok": True,
                "documents": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

        # 分页 scroll 收集去重文档（取每个 doc_uid 的第一个 chunk）
        scroll_limit = 1000
        offset = 0
        seen = {}
        # seen[doc_uid] = {metadata from first chunk}

        # 构建 filter（如果 needs_review 不是 None）
        scroll_filter = None
        if needs_review is not None:
            scroll_filter = {
                "must": [
                    {"key": "needs_review", "match": {"value": bool(needs_review)}}
                ]
            }

        while True:
            scroll_body = {
                "limit": scroll_limit,
                "offset": offset,
                "with_payload": True,
                "with_vector": False,
            }
            if scroll_filter:
                scroll_body["filter"] = scroll_filter

            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json=scroll_body,
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break

            for p in batch:
                pl = p.get("payload", {})
                did = pl.get("doc_uid", "")
                if not did:
                    continue
                if did not in seen:
                    seen[did] = {
                        "doc_uid": did,
                        "title": pl.get("title", "") or pl.get("source", "未知"),
                        "source": pl.get("source", ""),
                        "content_type": pl.get("content_type", ""),
                        "domain": pl.get("domain", []),
                        "temporal_nature": pl.get("temporal_nature", ""),
                        "epistemic_status": pl.get("epistemic_status", ""),
                        "trust_score": pl.get("trust_score", 3),
                        "is_personal": pl.get("is_personal", False),
                        "chunk_count": 1,
                        "created_at": pl.get("created_at", ""),
                    }
                else:
                    seen[did]["chunk_count"] += 1

            offset += len(batch)
            if offset >= total_pts:
                break

        # 转成列表，按 created_at 降序
        docs = list(seen.values())
        docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)

        total = len(docs)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "ok": True,
            "documents": docs[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_document(doc_uid: str, collection: str = DEFAULT_COLLECTION) -> dict:
    """
    获取指定文档的所有分块。
    返回：
        {"ok": True, "doc_uid": "...", "chunks": [{text, ...}, ...]}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 使用 scroll + filter 获取该 doc_uid 的所有 points
        all_points = []
        scroll_limit = 1000
        offset = 0

        while True:
            filter_obj = {"must": [{"key": "doc_uid", "match": {"value": doc_uid}}]}
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "filter": filter_obj,
                      "with_payload": True, "with_vector": False},
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break
            all_points.extend(batch)
            offset += len(batch)
            if len(batch) < scroll_limit:
                break

        if not all_points:
            return {"ok": False, "error": f"文档 {doc_uid} 不存在"}

        chunks = []
        for p in all_points:
            pl = p.get("payload", {})
            chunks.append({
                "chunk_index": pl.get("chunk_index", 0),
                "text": pl.get("text", ""),
                "title": pl.get("title", ""),
                "source": pl.get("source", ""),
                "content_type": pl.get("content_type", ""),
                "domain": pl.get("domain", []),
                "images": pl.get("images", []),
            })

        chunks.sort(key=lambda c: c["chunk_index"])
        return {"ok": True, "doc_uid": doc_uid, "chunks": chunks}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_document(doc_uid: str, collection: str = DEFAULT_COLLECTION) -> dict:
    """
    删除指定文档的所有分块。
    返回：
        {"ok": True, "deleted": N}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 先获取所有匹配的点 ID
        point_ids = []
        scroll_limit = 1000
        offset = 0

        while True:
            filter_obj = {"must": [{"key": "doc_uid", "match": {"value": doc_uid}}]}
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "filter": filter_obj,
                      "with_payload": False, "with_vector": False},
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break
            point_ids.extend([p["id"] for p in batch])
            offset += len(batch)
            if len(batch) < scroll_limit:
                break

        if not point_ids:
            return {"ok": False, "error": f"文档 {doc_uid} 不存在"}

        # 批量删除（每批 1000）
        deleted = 0
        for i in range(0, len(point_ids), 1000):
            batch_ids = point_ids[i:i+1000]
            del_resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/delete",
                json={"points": batch_ids},
                timeout=30,
            )
            if del_resp.status_code == 200:
                deleted += len(batch_ids)

        return {"ok": True, "deleted": deleted, "doc_uid": doc_uid}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def update_document(doc_uid: str, metadata: dict,
                   collection: str = DEFAULT_COLLECTION) -> dict:
    """
    更新指定文档所有分块的元数据。
    metadata 中的字段会覆盖所有分块的对应字段。

    返回：
        {"ok": True, "updated": N}
    """
    if not _check_qdrant():
        return {"ok": False, "error": "Qdrant 未运行"}

    try:
        # 先获取所有匹配的点
        all_points = []
        scroll_limit = 1000
        offset = 0

        while True:
            filter_obj = {"must": [{"key": "doc_uid", "match": {"value": doc_uid}}]}
            resp = requests.post(
                f"{QDRANT_URL}/collections/{collection}/points/scroll",
                json={"limit": scroll_limit, "offset": offset,
                      "filter": filter_obj,
                      "with_payload": True, "with_vector": True},
                timeout=30,
            )
            batch = resp.json()["result"]["points"] if resp.status_code == 200 else []
            if not batch:
                break
            all_points.extend(batch)
            offset += len(batch)
            if len(batch) < scroll_limit:
                break

        if not all_points:
            return {"ok": False, "error": f"文档 {doc_uid} 不存在"}

        # 更新 payload
        updated = 0
        for p in all_points:
            pid = p["id"]
            vector = p.get("vector", [])
            payload = p.get("payload", {})
            payload.update(metadata)
            # 写回 Qdrant（覆盖原 point）
            requests.put(
                f"{QDRANT_URL}/collections/{collection}/points",
                json={
                    "points": [{"id": pid, "vector": vector, "payload": payload}]
                },
                timeout=30,
            )
            updated += 1

        return {"ok": True, "updated": updated, "doc_uid": doc_uid}

    except Exception as e:
        return {"ok": False, "error": str(e)}


# ═════════════════════════════════════════
# CLI 入口
# ═════════════════════════════════════════

if __name__ == "__main__":
    # 修复 Windows GBK 环境下 print 非 ASCII 字符崩溃问题
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description="WorkBuddy 知识库引擎")
    parser.add_argument("query", nargs="*", help="搜索查询")
    parser.add_argument("--top", type=int, default=5, help="返回结果数")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="集合名称")
    parser.add_argument("--ingest", default=None, help="摄入文件路径")
    parser.add_argument("--text", default=None, help="直接摄入文本内容（与 --source 配合）")
    parser.add_argument("--ocr", default=None, help="OCR 图片路径")
    parser.add_argument("--engine", default="paddle", choices=["paddle", "tesseract", "structured"], help="OCR 引擎")
    parser.add_argument("--check-only", action="store_true", help="只 OCR 不入库")
    parser.add_argument("--llm-optimize", action="store_true", help="用LLM优化OCR结果（自动修复错别字）")
    parser.add_argument("--source", default=None, help="来源标识")
    parser.add_argument("--answer", action="store_true", help="端到端问答")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名")
    parser.add_argument("--llm-base-url", default=None, help="LLM API 地址")
    parser.add_argument("--llm-api-key", default=None, help="LLM API Key")
    parser.add_argument("--threshold", type=float, default=0.3, help="相关度阈值")
    parser.add_argument("--table-split-threshold", type=int, default=None, help="表格行拆分阈值（默认用 TABLE_SPLIT_THRESHOLD）")
    parser.add_argument("--model", default=EMBED_MODEL, help="嵌入模型")
    parser.add_argument("--output", default=None, help="输出目录")
    args = parser.parse_args()

    query_str = " ".join(args.query) if isinstance(args.query, list) else args.query

    if args.ocr:
        # 导入OCR工作流
        try:
            from ocr_workflow import do_ocr
            do_ocr(
                image_path=args.ocr,
                source=args.source or "",
                engine=args.engine,
                check_only=args.check_only,
                collection=args.collection,
                model=args.model,
                llm_optimize=args.llm_optimize,
                llm_api_key=args.llm_api_key or os.environ.get("KB_LLM_API_KEY", ""),
                llm_base_url=args.llm_base_url or os.environ.get("KB_LLM_BASE_URL", ""),
                llm_model=args.llm_model or os.environ.get("KB_LLM_MODEL", "deepseek-chat")
            )
        except ImportError:
            print("❌ 错误: ocr_workflow.py 未找到。请确保 ocr_workflow.py 在同一目录下。")
            sys.exit(1)
    elif args.ingest:
        result = ingest(file_path=args.ingest, metadata={"source": args.source or ""}, collection=args.collection, model=args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.text and args.source:
        result = ingest(text=args.text, metadata={"source": args.source}, collection=args.collection, model=args.model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif query_str and args.answer:
        result = answer(
            query_str,
            top_k=args.top,
            collection=args.collection,
            model=args.model,
            threshold=args.threshold,
            llm_model=args.llm_model,
            llm_base_url=args.llm_base_url,
            llm_api_key=args.llm_api_key,
            output_dir=args.output,
            table_split_threshold=args.table_split_threshold
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif query_str:
        result = search(
            query_str,
            top_k=args.top,
            collection=args.collection,
            model=args.model,
            score_threshold=args.threshold
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()
