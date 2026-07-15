# flake8: noqa: E501
"""Classify Pipeline — 三层管道自动标注引擎

Extracted from kb_query.py (A5 refactor).

管道:
  Layer 1: 文件元数据 + 规则引擎 并行推断
  Layer 2: 合并仲裁 (file > rule > LLM > default) + LLM 兜底缺口
  Layer 3: 程序计算置信度 (非 LLM 自报)

主要函数:
  classify_document() — 入口，返回 AnnotatedField 结构
  auto_classify()    — 薄包装，向后兼容旧调用方
"""
import json
import re
import os
import logging
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

from config.classifications import normalize_facet_values, CLASSIFY_RULES
from search_engine import _call_llm_api, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from utils.llm_helpers import extract_json_block as _extract_json_block
from text_pipeline import detect_language, parse_frontmatter


def route_by_confidence(overall_conf: float, conf_low: float, conf_high: float) -> tuple:
    """
    置信度三档路由。
    返回 (needs_review, should_dlq)。

    调用方: pages/ingest.py, watcher/processor.py
    """
    if overall_conf >= conf_high:
        return False, False
    elif overall_conf >= conf_low:
        return True, False
    else:
        return False, True


# ═══════════════════════════════════════════
# 阶段二：标签形成引擎 — 三层管道
# Layer 1: 📎文件元数据 + 📐规则引擎 并行推断
# Layer 2: 合并仲裁 (file > rule > LLM > default) + LLM 兜底缺口
# Layer 3: 程序计算置信度 (非 LLM 自报)
# ═══════════════════════════════════════════

# ── T1: 核心数据结构常量 ──

# 来源置信度：每个来源固有的可信度
SOURCE_CONFIDENCE = {
    "file":    1.0,   # 文件自带元数据，最可信
    "rule":    0.85,  # 规则引擎命中，确定性高
    "llm":     0.60,  # LLM 推断 (temp=0 确定性，但语义有不确定性)
    "user":    1.0,   # 用户手动确认
    "default": 0.0,   # 智能默认值，未经验证
}

# 分面字段权重：用于计算整体置信度
FIELD_WEIGHTS = {
    "content_type":     0.25,
    "domain":           0.25,
    "temporal_nature":  0.20,
    "epistemic_status": 0.20,
    "keywords":         0.10,
}

# 必填分面字段列表
REQUIRED_FACET_FIELDS = ["content_type", "domain", "temporal_nature", "epistemic_status"]

# 智能默认值
SMART_DEFAULTS = {
    "content_type":     "knowledge",
    "domain":           [],
    "temporal_nature":  "timeboxed",
    "epistemic_status": "unverified",
    "lifecycle":        "published",
    "trust_score":      3,
    "keywords":         [],
    "title":            "",
    "author":           "",
    "auto_summary":     "",
    "is_personal":      False,
    "knowledge_type":   "",
    "udc_code":         "",
}


def _make_field(value, source: str, conf: float = None) -> dict:
    """创建一个带来源和置信度的字段。"""
    return {
        "value": value,
        "source": source,
        "confidence": conf if conf is not None else SOURCE_CONFIDENCE.get(source, 0.0),
    }


# ── T2: 规则引擎 ──

def match_rules(text: str, field_name: str) -> tuple:
    """
    对指定分面字段做规则匹配。
    
    返回:
        (value, source) — 命中时 value=规则值, source="rule"
        (None, None)    — 未命中
    
    注意: domain 是多选字段，返回的是 list（所有命中值的去重列表）。
    """
    rules = CLASSIFY_RULES.get(field_name, [])
    text_lower = text.lower()
    
    # domain 是多选 — 收集所有命中值
    if field_name == "domain":
        matched = []
        for rule in rules:
            hit = False
            for kw in rule["keywords"]:
                if kw.lower() in text_lower:
                    hit = True
                    break
            if not hit:
                for pattern in rule.get("patterns", []):
                    if re.search(pattern, text, re.IGNORECASE):
                        hit = True
                        break
            if hit and rule["value"] not in matched:
                matched.append(rule["value"])
        if matched:
            return matched, "rule"
        return None, None
    
    # 其他字段单选 — 返回第一个命中
    for rule in rules:
        for kw in rule["keywords"]:
            if kw.lower() in text_lower:
                return rule["value"], "rule"
        for pattern in rule.get("patterns", []):
            if re.search(pattern, text, re.IGNORECASE):
                return rule["value"], "rule"
    return None, None


def match_all_rules(text: str) -> dict:
    """
    对全部 4 个分面字段做规则匹配，返回带来源标记的字段字典。
    
    返回:
        {
            "content_type":     AnnotatedField | None,
            "domain":           AnnotatedField | None,
            "temporal_nature":  AnnotatedField | None,
            "epistemic_status": AnnotatedField | None,
        }
        未命中的字段值为 None。
    """
    result = {}
    for field in REQUIRED_FACET_FIELDS:
        value, source = match_rules(text, field)
        if value is not None:
            result[field] = _make_field(value, source)
        else:
            result[field] = None
    return result


def extract_file_fields(file_metadata: dict) -> dict:
    """
    从文件元数据中提取可用字段（📎 file 来源）。
    
    文件元数据可能包含: title, author, content_type, keywords, source 等。
    只提取确实有值的字段。
    """
    if not file_metadata:
        return {}
    
    result = {}
    # title, author — 文件自带的标题和作者
    if file_metadata.get("title"):
        result["title"] = _make_field(file_metadata["title"], "file")
    if file_metadata.get("author"):
        result["author"] = _make_field(file_metadata["author"], "file")
    
    # content_type — 文件元数据可能指定类型
    if file_metadata.get("content_type"):
        result["content_type"] = _make_field(file_metadata["content_type"], "file")
    
    # keywords — 文件元数据可能包含关键词
    if file_metadata.get("keywords"):
        kws = file_metadata["keywords"]
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",") if k.strip()]
        result["keywords"] = _make_field(kws, "file")
    
    return result


# ── T3: LLM 兜底 — 仅对缺口字段调用 LLM ──

def call_llm_for_missing(text: str, missing_fields: list) -> dict:
    """
    调用 LLM 推断指定缺口字段（temperature=0，确定性输出）。
    LLM 只生成 missing_fields 中列出的字段，不生成 confidence。
    
    返回:
        dict — {"field_name": value, ...} 扁平值字典（不含来源标记）
        失败返回空 dict
    """
    if not missing_fields:
        return {}
    
    api_key = os.environ.get("KB_LLM_API_KEY") or LLM_API_KEY
    if not api_key:
        return {}
    
    sample = text[:5000].strip()
    if not sample:
        return {}
    
    from config.classifications import (
        CONTENT_TYPES, DOMAINS, TEMPORAL_NATURE, EPISTEMIC_STATUS,
        KNOWLEDGE_TYPES, TRUST_SCORE_LABELS,
    )
    
    # 动态构建 prompt — 只要求 missing_fields 中的字段
    field_descriptions = []
    if "content_type" in missing_fields:
        ct_list = "\n".join(f"  - {k}: {v}" for k, v in CONTENT_TYPES.items())
        field_descriptions.append(f'### content_type — 单选：\n{ct_list}')
    if "domain" in missing_fields:
        domain_list = "\n".join(f"  - {k}: {v}" for k, v in DOMAINS.items())
        field_descriptions.append(f'### domain — 可多选 0-3 个，不相关就空数组 []：\n{domain_list}')
    if "temporal_nature" in missing_fields:
        temporal_list = "\n".join(f"  - {k}: {v}" for k, v in TEMPORAL_NATURE.items())
        field_descriptions.append(f'### temporal_nature — 单选：\n{temporal_list}')
    if "epistemic_status" in missing_fields:
        epistemic_list = "\n".join(f"  - {k}: {v}" for k, v in EPISTEMIC_STATUS.items())
        field_descriptions.append(f'### epistemic_status — 单选：\n{epistemic_list}')
    if "keywords" in missing_fields:
        field_descriptions.append('### keywords — 3-8 个技术术语或关键概念')
    if "title" in missing_fields:
        field_descriptions.append('### title — 简要标题，不超过 50 字')
    if "author" in missing_fields:
        field_descriptions.append('### author — 作者/出处，没有则留空 ""')
    if "auto_summary" in missing_fields:
        field_descriptions.append('### auto_summary — 一句话摘要，不超过 100 字')
    if "trust_score" in missing_fields:
        trust_labels = "\n".join(f"  {k}: {v}" for k, v in TRUST_SCORE_LABELS.items())
        field_descriptions.append(f'### trust_score — 0-5 整数：\n{trust_labels}')
    if "knowledge_type" in missing_fields:
        ktype_list = "\n".join(f"  - {k}: {v}" for k, v in KNOWLEDGE_TYPES.items())
        field_descriptions.append(f'### knowledge_type — 单选：\n{ktype_list}')
    if "udc_code" in missing_fields:
        field_descriptions.append('### udc_code — UDC 细分码，如 "621"，不确定留空 ""')
    if "is_personal" in missing_fields:
        field_descriptions.append('### is_personal — true=个人经验/笔记，false=客观内容')
    if "lifecycle" in missing_fields:
        field_descriptions.append('### lifecycle — published/draft/review 等')
    
    # 构建示例 JSON — 只包含 missing_fields
    example_fields = {}
    for f in missing_fields:
        if f == "domain":
            example_fields[f] = ["0"]
        elif f == "keywords":
            example_fields[f] = ["关键词1", "关键词2"]
        elif f == "trust_score":
            example_fields[f] = 3
        elif f == "is_personal":
            example_fields[f] = False
        else:
            example_fields[f] = "value"
    example_json = json.dumps(example_fields, ensure_ascii=False)
    
    prompt = f"""你是一个知识分类专家。请分析以下文本，只填写以下字段：{", ".join(missing_fields)}

## 文本内容
{sample}

## 需要填写的字段
{chr(10).join(field_descriptions)}

## 输出格式
严格输出以下 JSON，不要包含任何额外文字、不要用 ```json 包裹：
{example_json}"""
    
    try:
        raw = _call_llm_api(
            [{"role": "user", "content": prompt}],
            base_url=os.environ.get("KB_LLM_BASE_URL") or LLM_BASE_URL,
            api_key=api_key,
            model=os.environ.get("KB_LLM_MODEL") or LLM_MODEL,
        )
    except Exception as e:
        logger.warning(f"call_llm_for_missing failed: {e}")
        return {}
    
    result = _extract_json_block(raw)
    if result is None:
        return {}
    
    # 只取 missing_fields 中的字段
    return {k: v for k, v in result.items() if k in missing_fields}


# ── T4: 合并仲裁 ──

def merge_parallel(file_fields: dict, rule_fields: dict) -> dict:
    """
    合并文件源和规则源的结果（并行产出，file 优先）。
    
    对每个字段：
        - 两源都有值 → file 优先 (file > rule)
        - 只有一源有值 → 用该源
        - 两源都没值 → 该字段为 None（等 LLM 兜底或 default）
    
    返回带来源标记的字段字典，未覆盖的字段值为 None。
    """
    all_keys = set(REQUIRED_FACET_FIELDS) | set(file_fields.keys()) | set(rule_fields.keys())
    merged = {}
    for key in all_keys:
        file_val = file_fields.get(key)
        rule_val = rule_fields.get(key)
        if file_val is not None:
            merged[key] = file_val
        elif rule_val is not None:
            merged[key] = rule_val
        else:
            merged[key] = None
    return merged


def fill_defaults(annotated: dict) -> dict:
    """
    对仍为 None 的字段填入智能默认值 (⚙️ default)。
    """
    for key, default_val in SMART_DEFAULTS.items():
        if annotated.get(key) is None or (isinstance(annotated.get(key), dict) and annotated[key].get("value") is None):
            annotated[key] = _make_field(default_val, "default")
    return annotated


# ── T5: 置信度计算 ──

def calculate_confidence(annotated: dict) -> float:
    """
    程序计算整体置信度：Σ(字段权重 × 字段来源置信度)。
    
    非分面字段（title/author/auto_summary 等）不参与计算，
    但影响是否调用 LLM（有值就不调用）。
    """
    total = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        field_data = annotated.get(field)
        if field_data and isinstance(field_data, dict):
            total += weight * field_data.get("confidence", 0.0)
    return round(total, 2)


def _validate_and_normalize_merged(merged: dict) -> dict:
    """
    验证并规范化 merged 字典中的字段值。
    
    处理:
        1. normalize 4 个分面字段（枚举守卫）
        2. 校验 keywords 是 list
        3. 校验 title/author/auto_summary 是 str
        4. 校验 is_personal 是 bool
        5. 校验 trust_score 是 0-5 int
    
    原地修改 merged，并返回。
    """
    # ── normalize 分面字段 ──
    flat_for_normalize = {}
    for f in REQUIRED_FACET_FIELDS:
        fd = merged.get(f)
        if fd and isinstance(fd, dict):
            flat_for_normalize[f] = fd.get("value")
    normalize_facet_values(flat_for_normalize)
    for f in REQUIRED_FACET_FIELDS:
        if merged.get(f) and isinstance(merged[f], dict):
            merged[f]["value"] = flat_for_normalize.get(f, merged[f]["value"])
    
    # ── 校验 keywords 是 list ──
    kw_field = merged.get("keywords")
    if kw_field and isinstance(kw_field, dict):
        kw_val = kw_field.get("value", [])
        if not isinstance(kw_val, list):
            kw_val = [str(kw_val)] if kw_val else []
        kw_val = [str(k).strip()[:50] for k in kw_val if k]
        kw_field["value"] = kw_val
    
    # ── 校验 title/author/auto_summary 是 str ──
    for str_field in ["title", "author", "auto_summary"]:
        fd = merged.get(str_field)
        if fd and isinstance(fd, dict):
            fd["value"] = str(fd.get("value", "")).strip()[:200 if str_field == "auto_summary" else 100]
    
    # ── 校验 is_personal 是 bool ──
    ip_fd = merged.get("is_personal")
    if ip_fd and isinstance(ip_fd, dict):
        ip_val = ip_fd.get("value", False)
        if isinstance(ip_val, str):
            ip_fd["value"] = ip_val.strip().lower() in ("true", "yes", "1")
        else:
            ip_fd["value"] = bool(ip_val)
    
    # ── 校验 trust_score 是 0-5 int ──
    ts_fd = merged.get("trust_score")
    if ts_fd and isinstance(ts_fd, dict):
        try:
            ts_fd["value"] = max(0, min(5, int(ts_fd.get("value", 3))))
        except (ValueError, TypeError):
            ts_fd["value"] = 3
    
    return merged


# ── T6: classify_document() 主函数 ──

def classify_document(text: str, file_metadata: dict = None, project_source: str = "通用") -> dict:
    """
    阶段二标签形成主函数 — 三层管道。
    
    Layer 1: 📎文件元数据 + 📐规则引擎 并行推断（互不依赖）
    Layer 2: 合并仲裁 (file > rule) → 识别缺口 → 🤖LLM 兜底 (temp=0, 仅缺口) → ⚙️default 填剩余
    Layer 3: 程序计算置信度
    
    返回:
        {
            "ok": true/false,
            "classification": {  # 扁平值字典（兼容旧接口）
                "content_type", "domain", "temporal_nature", "epistemic_status",
                "keywords", "title", "author", "auto_summary", "trust_score",
                "knowledge_type", "udc_code", "is_personal", "lifecycle",
                "confidence": {"overall": float},
            },
            "annotated": {  # 带来源标记的完整结构（新接口）
                "content_type": AnnotatedField, ...
                "field_sources": {"content_type": "rule", ...},
                "overall_confidence": float,
            },
            "raw_response": "LLM原始输出(调试用, 可能为空)",
        }
    """
    # ── Layer 0.5: 解析中转文件 frontmatter（标题/作者作为文件真相源，抑制 LLM 漂移）──
    # 单一入口：watch / 网页上传 / 死信重摄入 都经 classify_document，frontmatter 在此统一解析，
    # 杜绝"漏改某个调用点"导致的标题/作者漂移。调用方已显式传入则保留（watcher/网页上传现状不变）。
    text, _fm = parse_frontmatter(text)
    file_metadata = dict(file_metadata or {})
    if _fm.get("title") and not file_metadata.get("title"):
        file_metadata["title"] = _fm["title"]
    if _fm.get("up_name") and not file_metadata.get("author"):
        file_metadata["author"] = _fm["up_name"]
    if _fm.get("source_url") and not file_metadata.get("source_url"):
        file_metadata["source_url"] = _fm["source_url"]

    # ── Layer 1: 两个源并行跑，互不依赖 ──
    file_fields = extract_file_fields(file_metadata)
    rule_fields = match_all_rules(text)
    
    # ── Layer 2: 合并 + 识别缺口 ──
    merged = merge_parallel(file_fields, rule_fields)
    
    # 识别仍为 None 或空值的分面字段 + 可选字段
    missing_facets = []
    for f in REQUIRED_FACET_FIELDS:
        field_data = merged.get(f)
        if field_data is None or (isinstance(field_data, dict) and not field_data.get("value")):
            missing_facets.append(f)
    
    # 可选字段也尝试让 LLM 补充
    optional_for_llm = ["keywords", "title", "author", "auto_summary", "trust_score",
                        "knowledge_type", "udc_code", "is_personal", "lifecycle"]
    missing_optional = [f for f in optional_for_llm if merged.get(f) is None]
    
    all_missing = missing_facets + missing_optional
    
    # LLM 只在有缺口时才调用，且只生成缺口字段
    raw_response = ""
    if all_missing:
        llm_result = call_llm_for_missing(text, all_missing)
        raw_response = str(llm_result) if llm_result else ""
        
        # 将 LLM 结果填入 merged（标记来源为 llm）
        for field, value in llm_result.items():
            if value is not None and value != "":
                merged[field] = _make_field(value, "llm")
    
    # 填充默认值
    fill_defaults(merged)
    
    # ── 验证并规范化所有字段值 ──
    _validate_and_normalize_merged(merged)
    
    # ── 闪念联动：content_type=idea → lifecycle=idea（覆盖默认的 published）──
    _ct = merged.get("content_type")
    if _ct and isinstance(_ct, dict) and _ct.get("value") == "idea":
        _lc = merged.get("lifecycle")
        if _lc and isinstance(_lc, dict):
            _lc["value"] = "idea"
    
    # ── Layer 3: 程序计算置信度 ──
    overall_conf = calculate_confidence(merged)
    
    # 构建 field_sources 字典
    field_sources = {}
    for key, fd in merged.items():
        if fd and isinstance(fd, dict):
            field_sources[key] = fd.get("source", "default")
    
    # 构建扁平 classification（兼容旧接口）
    classification = {}
    for key in REQUIRED_FACET_FIELDS + ["keywords", "title", "author", "auto_summary",
                                         "trust_score", "knowledge_type", "udc_code",
                                         "is_personal", "lifecycle"]:
        fd = merged.get(key)
        if fd and isinstance(fd, dict):
            classification[key] = fd.get("value")
        else:
            classification[key] = SMART_DEFAULTS.get(key)
    
    classification["confidence"] = {"overall": overall_conf}

    # ── Layer 0: 系统自动填（language / project_source / source）──
    # 这些字段不参与 file > rule > llm 流程，由系统直接确定
    lang = detect_language(text)
    classification["language"] = lang

    classification["project_source"] = project_source

    if file_metadata and file_metadata.get("source"):
        src = file_metadata["source"]
    elif file_metadata:
        # 文件上传但没有显式 source — 用文件名或默认描述
        src_path = file_metadata.get("source_path", "")
        src = f"文件: {os.path.basename(src_path)}" if src_path else "文件上传"
    else:
        src = "手动输入"
    classification["source"] = src

    # 将 Layer 0 字段写入 merged（使 annoteted 也包含它们）
    merged["language"] = _make_field(lang, "system")
    merged["project_source"] = _make_field(project_source, "system")
    merged["source"] = _make_field(src, "system")

    return {
        "ok": True,
        "classification": classification,
        "annotated": {
            **merged,
            "field_sources": field_sources,
            "overall_confidence": overall_conf,
        },
        "raw_response": raw_response,
    }


def auto_classify(text: str, metadata: dict = None) -> dict:
    """
    兼容包装：调用 classify_document() 并返回与旧接口兼容的结构。
    
    阶段二已将标签形成逻辑重构为 classify_document() 三层管道。
    此函数保留以兼容现有调用方（main.py 等），内部转发到新实现。
    """
    result = classify_document(text, file_metadata=metadata)
    # 旧接口不返回 "annotated" 键，只返回 classification + raw_response
    return {
        "ok": result.get("ok", False),
        "classification": result.get("classification", {}),
        "annotated": result.get("annotated", {}),
        "raw_response": result.get("raw_response", ""),
    }



