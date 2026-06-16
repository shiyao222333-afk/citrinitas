<p align="center">
  <img src="assets/logo.svg" alt="Athanor Logo" width="120" height="120">
</p>

<h1 align="center">Athanor · 熔知 / MindForge</h1>

<p align="center">
  <b>个人本地知识引擎</b><br>
  把截图、手册、笔记丢进去，问一个问题，直接得到<strong>带来源引用的答案</strong>。<br>
  数据全在本地，不联网也能用。
</p>

<p align="center">
  <a href="https://github.com/shiyao222333-afk/athanor"><img src="https://img.shields.io/badge/Python-3.13+-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+"></a>
  <a href="https://github.com/shiyao222333-afk/athanor/blob/main/LICENSE"><img src="https://img.shields.io/github/license/shiyao222333-afk/athanor?style=flat-square" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Stage-Pre--release-yellow?style=flat-square" alt="Pre-release">
  <a href="https://github.com/shiyao222333-afk/athanor/stargazers"><img src="https://img.shields.io/github/stars/shiyao222333-afk/athanor?style=social" alt="Stars"></a>
</p>

<p align="center">
  <b>🌐 Language:</b> &nbsp;
  <a href="#cn">🇨🇳 中文</a> &nbsp;|&nbsp;
  <a href="#en">🇬🇧 English</a>
</p>

<p align="center">
  <a href="#-为什么需要-athanor"><b>🤔 为什么需要</b></a> ·
  <a href="#-核心能力--竞品对比"><b>✨ 核心能力 & 竞品对比</b></a> ·
  <a href="#-操作流程"><b>🔄 操作流程</b></a> ·
  <a href="#-架构概览"><b>🏗️ 架构概览</b></a> ·
  <a href="#-路线图"><b>🗺️ 路线图</b></a> ·
  <a href="#-快速开始"><b>⚡ 快速开始</b></a> ·
  <a href="https://github.com/shiyao222333-afk/athanor/issues"><b>🐛 提 Issue</b></a>
</p>

---

<!-- ============================================================ -->
<!--                        CN VERSION                            -->
<!-- ============================================================ -->

<span id="cn"></span>

## 🤔 为什么需要 Athanor？

> **"有问题直接问 LLM（GPT/DeepSeek）不就行了，为什么要手动输入知识？"**

这是最重要的问题。答案一句话：

> **LLM 是「聪明的外人」，Athanor 是「读过你所有资料的私人助理」。**

| 问题 | 直接问 LLM | 用 Athanor |
|------|-----------|-------------------|
| 没有你的私有知识 | ❌ 它没读过 | ✅ 直接搜你本地资料 |
| 没有记忆 | ❌ 每次对话都是新的 | ✅ 越用越强 |
| 无法溯源 | ❌ 答案不知道从哪来 | ✅ 每个答案带 `[引用N]` |
| 数据隐私 | ❌ 上传云端 | ✅ 全本地运行 |

---

## ✨ 核心能力 & 竞品对比

> 下表中每个 Athanor ✅ 后面标注了与竞品的关键差异。完整学术/技术依据详见 [docs/schema.md](docs/schema.md) · [PROJECT_PLAN.md](PROJECT_PLAN.md) · [CHANGELOG.md](CHANGELOG.md).

### 📊 功能逐一对比

| 功能 | Athanor | RAGFlow<br><sub>37k⭐</sub> | AnythingLLM<br><sub>30k⭐</sub> | Dify<br><sub>60k⭐</sub> | FastGPT<br><sub>20k⭐</sub> |
|------|:-------:|:-------:|:-------:|:----:|:-------:|
| **📥 摄入** | | | | | |
| 中文 OCR | ✅ PPStructureV3<sup>1</sup> | ✅ DeepDoc | ❌ | ❌ | ❌ |
| 公式识别+渲染 | ✅ KaTeX<sup>2</sup> | ✅ | ❌ | ❌ | ❌ |
| LLM 自动分类 | ✅ 四层推断<sup>3</sup> | ❌ | ❌ | ❌ | ❌ |
| 多格式检测 | ✅ 8种+编码自检<sup>4</sup> | ✅ 7种解析器 | ✅ | ✅ 流水线 | ✅ |
| 置信度路由 | ✅ 三档<sup>5</sup> | ❌ | ❌ | ❌ | ❌ |
| 死信队列 | ✅ | ❌ | ❌ | ❌ | ❌ |
| **🔍 搜索** | | | | | |
| 表格行级拆分 | ✅ 按行索引<sup>6</sup> | ❌ | ❌ | ❌ | ❌ |
| 连续引用编号 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 引用点击溯源 | ✅ | ✅ | ✅ | ✅ | ✅ |
| **🗂️ 知识组织** | | | | | |
| 分面分类 | ✅ 4维 (UDC+FPF)<sup>7</sup> | ❌ 扁平标签 | ❌ 工作区 | ❌ 元数据字段 | ❌ 数据集 |
| 认知验证层级 | ✅ L0-L2 | ❌ | ❌ | ❌ | ❌ |
| 通用关系字段 | ✅ 8种关系<sup>8</sup> | ❌ | ❌ | ❌ | ❌ |
| **🏗️ 架构** | | | | | |
| 本地运行 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 部署方式 | pip install | Docker | Desktop/Docker | Docker+DBS | Docker+DBS |
| 开源协议 | MIT | Apache 2.0 | MIT | Apache 2.0 | MIT |

> <sup>1</sup> **OCR**：RAGFlow 用 DeepDoc（ONNX+pdfplumber）同等强大，但面向企业 PDF 批处理；Athanor 聚焦个人混合素材（截图/扫描件/EPUB）的 OCR→LLM纠错→摄入**自动化闭环**。FastGPT/Dify/AnythingLLM 无内置 OCR。  
> <sup>2</sup> **公式**：Athanor 通过 PPStructureV3→LaTeX→KaTeX 将公式渲染为可缩放 SVG 嵌入搜索结果。RAGFlow 支持公式识别但不确认是否有专门渲染链路。其余竞品不区分公式和普通文本。  
> <sup>3</sup> **自动分类**：Athanor 用 LLM 四层管道（模板→元数据→关键词→LLM推断）自动标注分面字段，用户只需确认。所有竞品均无此能力——RAGFlow 分块仅带坐标标签，Dify 需手动编排流水线，FastGPT/AnythingLLM 靠文件夹手动组织。[→ FPF arxiv 2601.21116](docs/schema.md)  
> <sup>4</sup> **格式检测**：Athanor 除识别 8 种格式外还自动提取元数据（EPUB Dublin Core / PDF Document Info / HTML meta）+ chardet UTF-8→GBK 编码兜底。RAGFlow 有 7 种解析器切换能力更强，但不提取元数据。  
> <sup>5</sup> **置信度路由**：Athanor 独有三档路由（≥0.8 直入 / 0.5-0.8 标记审查 / <0.5 隔离），失败文件入死信队列。竞品均为"全有或全无"——解析失败静默丢弃。这是个人知识管理的核心安全设计。[→ PROJECT_PLAN.md](PROJECT_PLAN.md)  
> <sup>6</sup> **表格拆分**：Athanor 按行切分表格为独立检索单元，每行保留表头上下文。RAGFlow 按 token 切分（默认512），Dify 用父子分块模式，都不针对表格结构做行级索引。  
> <sup>7</sup> **分面分类**：基于 UDC 国际十进分类法 + FPF 认知层级，4 维标注（类型×领域×时效×验证层级），每维 Payload Index 支持组合过滤。竞品均为文件夹/标签的二维组织，不区分"数学定理(evergreen/corroborated)"和"行业新闻(transient/unverified)"。[→ UDC](https://www.udcsummary.info/)  
> <sup>8</sup> **关系字段**：Athanor 支持 similar/references/contradicts/derived_from/merged_into/supersedes/depends_on 8 种关系，可建立引用链和矛盾链。所有竞品均无条目间关系管理。[→ docs/schema.md](docs/schema.md)

### ⚖️ 各有千秋与定位取舍

坦诚地说，竞品在以下方面比我们强：

| 竞品 | 核心优势 | Athanor 的状态 |
|------|---------|---------------|
| **RAGFlow** | 知识图谱多跳推理、Agent 融合、7 种解析器矩阵、企业多租户 | 均不支持，定位个人使用 |
| **Dify** | 完整 AI 应用平台（可视化工作流+插件市场+运维监控）、60k⭐ 社区 | 无工作流/插件/监控，社区刚起步 |
| **FastGPT** | QA 自动生成模式（文档→问答对）、50 万+ 用户验证 | 无此摄入方式 |
| **AnythingLLM** | Electron 桌面端、即插即用多模型 | 无桌面端 |

但 Athanor 并不打算成为另一个 RAGFlow 或 Dify。我们的取舍很明确：

| 我们不做 | 我们在做 |
|----------|---------|
| 企业多租户 / 可视化工作流 / Agent / 插件市场 | **个人知识引擎**：深度理解 + 结构化认知 + 精确溯源 |
| 桌面应用 / 多端适配 | **轻量部署**：pip install 一条命令 |

> 💡 需要企业级 RAG 平台或通用 AI 应用构建器 → RAGFlow / Dify。需要**个人知识深度理解**且愿意和项目一起成长 → Athanor 的方向更对路。

---

## 🔄 操作流程

### 摄入管线

```mermaid
flowchart TD
    A[📎 上传文件 / 📸 OCR截图 / ✍️ 手动输入] --> B{文件类型检测}
    B -->|EPUB/PDF/HTML| C[📋 提取元数据<br>标题/作者/日期]
    B -->|TXT/MD/DOCX/PPTX| D[📄 直接读取文本]
    B -->|图片/扫描PDF| E[🔍 PaddleOCR 识别]

    C --> F{编码检测<br>chardet}
    D --> F
    E --> G[🤖 LLM OCR 纠错]
    G --> F

    F --> H[📊 内容确认]
    H --> I[🤖 AI 自动分析<br>推断分面字段]
    I --> J{置信度路由}

    J -->|≥ 0.8| K[✅ 直接入库]
    J -->|0.5 ~ 0.8| L[⚠️ 入库 + 标记审查]
    J -->|< 0.5| M[🚫 入审核队列<br>不污染知识库]

    K --> N[(Qdrant 向量库)]
    L --> N

    style A fill:#e1f5fe
    style N fill:#c8e6c9
    style M fill:#ffcdd2
```

### 搜索问答

```mermaid
flowchart LR
    A[❓ 用户提问] --> B[🔢 向量化<br>qwen3-embedding:4b]
    B --> C[🔍 Qdrant 语义检索<br>Top-K + 分面过滤]
    C --> D[📊 表格行级拆分<br>精确到单元格]
    D --> E[📐 KaTeX 公式渲染]
    E --> F[🤖 LLM 合成回答<br>基于检索结果]
    F --> G[🔗 引用连续编号<br>点击跳转原文]

    style A fill:#e1f5fe
    style G fill:#c8e6c9
```

---

## 🏗️ 架构概览

```mermaid
graph TB
    subgraph 用户层["🖥️ 用户层"]
        UI["NiceGUI SPA<br>FastAPI + Vue + Quasar<br>WebSocket 实时通信"]
    end

    subgraph 服务层["⚙️ 服务层"]
        INGEST["📥 摄入管线<br>格式检测 → OCR纠错 →<br>LLM分类 → 置信度路由"]
        SEARCH["🔍 检索引擎<br>向量检索 → 分面过滤 →<br>表格拆分 → 公式渲染"]
        QA["💬 问答合成<br>LLM总结 → 引用编号 →<br>连续溯源"]
    end

    subgraph 核心层["🧠 核心层"]
        KB["kb_query.py<br>核心引擎<br>与UI完全解耦"]
        OCR["PaddleOCR<br>PPStructureV3"]
        EMBED["Ollama<br>qwen3-embedding:4b"]
    end

    subgraph 存储层["💾 存储层"]
        QDRANT[("Qdrant<br>2560d · Cosine<br>11 Payload Index")]
        FS[("文件系统<br>原始文件<br>死信队列")]
    end

    UI --> INGEST
    UI --> SEARCH
    UI --> QA
    INGEST --> KB
    SEARCH --> KB
    QA --> KB
    KB --> OCR
    KB --> EMBED
    KB --> QDRANT
    KB --> FS
```

**技术栈一览：**

| 层 | 技术 | 说明 |
|----|------|------|
| 向量数据库 | [Qdrant](https://github.com/qdrant/qdrant) | 2560d, Cosine 距离, 单集合 `athanor_v1` |
| 嵌入模型 | [Ollama](https://github.com/ollama/ollama) + `qwen3-embedding:4b` | 本地推理，中英文兼顾 |
| OCR 引擎 | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) / PPStructureV3 | 中文优化，表格+公式识别 |
| LLM 合成 | OpenAI 兼容 API（默认 DeepSeek） | 可切换通义千问/本地模型 |
| 公式渲染 | [KaTeX](https://github.com/KaTeX/KaTeX) | 服务端渲染，矢量输出 |
| Web UI | [NiceGUI](https://nicegui.io) 3.13 | SPA, FastAPI + Vue + Quasar + WebSocket |
| 编码检测 | [chardet](https://github.com/chardet/chardet) | UTF-8 → GBK → latin-1 兜底链 |

---

## 🗺️ 路线图

| 版本 | 状态 | 代号 | 核心交付 |
|------|:----:|------|---------|
| v0.1.0 | ✅ | 核心引擎 | CLI 向量搜索 + LLM 问答 + OCR + KaTeX + 表格拆分 |
| v0.2.0 | ✅ | Web UI MVP | 4 页面（摄入/检索/管理/配置）+ 首次建库向导 |
| v0.3.0 | ✅ | 分面分类 v4.0 | 36 字段分组方案 + 关系管理 + 分面统计仪表盘 |
| v0.4.0 | ✅ | 智能摄入 | LLM 自动分类 + 两阶段摄入管线 |
| v0.4.1 | ✅ | 分面分类 v5.0 | UDC 9 主类 + NiceGUI SPA 迁移 |
| v0.4.5 | 🚧 | 智能摄入深化 | 8 格式检测 + 死信队列 + 置信度路由 |
| v0.5.0 | 🔮 | 守望文件夹 | 文件夹监听自动摄入 + 批量处理 |
| v1.0.0 | 🔮 | 生产就绪 | 移动端适配 + 微信 Bot + 知识图谱 |

> 详细路线图见 [PROJECT_PLAN.md](PROJECT_PLAN.md)

---

## ⚙️ 快速开始

### 环境准备

```bash
# Python >= 3.13
# Ollama（嵌入模型运行环境）从 https://ollama.com 安装

# 拉取嵌入模型
ollama pull qwen3-embedding:4b
```

### 安装 & 启动

```bash
pip install nicegui requests qdrant-client \
            paddlepaddle paddleocr "paddlex[ocr]==3.7.0" \
            fpdf2 pillow matplotlib

# 启动
python run.py
# → 浏览器访问 http://localhost:8080
```

### 使用流程

1. **首次使用** → 自动弹出建库向导 → 选择嵌入模型 → 创建集合
2. **摄入资料** →「文档注入」页面上传文件或 OCR 截图
3. **搜索问答** →「智能检索」页面输入问题，勾选是否启用 AI 问答
4. **管理知识** →「知识中枢」页面查看统计、审核队列、导出数据

> 📘 详细指南：[START.md](START.md)

---

## 👤 适合谁用？

| ✅ 非常适合 | ❌ 不太适合 |
|------------|------------|
| 有中文技术文档/手册积累的人 | 数据量极小（<10 个文件）且不需要搜索 |
| 截图/照片里有大量文字需要检索 | 想要商业化完整 Web UI（我们还在迭代） |
| 关心数据隐私，不想上传云端 | 不想碰任何配置（首次需 2 分钟） |
| 需要精确溯源：答案从哪张图/哪份文档来 | |
| 公式/表格很多的技术文档 | |
| 小说作者（世界观设定管理） | |
| 学术研究者（论文/标准文档管理） | |

---

## ❓ FAQ

**Q：支持英文文档吗？**
A：支持。`qwen3-embedding:4b` 对中英文都有效果。英文场景可换 `nomic-embed-text`。

**Q：能处理多少数据？**
A：理论上无上限，受限于硬件。Qdrant 支持磁盘存储。建议先从小批量（几十个文件）开始。

**Q：和 Obsidian / Notion 有什么区别？**
A：Obsidian 是笔记管理，Notion 是在线协作。Athanor 专注**非结构化资料**（截图、扫描件、PDF）的**语义搜索和问答**。

**Q：需要联网吗？**
A：摄入和向量检索不需要联网。仅 LLM 合成回答时需联网（可切换本地 LLM 完全离线）。

**Q：和 RAGFlow / Dify 的定位差异？**
A：RAGFlow/Dify 是面向企业的 RAG 引擎平台，Athanor 是面向个人的知识引擎——更轻量（pip 直接装）、更深入（表格行级拆分、分面分类、认知验证层级）、更聚焦个人场景。

---

## 🤝 贡献

欢迎参与！项目处于活跃开发阶段，每一份贡献都能显著影响方向。

- 🐛 **报告 Bug**：[提交 Issue](https://github.com/shiyao222333-afk/athanor/issues/new)
- 💡 **功能请求**：[功能请求](https://github.com/shiyao222333-afk/athanor/issues/new?template=feature)
- 💻 **代码贡献**：Fork → 分支 → PR

---

## 📄 许可证

[MIT License](LICENSE) — 自由使用、修改和分发。

---

## 🙏 致谢

- [Qdrant](https://github.com/qdrant/qdrant) — 高性能向量数据库
- [Ollama](https://github.com/ollama/ollama) — 本地 LLM 运行环境
- [NiceGUI](https://nicegui.io) — Python SPA 框架
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — 中文 OCR 引擎
- [KaTeX](https://github.com/KaTeX/KaTeX) — 公式渲染引擎
- [UDC](https://www.udcsummary.info/) — 国际十进分类法
- Gilda & Lamb (2026) — FPF 第一性原理框架 ([arxiv 2601.21116](https://arxiv.org/abs/2601.21116))

---

<!-- ============================================================ -->
<!--                        EN VERSION                            -->
<!-- ============================================================ -->

<span id="en"></span>

# 🇬🇧 Athanor · 熔知 / MindForge

<p align="center">
  <b>Personal Local Knowledge Engine</b><br>
  Drop in screenshots, manuals, and notes. Ask a question. Get <strong>answers with source citations</strong>.<br>
  All data stays local. Works offline.
</p>

---

## 🤔 Why Athanor?

> **"Why not just ask an LLM (GPT/DeepSeek) directly? Why manually input knowledge?"**

The answer in one line:

> **An LLM is a "smart stranger." Athanor is a "personal assistant that has read everything you own."**

| Problem | Direct LLM | Athanor |
|---------|-----------|---------|
| No access to your private knowledge | ❌ Never read it | ✅ Searches your local files |
| No memory | ❌ Each chat starts fresh | ✅ Gets smarter over time |
| No traceability | ❌ Can't tell where answers come from | ✅ Every answer cites `[refN]` |
| Data privacy | ❌ Uploaded to cloud | ✅ Fully local |

---

## ✨ Core Capabilities & Comparison

> Each ✅ below is annotated with what makes Athanor's approach different from competitors. See [docs/schema.md](docs/schema.md) · [PROJECT_PLAN.md](PROJECT_PLAN.md) · [CHANGELOG.md](CHANGELOG.md) for full references.

### 📊 Feature-by-Feature Comparison

| Feature | Athanor | RAGFlow<br><sub>37k⭐</sub> | AnythingLLM<br><sub>30k⭐</sub> | Dify<br><sub>60k⭐</sub> | FastGPT<br><sub>20k⭐</sub> |
|---------|:-------:|:-------:|:-------:|:----:|:-------:|
| **📥 Ingestion** | | | | | |
| Chinese OCR | ✅ PPStructureV3<sup>1</sup> | ✅ DeepDoc | ❌ | ❌ | ❌ |
| Formula recognition + rendering | ✅ KaTeX<sup>2</sup> | ✅ | ❌ | ❌ | ❌ |
| LLM auto-classification | ✅ 4-layer<sup>3</sup> | ❌ | ❌ | ❌ | ❌ |
| Multi-format detection | ✅ 8 + encoding check<sup>4</sup> | ✅ 7 parsers | ✅ | ✅ Pipeline | ✅ |
| Confidence routing | ✅ 3-tier<sup>5</sup> | ❌ | ❌ | ❌ | ❌ |
| Dead Letter Queue | ✅ | ❌ | ❌ | ❌ | ❌ |
| **🔍 Search** | | | | | |
| Row-level table splitting | ✅ By row<sup>6</sup> | ❌ | ❌ | ❌ | ❌ |
| Consecutive citations | ✅ | ❌ | ❌ | ❌ | ❌ |
| Clickable provenance | ✅ | ✅ | ✅ | ✅ | ✅ |
| **🗂️ Knowledge Org** | | | | | |
| Faceted classification | ✅ 4D (UDC+FPF)<sup>7</sup> | ❌ Flat tags | ❌ Workspaces | ❌ Metadata | ❌ Datasets |
| Epistemic verification | ✅ L0–L2 | ❌ | ❌ | ❌ | ❌ |
| Universal relations | ✅ 8 types<sup>8</sup> | ❌ | ❌ | ❌ | ❌ |
| **🏗️ Architecture** | | | | | |
| Fully local | ✅ | ✅ | ✅ | ✅ | ✅ |
| Deployment | pip install | Docker | Desktop/Docker | Docker+DBS | Docker+DBS |
| License | MIT | Apache 2.0 | MIT | Apache 2.0 | MIT |

> <sup>1</sup> **OCR**: RAGFlow's DeepDoc (ONNX+pdfplumber) is equally strong but targets enterprise PDF batch processing; Athanor focuses on personal mixed media (screenshots/scans/EPUBs) with an OCR→LLM correction→ingestion **automated loop**. FastGPT/Dify/AnythingLLM have no built-in OCR.  
> <sup>2</sup> **Formulas**: Athanor renders formulas as scalable SVG via PPStructureV3→LaTeX→KaTeX, embedded in search results. RAGFlow supports formula recognition but its dedicated rendering pipeline is unconfirmed. Others treat formulas as plain text.  
> <sup>3</sup> **Auto-classification**: Athanor uses a 4-layer LLM pipeline (template→metadata→keyword→LLM inference) to auto-label facet fields; users only confirm. No competitor has this — RAGFlow chunks carry only coordinate tags, Dify requires manual pipeline configuration, FastGPT/AnythingLLM rely on folder organization. [→ FPF arxiv 2601.21116](docs/schema.md)  
> <sup>4</sup> **Format detection**: Athanor goes beyond format ID to auto-extract metadata (EPUB Dublin Core / PDF Document Info / HTML meta) + chardet UTF-8→GBK encoding chain. RAGFlow's 7-parser matrix is more flexible but doesn't extract metadata automatically.  
> <sup>5</sup> **Confidence routing**: Unique 3-tier routing (≥0.8 direct / 0.5-0.8 flagged / <0.5 quarantined) with Dead Letter Queue. All competitors use all-or-nothing — parse failures are silently discarded. This is Athanor's core safety design for personal knowledge management. [→ PROJECT_PLAN.md](PROJECT_PLAN.md)  
> <sup>6</sup> **Table splitting**: Athanor splits tables by row as independent search units with header context preserved. RAGFlow chunks by token count (default 512), Dify uses parent-child mode — neither does row-level structural indexing.  
> <sup>7</sup> **Faceted classification**: Based on UDC (Universal Decimal Classification) + FPF epistemic hierarchy. 4 dimensions (type × domain × temporality × verification) with Payload Indexes. Competitors use folder/label 2D organization — none distinguishes "math theorem (evergreen/corroborated)" from "industry news (transient/unverified)." [→ UDC](https://www.udcsummary.info/)  
> <sup>8</sup> **Relations**: Athanor supports 8 relation types (similar/references/contradicts/derived_from/merged_into/supersedes/depends_on) building citation and contradiction chains. No competitor offers inter-entry relation management. [→ docs/schema.md](docs/schema.md)

### ⚖️ Strengths & Trade-offs

To be fair, competitors beat us in these areas:

| Competitor | Key Strengths | Athanor Status |
|------------|--------------|----------------|
| **RAGFlow** | Knowledge graph multi-hop reasoning, Agent integration, 7-parser matrix, enterprise multi-tenancy | None supported — personal use only |
| **Dify** | Full AI app platform (visual workflow + plugin marketplace + observability), 60k⭐ community | No workflow/plugins/monitoring, community just starting |
| **FastGPT** | QA auto-generation (docs→Q&A pairs), 500K+ validated users | Don't have this ingestion mode |
| **AnythingLLM** | Electron desktop app, plug-and-play multi-model | No desktop app |

Athanor is not trying to become another RAGFlow or Dify. Our trade-offs are deliberate:

| We DON'T do | We DO |
|-------------|-------|
| Enterprise multi-tenancy / visual workflows / Agents / plugins | **Personal knowledge engine**: deep understanding + structured cognition + precise provenance |
| Desktop app / multi-platform | **Lightweight**: single `pip install` |

> 💡 Need an enterprise RAG platform or general AI app builder → RAGFlow / Dify. Need **deep personal knowledge understanding** and willing to grow with the project → Athanor is a better fit.

---

## 🔄 Workflow

### Ingestion Pipeline

```mermaid
flowchart TD
    A[📎 Upload / 📸 OCR / ✍️ Manual] --> B{Format Detection}
    B -->|EPUB/PDF/HTML| C[📋 Extract Metadata]
    B -->|TXT/MD/DOCX/PPTX| D[📄 Direct Read]
    B -->|Image/Scanned PDF| E[🔍 PaddleOCR]

    C --> F{Encoding Detection}
    D --> F
    E --> G[🤖 LLM OCR Correction]
    G --> F

    F --> H[📊 Content Confirmation]
    H --> I[🤖 AI Auto-Classification]
    I --> J{Confidence Routing}

    J -->|≥ 0.8| K[✅ Direct Ingest]
    J -->|0.5 ~ 0.8| L[⚠️ Ingest + Flag Review]
    J -->|< 0.5| M[🚫 Review Queue]

    K --> N[(Qdrant)]
    L --> N

    style A fill:#e1f5fe
    style N fill:#c8e6c9
    style M fill:#ffcdd2
```

### Search & Q&A

```mermaid
flowchart LR
    A[❓ Query] --> B[🔢 Embedding]
    B --> C[🔍 Qdrant Search]
    C --> D[📊 Table Splitting]
    D --> E[📐 KaTeX Render]
    E --> F[🤖 LLM Synthesis]
    F --> G[🔗 Citations]

    style A fill:#e1f5fe
    style G fill:#c8e6c9
```

---

## 🏗️ Architecture

```mermaid
graph TB
    subgraph UI_Layer["🖥️ UI Layer"]
        UI["NiceGUI SPA<br>FastAPI + Vue + Quasar<br>WebSocket"]
    end

    subgraph Service_Layer["⚙️ Service Layer"]
        INGEST["📥 Ingestion Pipeline<br>Format Detection → OCR →<br>Classification → Routing"]
        SEARCH["🔍 Search Engine<br>Vector Search → Facet Filter →<br>Table Split → Formula Render"]
        QA["💬 Q&A Synthesis<br>LLM Summary → Citation →<br>Provenance Trace"]
    end

    subgraph Core_Layer["🧠 Core Layer"]
        KB["kb_query.py<br>Core Engine<br>UI-Decoupled"]
        OCR_E["PaddleOCR<br>PPStructureV3"]
        EMBED["Ollama<br>qwen3-embedding:4b"]
    end

    subgraph Storage_Layer["💾 Storage Layer"]
        QDRANT[("Qdrant<br>2560d · Cosine")]
        FS[("File System<br>Raw Files<br>DLQ")]
    end

    UI --> INGEST
    UI --> SEARCH
    UI --> QA
    INGEST --> KB
    SEARCH --> KB
    QA --> KB
    KB --> OCR_E
    KB --> EMBED
    KB --> QDRANT
    KB --> FS
```

**Tech Stack:**

| Layer | Technology | Notes |
|-------|-----------|-------|
| Vector DB | [Qdrant](https://github.com/qdrant/qdrant) | 2560d, Cosine, single collection `athanor_v1` |
| Embeddings | [Ollama](https://github.com/ollama/ollama) + `qwen3-embedding:4b` | Local inference, bilingual |
| OCR | [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) / PPStructureV3 | Chinese-optimized, table + formula recognition |
| LLM | OpenAI-compatible API (default DeepSeek) | Swappable (Qwen, local models) |
| Formula | [KaTeX](https://github.com/KaTeX/KaTeX) | Server-side rendering, vector output |
| Web UI | [NiceGUI](https://nicegui.io) 3.13 | SPA, FastAPI + Vue + Quasar + WebSocket |
| Encoding | [chardet](https://github.com/chardet/chardet) | UTF-8 → GBK → latin-1 fallback chain |

---

## 🗺️ Roadmap

| Version | Status | Codename | Key Deliverables |
|---------|:------:|----------|------------------|
| v0.1.0 | ✅ | Core Engine | CLI vector search + LLM Q&A + OCR + KaTeX + table splitting |
| v0.2.0 | ✅ | Web UI MVP | 4 pages (ingest/search/manage/config) + collection wizard |
| v0.3.0 | ✅ | Faceted Classification v4.0 | 36-field grouped schema + relations + facet stats dashboard |
| v0.4.0 | ✅ | Smart Ingestion | LLM auto-classification + two-phase ingestion pipeline |
| v0.4.1 | ✅ | Faceted Classification v5.0 | UDC 9 main classes + NiceGUI SPA migration |
| v0.4.5 | 🚧 | Deep Ingestion | 8-format detection + Dead Letter Queue + confidence routing |
| v0.5.0 | 🔮 | Watch Folder | Folder monitoring + auto-ingestion + batch processing |
| v1.0.0 | 🔮 | Production Ready | Mobile adaptation + WeChat Bot + knowledge graph |

> Full roadmap: [PROJECT_PLAN.md](PROJECT_PLAN.md)

---

## ⚙️ Setup

```bash
# Prerequisites
# Python >= 3.13, Ollama from https://ollama.com
ollama pull qwen3-embedding:4b

# Install & Run
pip install nicegui requests qdrant-client \
            paddlepaddle paddleocr "paddlex[ocr]==3.7.0" \
            fpdf2 pillow matplotlib
python run.py
# → http://localhost:8080
```

**Usage:**
1. **First launch** → Collection wizard pops up → select embedding model → create collection
2. **Ingest** → "Document Ingestion" page → upload files or OCR screenshots
3. **Search** → "Smart Search" page → type query, toggle AI synthesis
4. **Manage** → "Knowledge Hub" page → stats, review queue, export

> 📘 Detailed guide: [START.md](START.md)

---

## 👤 Who Is This For?

| ✅ Great fit | ❌ Not a great fit |
|-------------|-------------------|
| People with Chinese technical docs/manuals | Tiny datasets (<10 files) with no search needs |
| Lots of text trapped in screenshots/photos | Want a polished commercial Web UI (we're iterating) |
| Privacy-conscious, don't want cloud upload | Don't want any config (first setup takes 2 min) |
| Need precise provenance: which doc/page did this come from? | |
| Technical docs heavy on formulas and tables | |
| Fiction authors (worldbuilding knowledge management) | |
| Academic researchers (paper/standard management) | |

---

## ❓ FAQ

**Q: Does it support English documents?**
A: Yes. `qwen3-embedding:4b` works well for both Chinese and English. For English-only, switch to `nomic-embed-text`.

**Q: How much data can it handle?**
A: Theoretically unlimited, bounded by hardware. Qdrant supports disk storage. Start with small batches (a few dozen files).

**Q: How is it different from Obsidian / Notion?**
A: Obsidian is note management; Notion is online collaboration. Athanor focuses on **semantic search and Q&A over unstructured materials** (screenshots, scans, PDFs).

**Q: Does it need internet?**
A: Ingestion and vector search work offline. Only LLM synthesis needs internet (switch to a local LLM for full offline operation).

**Q: How does it differ from RAGFlow / Dify?**
A: RAGFlow/Dify are enterprise RAG platforms. Athanor is a personal knowledge engine — lighter (pip install), deeper (row-level table splitting, faceted classification, epistemic verification levels), and focused on individual use cases.

---

## 🤝 Contributing

Contributions welcome! The project is in active development — every contribution shapes its direction.

- 🐛 **Bug Report**: [Open an Issue](https://github.com/shiyao222333-afk/athanor/issues/new)
- 💡 **Feature Request**: [Feature Request](https://github.com/shiyao222333-afk/athanor/issues/new?template=feature)
- 💻 **Code**: Fork → Branch → PR

---

## 📄 License

[MIT License](LICENSE) — Free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- [Qdrant](https://github.com/qdrant/qdrant) — High-performance vector database
- [Ollama](https://github.com/ollama/ollama) — Local LLM runtime
- [NiceGUI](https://nicegui.io) — Python SPA framework
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — Chinese OCR engine
- [KaTeX](https://github.com/KaTeX/KaTeX) — Formula rendering engine
- [UDC](https://www.udcsummary.info/) — Universal Decimal Classification
- Gilda & Lamb (2026) — FPF First-Principles Framework ([arxiv 2601.21116](https://arxiv.org/abs/2601.21116))

---

<p align="center">
  <a href="#cn">🇨🇳 Back to 中文</a> &nbsp;|&nbsp;
  <a href="#en">🇬🇧 Back to Top</a>
</p>

<p align="center">
  ⭐ If this direction resonates with you, please give it a Star!<br>
  🗂️ Turn your accumulated knowledge into real assets.
</p>

<p align="center">
  <img src="https://api.star-history.com/svg?repos=shiyao222333-afk/athanor&type=Date&width=600&height=200" alt="Star History Chart">
</p>
