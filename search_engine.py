# flake8: noqa: E501
"""Search Engine — 语义搜索 / LLM 问答合成 / HTML 报告渲染

Extracted from kb_query.py (A4 refactor).

架构:
  搜索: 自然语言 → 向量检索 → Qdrant
  问答: 搜索结果 → LLM API → 程序渲染 HTML (KaTeX)
  报告: HTML 含公式渲染/图片嵌入/表格分页 → PDF
"""
import requests
import json
import os
import re
import subprocess
import io
import base64
import math
import tempfile
import html
import hashlib
from collections import defaultdict
from typing import Optional
from datetime import datetime, timezone

from qconst import (
    QDRANT_URL, DEFAULT_COLLECTION, PROJECT_DIR,
    _check_qdrant, OLLAMA_URL, EMBED_MODEL, EMBED_DIM,
    SEARCH_TOP_K, SEARCH_SCORE_THRESHOLD,
    RERANK_ENABLED, RERANK_MODEL, RERANK_TOP_N,
    TABLE_SPLIT_THRESHOLD,
)
from qdrant_client import _ensure_collection
from text_pipeline import _embed
from reranker import rerank_results, rerank_results_simple
from sparse_encoder import encode_sparse_query

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


# TABLE_SPLIT_THRESHOLD — 从 pipe_cfg.yaml 统一导入（见 qconst 顶部）

# 有效过滤键（facet_filter 参数校验用）
_VALID_FILTER_KEYS = {"content_type","domain","knowledge_type","tags","temporal_nature","epistemic_status","lifecycle","is_personal","trust_score_min"}


def _build_qdrant_filter(facet_filter: dict) -> dict:
    """从 facet_filter 构建 Qdrant 过滤条件（must 数组）。"""
    if not facet_filter:
        return None
    _invalid_keys = set(facet_filter.keys()) - _VALID_FILTER_KEYS
    if _invalid_keys:
        print(f"[Search] facet_filter invalid keys (ignored): {_invalid_keys}")
    must_conditions = []

    def _add_match(key, vals):
        must_conditions.append({
            "key": key,
            "match": {"value": vals[0]} if len(vals) == 1 else {"any": vals}
        })

    for key in ("content_type", "domain", "knowledge_type", "tags"):
        if facet_filter.get(key):
            _add_match(key, facet_filter[key])

    for key in ("temporal_nature", "epistemic_status", "lifecycle"):
        if facet_filter.get(key):
            must_conditions.append({
                "key": key,
                "match": {"value": facet_filter[key]}
            })

    if "is_personal" in facet_filter:
        must_conditions.append({
            "key": "is_personal",
            "match": {"value": facet_filter["is_personal"]}
        })

    if facet_filter.get("trust_score_min") is not None:
        must_conditions.append({
            "key": "trust_score",
            "range": {"gte": facet_filter["trust_score_min"]}
        })

    return {"must": must_conditions} if must_conditions else None


def _query_qdrant_rrf(
    query: str,
    query_vec: list,
    top_k: int,
    qdrant_filter: dict,
    score_threshold: float,
    collection: str = DEFAULT_COLLECTION,
) -> list:
    """执行 Qdrant RRF 混合查询 + 重排序，返回结果列表。"""
    # ── 生成稀疏查询向量 ──
    sparse_query = None
    try:
        sparse_query = encode_sparse_query(query)
    except Exception as e:
        print(f"[Search] 稀疏查询向量生成失败（降级为纯稠密搜索）: {e}")

    # ── 搜索 Qdrant（原生混合查询：稠密 + 稀疏 → RRF 融合）──
    try:
        prefetch = []
        if sparse_query:
            prefetch.append({
                "query": {"indices": sparse_query[0], "values": sparse_query[1]},
                "using": "bm25",
                "limit": top_k * 2,
            })
        prefetch.append({
            "query": query_vec,
            "using": "dense",
            "limit": top_k * 2,
        })

        query_body = {
            "prefetch": prefetch,
            "query": {"fusion": "rrf"},
            "limit": top_k,
            "with_payload": True,
        }
        if qdrant_filter:
            query_body["filter"] = qdrant_filter
            query_body["params"] = {"acorn": {"enable": True, "max_selectivity": 0.4}}

        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/query",
            json=query_body,
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json()["result"]["points"]

        # 后过滤
        if score_threshold and score_threshold > 0:
            filtered = [r for r in results if r.get("score", 0) >= score_threshold]
            if filtered:
                results = filtered

        # 重排序
        try:
            if RERANK_ENABLED:
                results = rerank_results(query=query, results=results,
                                       model=RERANK_MODEL, top_n=RERANK_TOP_N)
        except Exception as e:
            print(f"[Search] 重排序失败: {e}，尝试简单重排序")
            try:
                results = rerank_results_simple(query, results, top_n=RERANK_TOP_N)
            except Exception as e2:
                print(f"[Search] 简单重排序也失败: {e2}，使用原始排序")
        return results
    except Exception as e:
        raise e


def _img_tag(img_path: str, max_w: int = 700) -> str:
    """将图片路径转为 base64 <img> 标签，失败返回原路径 file:// 引用。"""
    b64 = _img_to_b64(img_path, max_w=max_w)
    if b64:
        return f'<br><img src="{b64}" class="evidence-img"><br>'
    return f'<br><img src="file://{html.escape(img_path)}" class="evidence-img"><br>'


def _cell_html(raw: str) -> str:
    """处理 table cell: 先转义HTML防XSS，再还原公式和图片引用。"""
    s = html.escape(raw)
    s = _formula_to_html_spans(s)
    s = re.sub(r'\[image:\s*(.+?)\]', lambda m: _img_tag(m.group(1).strip()), s)
    return s


def _pipe_table_to_html(pipe_lines: list) -> str:
    """将 Markdown 管道表格行列表转为 HTML <table>。列宽由内容预计算。"""
    rows = []
    for pl in pipe_lines:
        cells = pl.strip().strip('|').split('|')
        rows.append([c.strip() for c in cells])
    data_rows = [rows[0]] + rows[2:]
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


def _format_evidence_text(text: str) -> str:
    """格式化原始素材文本为 HTML：表格自动转 <table>，公式/图片引用包裹。"""
    lines = text.split('\n')
    pipe_lines = [l for l in lines if l.strip().startswith('|')]
    if len(pipe_lines) >= 3 and '---' in pipe_lines[1]:
        return _pipe_table_to_html(pipe_lines)
    result = []
    for line in lines:
        escaped = html.escape(line)
        escaped = re.sub(r'\[image:\s*([^\]]+)\]', lambda m: _img_tag(m.group(1).strip()), escaped)
        escaped = _formula_to_html_spans(escaped)
        result.append(escaped)
    return '\n'.join(result)


def search(
    query: str,
    top_k: int = None,
    collection: str = DEFAULT_COLLECTION,
    score_threshold: float = None,
    model: str = None,
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

    # 默认值从 pipe_cfg.yaml 读取（参数显式传入时优先）
    if top_k is None:
        top_k = SEARCH_TOP_K
    if score_threshold is None:
        score_threshold = SEARCH_SCORE_THRESHOLD
    if model is None:
        model = EMBED_MODEL

    # 嵌入查询
    try:
        query_vec = _embed([query], model=model)[0]
    except Exception as e:
        return {"ok": False, "error": f"嵌入查询失败: {e}"}

    # 构建过滤条件（分面过滤）
    qdrant_filter = _build_qdrant_filter(facet_filter)

    # ── 搜索 Qdrant（原生混合查询：稠密 + 稀疏 → RRF 融合）──
    try:
        results = _query_qdrant_rrf(query, query_vec, top_k, qdrant_filter, score_threshold, collection)
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
            "content_hash":    payload.get("content_hash", ""),
            "doc_uid":        payload.get("doc_uid", ""),
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
            # 重排序分数（如果有）
            "rerank_score":   r.get("rerank_score", None),
        })

    # ── v0.8.0: Grouping API — 按 doc_id 分组去重，每文档只保留最佳 chunk ──
    if chunks:
        doc_groups = {}
        for c in chunks:
            did = c["doc_id"]
            if did not in doc_groups or c["score"] > doc_groups[did]["score"]:
                doc_groups[did] = c
            # 统计该文档在结果中出现的 chunk 数
            doc_groups[did]["_chunks_in_results"] = doc_groups[did].get("_chunks_in_results", 0) + 1
        grouped = sorted(doc_groups.values(), key=lambda c: c["score"], reverse=True)
        # 附加分组元信息
        for c in grouped:
            c["group_chunks_count"] = c.pop("_chunks_in_results", 1)
        chunks = grouped

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
            "temperature": 0,
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
    
    D5 修复：支持相对路径（相对于 PROJECT_DIR）
    """
    # D5 修复：如果路径是相对的，转换为绝对路径
    if not os.path.isabs(img_path):
        img_path = os.path.join(PROJECT_DIR, img_path)
    
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
    top_k: int = None,
    collection: str = DEFAULT_COLLECTION,
    model: str = None,
    threshold: float = None,
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
    # 默认值从 pipe_cfg.yaml 读取（参数显式传入时优先）
    if top_k is None:
        top_k = SEARCH_TOP_K
    if model is None:
        model = EMBED_MODEL
    if threshold is None:
        threshold = SEARCH_SCORE_THRESHOLD
    if table_split_threshold is None:
        table_split_threshold = TABLE_SPLIT_THRESHOLD
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
# 分面统计（知识中枢仪表盘）
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
        # S5 fix: 边 scroll 边聚合，不积累全量 points 到内存
        scroll_limit = 1000
        offset = 0
        ct_count = defaultdict(int)
        domain_count = defaultdict(int)
        tn_count = defaultdict(int)
        ep_count = defaultdict(int)
        trust_sum = 0
        trust_n = 0
        personal_n = 0
        archived_n = 0

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
                # 逐批聚合，不保存到内存
                for p in batch:
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

                offset += len(batch)
            except Exception:
                break

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
