"""
Citrinitas 分面分类 + 完整字段定义 — Faceted Classification Schema v5.1

设计原则：
  - 分面分类（Faceted Classification）替代传统层级分类法
  - 4个独立分面：内容类型 / 主题域(UDC) / 时效属性 / 认知验证状态
  - 分组字段：relations / timeline / origin / stats（语义聚拢，减少字段数）
  - 每个分面的值可独立扩展，无需修改数据结构
  - 总字段数：36 个（28 个活跃字段 + 10 个预留扩展槽位）
  - 所有活跃字段 100% 自动填充，字段来源分四象限（见下方）

存储方案：单集合（athanor_v1）+ Payload 过滤

═══════════════════════════════════════════
字段来源四象限（Field Source Classification）
═══════════════════════════════════════════

象限一 — 文件自带（File-originated，置信度 1.0）
  从文件元数据层提取，优先级最高。当与 AI 推断冲突时，文件自带优先。
  字段: title, origin.author, origin.source_url, origin.file_type, source,
        timeline.published, version, timeline.effective

象限二 — AI 推断（AI-inferred，置信度由 LLM 返回）
  LLM 分析文本语义推断。当文件无对应元数据时，AI 作为后备来源。
  字段: content_type, domain, temporal_nature, epistemic_status, udc_code,
        keywords, auto_summary, trust_score, knowledge_type, is_personal, lifecycle

象限三 — 程序自动生成（System-generated，置信度 1.0）
  纯代码逻辑，确定性输出。
  字段: doc_id, content_hash, text, chunk_index, images, language,
        timeline.ingested, timeline.accessed, stats.access_count, stats.starred,
        origin.ingest_method, is_canonical, access_level, is_archived, batch_id

象限四 — 智能默认值（Smart defaults，置信度 0.0）
  当前无法自动确定，填入占位值等待未来进化。
  字段: project_source, target_platform, related_product, tags, relations,
        timeline.expiry, + 10 预留扩展槽位

填充优先级: 文件自带 > AI 推断 > 智能默认值
程序自动生成字段与其他三类无重叠，不存在优先级冲突。

═══════════════════════════════════════════

v5.1 变更（2026-06-17）:
  - 新增四象限字段来源分类（即本文档顶部章节）
  - 明确 36 = 28活跃 + 10扩展槽位
  - title/author 填充优先级：文件自带 > AI 推断

v5.0 变更（2026-06-16）:
  - domain: 自定义9域 → UDC 9主类
  - 分面3: lifecycle → temporal_nature（lifecycle 降级为普通字段）
  - 分面4: project_source → epistemic_status（project_source 降级为普通字段）
  - 移除: objectivity（被 content_type + epistemic_status 联合覆盖）
"""

# ═══════════════════════════════════════════
# 分面1：内容类型（content_type）— 必填
# 覆盖：文档/视频脚本/书籍/论文/标准/网页/笔记/其它
# ═══════════════════════════════════════════
CONTENT_TYPES = {
    "knowledge":     "知识条目（从文档/书籍/论文提取的结构化知识点）",
    "document":      "原始文档（PDF/Word/TXT，未提取知识）",
    "video_script":  "视频脚本（B站/抖音等）",
    "social_post":   "社媒文案（小红书/公众号/微博）",
    "article":       "文章/博客",
    "book":          "书籍章节或全文",
    "paper":         "学术论文/期刊",
    "standard":      "标准/规范文件（国标/ISO/行业规范）",
    "webpage":       "网页内容（爬虫或手动保存）",
    "personal_note": "个人笔记（学习/心得/日记）",
    "project_note":  "项目笔记（工作日志/项目记录）",
    "idea":          "想法/灵感（未成形的点子）",
    "template":      "模板（脚本模板/文档模板）",
    "legal_doc":     "法律文件（合同/证书/专利）",
    "other":         "其它（无法归类的内容）",
}

CONTENT_TYPE_OPTIONS = [
    ("knowledge",     "📖 知识条目"),
    ("document",      "📄 原始文档"),
    ("video_script",  "🎬 视频脚本"),
    ("social_post",   "📱 社媒文案"),
    ("article",       "📰 文章/博客"),
    ("book",          "📚 书籍"),
    ("paper",         "📑 学术论文"),
    ("standard",      "📜 标准/规范"),
    ("webpage",       "🌐 网页内容"),
    ("personal_note", "📝 个人笔记"),
    ("project_note",  "📋 项目笔记"),
    ("idea",          "💡 想法/灵感"),
    ("template",      "📐 模板"),
    ("legal_doc",     "⚖️ 法律文件"),
    ("other",         "📦 其它"),
]


# ═══════════════════════════════════════════
# 分面2：主题域（domain）— 必填，UDC 9 主类
# 基于国际十进分类法（UDC），9 个主类，支持多选
# 细分 UDC 码存为普通字段 udc_code，不入分面
# ═══════════════════════════════════════════
DOMAINS = {
    "0": "总论、信息科学（计算机、AI、知识管理、标准）",
    "1": "哲学、心理学（认知、个人成长）",
    "2": "宗教、神学",
    "3": "社会科学（法律、经济、管理、教育）",
    "5": "数学、自然科学（数学、物理、化学、生物）",
    "6": "应用科学、技术（机械、电气、通信、建筑、医疗）",
    "7": "艺术、文体（设计、影视、音乐）",
    "8": "语言、文学（写作、出版、语言学）",
    "9": "历史、地理（传记、技术史）",
}

DOMAIN_OPTIONS = [
    ("0", "📚 总论·信息科学"),
    ("1", "🧠 哲学·心理学"),
    ("2", "⛪ 宗教·神学"),
    ("3", "🏛️ 社会科学"),
    ("5", "🔬 数学·自然科学"),
    ("6", "⚙️ 应用科学·技术"),
    ("7", "🎨 艺术·文体"),
    ("8", "📝 语言·文学"),
    ("9", "📅 历史·地理"),
]


# ═══════════════════════════════════════════
# 生命周期（lifecycle）— 普通字段（非分面），可选
# v5.0: 从分面降级为普通字段，仍可 filter
# ═══════════════════════════════════════════
LIFECYCLE_STAGES = {
    "idea":        "想法阶段",
    "draft":       "草稿阶段",
    "in_progress": "进行中",
    "review":      "审核中",
    "published":   "已发布",
    "archived":    "已归档",
}

LIFECYCLE_OPTIONS = [
    ("idea",        "💡 想法"),
    ("draft",       "📝 草稿"),
    ("in_progress", "🔨 进行中"),
    ("review",      "👀 审核中"),
    ("published",   "✅ 已发布"),
    ("archived",    "📦 已归档"),
]


# ═══════════════════════════════════════════
# 分面3：时效属性（temporal_nature）— 必填
# 借鉴 RMS-Ltd doc-lifecycle-metadata-spec
# ═══════════════════════════════════════════
TEMPORAL_NATURE = {
    "evergreen": "常青 — 长期有效，不随时间贬值（数学定理、设计原则、标准参数）",
    "timeboxed": "有时限 — 一段时间内有效，之后可能过期（行业最佳实践、当前国标版本）",
    "transient": "时效敏感 — 会快速过时（行业动态、产品发布信息、趋势预测）",
}

TEMPORAL_NATURE_OPTIONS = [
    ("evergreen", "🌲 常青"),
    ("timeboxed", "⏳ 有时限"),
    ("transient", "⚡ 时效敏感"),
]


# ═══════════════════════════════════════════
# 分面4：认知验证状态（epistemic_status）— 必填
# 基于 FPF（First Principles Framework），arxiv 2601.21116
# L0 猜想 → L1 逻辑验证 → L2 实证验证
# ═══════════════════════════════════════════
EPISTEMIC_STATUS = {
    "unverified":     "L0 猜想 — 未验证的假设、个人意见、原始笔记",
    "substantiated":  "L1 逻辑验证通过 — 逻辑自洽，但缺外部实证",
    "corroborated":   "L2 实证验证 — 引用标准/论文/实验数据/法规",
}

EPISTEMIC_STATUS_OPTIONS = [
    ("unverified",    "❓ L0 猜想"),
    ("substantiated", "🔍 L1 逻辑验证"),
    ("corroborated",  "✅ L2 实证验证"),
]


# ═══════════════════════════════════════════
# 知识子类型（knowledge_type）
# 仅 content_type = "knowledge" 时填写
# ═══════════════════════════════════════════
KNOWLEDGE_TYPES = {
    "principle":   "原理",
    "formula":     "公式",
    "case":        "案例",
    "standard":    "标准/规范",
    "concept":     "概念/定义",
    "method":      "方法/流程",
    "data":        "数据/参数",
    "reference":   "参考文献",
    "procedure":   "工序/工艺",
    "requirement": "需求/规格",
    "test_data":   "测试数据",
}

KNOWLEDGE_TYPE_OPTIONS = [
    ("principle",   "📐 原理"),
    ("formula",     "🔢 公式"),
    ("case",        "📋 案例"),
    ("standard",    "📜 标准/规范"),
    ("concept",     "💡 概念/定义"),
    ("method",      "🔧 方法/流程"),
    ("data",        "📊 数据/参数"),
    ("reference",   "📚 参考文献"),
    ("procedure",   "⚙️ 工序/工艺"),
    ("requirement", "📋 需求/规格"),
    ("test_data",   "🧪 测试数据"),
]


# ═══════════════════════════════════════════
# 关系类型（relations 分组字段内的 type）
# ═══════════════════════════════════════════
RELATION_TYPES = {
    "similar":      "相似内容",
    "references":   "引用",
    "contradicts":  "矛盾/冲突",
    "derived_from": "衍生自",
    "merged_into":  "已合并到",
    "supersedes":   "替代/取代",
    "depends_on":   "依赖",
}


# ═══════════════════════════════════════════
# 摄入方式（origin.ingest_method）
# ═══════════════════════════════════════════
INGEST_METHODS = {
    "upload":  "UI上传",
    "email":   "邮件摄入",
    "api":     "API调用",
    "crawler": "爬虫",
    "manual":  "手动输入",
}


# ═══════════════════════════════════════════
# 可信度（trust_score）选项
# ═══════════════════════════════════════════
TRUST_SCORE_LABELS = {
    0: "未评级（默认值，表示尚未评估）",
    5: "⭐⭐⭐⭐⭐ 权威来源（国家标准/教科书/官方手册）",
    4: "⭐⭐⭐⭐ 可信来源（同行评审论文/官方文档）",
    3: "⭐⭐⭐ 一般来源（技术博客/个人经验）",
    2: "⭐⭐ 待验证（网络信息/未经核实）",
    1: "⭐ 存疑（矛盾/待 Crucible 验证）",
}


# ═══════════════════════════════════════════
# 语言（language）
# ═══════════════════════════════════════════
LANGUAGES = {
    "zh":    "中文",
    "en":    "English",
    "mixed": "中英混合",
}
LANGUAGE_OPTIONS = [(k, v) for k, v in LANGUAGES.items()]


# ═══════════════════════════════════════════
# 访问权限（access_level）
# ═══════════════════════════════════════════
ACCESS_LEVELS = {
    "private": "仅自己",
    "team":    "团队可见（未来）",
    "public":  "公开（未来）",
}
ACCESS_LEVEL_OPTIONS = [(k, v) for k, v in ACCESS_LEVELS.items()]


# ═══════════════════════════════════════════
# 目标平台（target_platform）— 内容分发的目标平台
# ═══════════════════════════════════════════
TARGET_PLATFORMS = {
    "none":     "无特定平台",
    "bilibili": "B站",
    "douyin":   "抖音",
    "xiaohongshu": "小红书",
    "wechat":   "微信公众号",
    "weibo":    "微博",
    "zhihu":    "知乎",
    "blog":     "个人博客",
    "internal": "内部使用",
}
TARGET_PLATFORM_OPTIONS = [(k, v) for k, v in TARGET_PLATFORMS.items()]


# ═══════════════════════════════════════════
# 许可证（license）— 未来用，暂存 ext_text1
# ═══════════════════════════════════════════
LICENSE_TYPES = {
    "private":   "私有",
    "cc0":       "CC0 公共领域",
    "cc_by":     "CC BY 署名",
    "cc_by_sa":  "CC BY-SA 署名相同方式共享",
    "fair_use":  "合理引用",
}


# ═══════════════════════════════════════════
# 兼容层：保留旧接口
# ═══════════════════════════════════════════
CLASSIFICATION_SCHEMES = {
    "faceted": {
        "label":  "faceted 分面分类（推荐）",
        "desc":   "多维度标签式分类，适合混合内容类型",
        "detail": (
            "4 个分面：内容类型(15) / 主题域-UDC(9) / 时效属性(3) / 认知验证状态(3)\n"
            "28 个活跃字段 + 10 个预留扩展槽位：分组设计（relations/timeline/origin/stats）"
        ),
        "collections": {"athanor_v1": "全部分面分类内容"},
    }
}
DEFAULT_SCHEME = "faceted"
DEFAULT_COLLECTION = "athanor_v1"


# ═══════════════════════════════════════════
# 域迁移映射（旧 9 域 → UDC 9 主类）
# 用于数据迁移脚本
# ═══════════════════════════════════════════
DOMAIN_MIGRATION_MAP = {
    "机械设计":   ["6"],    # 应用科学·技术 → 机械
    "智能家居":   ["6"],    # 应用科学·技术 → 电气/通信
    "AI编程":     ["0"],    # 总论·信息科学 → 计算机/AI
    "内容创作":   ["7"],    # 艺术·文体
    "企业管理":   ["3"],    # 社会科学 → 管理
    "个人成长":   ["1"],    # 哲学·心理学
    "出版写作":   ["8"],    # 语言·文学
    "法律专利":   ["3"],    # 社会科学 → 法律
    "标准规范":   ["0", "6"],  # 总论(标准) + 应用科学
}


def normalize_facet_values(metadata: dict) -> dict:
    """
    枚举守卫：验证并规范化分面字段值。
    
    在 LLM 返回结果后、写入 Qdrant 前执行：
        LLM 返回 → normalize_facet_values() → 严格枚举值 → 写入 Qdrant
    
    核心逻辑：
        1. 单选枚举（content_type / temporal_nature / epistemic_status）
           → 标准化空格/大小写/中英文 → 精确匹配 → fallback 默认值
        2. 多选列表（domain）
           → 逐项标准化 → 去重
        3. 数值字段（trust_score）
           → 确保在合法范围内
    
    返回：规范化后的 metadata（原地修改 + 返回）
    """
    # ── content_type：单选，15 种 ──
    ct = metadata.get("content_type")
    if ct:
        ct_norm = ct.strip().lower().replace(" ", "_")
        if ct_norm in CONTENT_TYPES:
            metadata["content_type"] = ct_norm
        else:
            # 模糊匹配：去掉前缀（如 "📖 knowledge" → "knowledge"）
            for valid_key in CONTENT_TYPES.keys():
                if valid_key in ct_norm or ct_norm in valid_key:
                    metadata["content_type"] = valid_key
                    break
            else:
                metadata["content_type"] = "other"  # fallback
    
    # ── domain：多选列表，9 种 UDC 主类 ──
    dom = metadata.get("domain")
    if dom:
        if isinstance(dom, str):
            dom = [d.strip() for d in dom.split(",")]
        elif not isinstance(dom, list):
            dom = [str(dom)]
        normalized = []
        for d in dom:
            d_norm = d.strip()
            if d_norm in DOMAINS:
                normalized.append(d_norm)
        metadata["domain"] = list(dict.fromkeys(normalized))  # 去重保持顺序
    
    # ── temporal_nature：单选，3 种 ──
    tn = metadata.get("temporal_nature")
    if tn:
        tn_norm = tn.strip().lower()
        if tn_norm in TEMPORAL_NATURE:
            metadata["temporal_nature"] = tn_norm
        else:
            # 模糊匹配
            for valid_key in TEMPORAL_NATURE.keys():
                if valid_key in tn_norm or tn_norm in valid_key:
                    metadata["temporal_nature"] = valid_key
                    break
            else:
                metadata["temporal_nature"] = "timeboxed"  # fallback
    
    # ── epistemic_status：单选，3 种 ──
    es = metadata.get("epistemic_status")
    if es:
        es_norm = es.strip().lower()
        if es_norm in EPISTEMIC_STATUS:
            metadata["epistemic_status"] = es_norm
        else:
            # 模糊匹配
            for valid_key in EPISTEMIC_STATUS.keys():
                if valid_key in es_norm or es_norm in valid_key:
                    metadata["epistemic_status"] = valid_key
                    break
            else:
                metadata["epistemic_status"] = "unverified"  # fallback
    
    # ── trust_score：数值，0-5 ──
    ts = metadata.get("trust_score")
    if ts is not None:
        try:
            ts_int = int(ts)
            metadata["trust_score"] = max(0, min(5, ts_int))
        except (ValueError, TypeError):
            metadata["trust_score"] = 3  # fallback 中等可信
    
    # ── knowledge_type：单选，11 种（仅 content_type="knowledge" 时有效）─┘
    kt = metadata.get("knowledge_type")
    if kt:
        kt_norm = kt.strip().lower()
        if kt_norm in KNOWLEDGE_TYPES:
            metadata["knowledge_type"] = kt_norm
        else:
            metadata["knowledge_type"] = "concept"  # fallback
    
    return metadata
