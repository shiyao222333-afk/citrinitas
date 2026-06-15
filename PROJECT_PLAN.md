# Athanor / KnowledgeForge — 项目主计划

> 这是项目的**唯一版本路线图**。每次制定功能计划前必须先读此文件，
> 计划变更时必须同步更新此文件。避免多文件版本号不一致。

最后更新: 2026-06-15

---

## 版本路线图

| 版本 | 状态 | 代号 | 核心交付 |
|------|:----:|------|---------|
| v0.1.0 | ✅ | 核心引擎 | CLI 向量搜索 + LLM 问答 + OCR + KaTeX + 表格拆分 |
| v0.2.0 | ✅ | Web UI MVP | Streamlit 4 页面（摄入/检索/管理/配置） |
| v0.3.0 | ✅ | 分面分类 v4.0 | 36 字段分组方案 + 关系管理 + 分面统计 + 知识管理面板 |
| v0.4.0 | ✅ | 智能摄入 | LLM 自动分类 + 两阶段摄入管线 + 共享表单组件 |
| v0.4.5 | 🚧 | 智能摄入深化 | 8 种格式智能检测 + docstore + 死信队列 + 审核队列 + 置信度路由 |
| v0.5.0 | 🔮 | 守望文件夹 | 文件夹监听自动摄入 + 批量文件处理 |
| v1.0.0 | 🔮 | 生产就绪 | FastAPI 后端 + 移动端适配 + 微信 Bot |

---

## 当前版本: v0.4.0

### 已完成的核心能力（v0.4.0 新增）

- **LLM 自动分类** — `kb_query.auto_classify(text)`: LLM 读取文本 → 推断 content_type/domain/keywords/trust_score/lifecycle/title/author，严格从给定选项中选取，字段合法性校验
- **两阶段摄入管线** — 阶段一确认内容 → 阶段二 LLM 自动分析 + 人工微调 → 摄入
- **共享表单组件** — `utils/ingest_ui.py`: `render_facet_form()` + `build_facet_metadata()`，三 Tab 统一调用，消除 ~200 行重复代码
- **智能默认值** — 手动输入的 content_type 默认 `idea`、is_personal 默认 True；文件/OCR 默认 `knowledge`
- **AI 分析结果可视化** — 5 列度量卡片展示 LLM 推断的分类结果，与表单联动

### v0.3.0 继承的能力

- 向量搜索 + LLM 综合问答（DeepSeek API / OpenAI 兼容）
- OCR 识别（PaddleOCR / PPStructureV3） + LLM 纠错
- KaTeX 服务端公式渲染 + 表格行级拆分引用
- 去重过滤（SHA256 + 同源去重 + OCR 质量过滤）
- 15 种内容类型 × 9 大主题域 × 6 级生命周期分面分类
- 通用关系字段（8 种关系类型：similar/references/contradicts/derived_from…）
- 分组字段：timeline / origin / stats（15 个独立字段压缩为 3 个嵌套对象）
- 知识管理面板：可信度编辑 / 归档 / 版本标记 / 关系管理
- 分面统计仪表盘：内容类型/主题域/生命周期分布可视化
- 高级摄入表单：14 个元数据字段 + 折叠面板
- 12 个预留扩展字段（ext_*）

### 技术栈

| 层 | 技术 |
|----|------|
| 向量库 | Qdrant（单集合 `athanor_v1`, 2560d, Cosine, 11 Payload Index） |
| 嵌入 | Ollama + qwen3-embedding:4b |
| LLM | DeepSeek API（OpenAI 兼容, 环境变量配置） |
| OCR | PaddleOCR / PPStructureV3 |
| 公式 | KaTeX（服务端渲染） |
| Web | Streamlit 1.58+ |

---

## v0.4.0 计划 — 智能摄入 ✅ 已完成

### 目标
用户在摄入文档时，系统用 LLM 自动分析文本内容，推断 content_type / domain / keywords 等分面字段，用户只需确认或微调。

### 具体任务
- [x] `kb_query.auto_classify(text)` — LLM 读文本 → 输出结构化 JSON 元数据，含字段校验
- [x] `utils/ingest_ui.py` — 抽取共享分面表单组件 `render_facet_form()` + `build_facet_metadata()`
- [x] 重构 `pages/1_文档注入.py` — 两阶段流程（内容确认 → AI分析 + 人工微调 → 摄入），代码从 660 行精简到 ~240 行
- [x] 三 Tab 表单去重（共享组件替代 3 份重复代码）

### 不做
- 批量文件摄入（留给 v0.5.0 守望文件夹）
- 实时预览时自动分类（等用户确认内容后再分析，避免浪费 token）

---

## v0.4.5 计划 — 智能摄入深化 🚧

### 背景

v0.4.0 完成了两阶段摄入管线（内容确认 → AI 分析 + 人工微调 → 摄入），但仅支持 .txt .pdf .md .json 四种格式。本次深化将文件类型扩展到 8 种核心格式，建立 docstore 文档注册表 + 死信队列 + 审核队列，并实现置信度路由，为 v0.5.0 守望文件夹全自动管线铺路。

### 设计决策（2026-06-15 确认）

- **元数据优先级**: 文件自带 > LLM 推断 > 用户手动。每条字段标记 `metadata_source: "file" | "llm" | "manual" | "inherit"`
- **低置信度处理**: 置信度 < 0.5 不进库（进审核队列）；0.5–0.8 入库 + 标记 `needs_review`；≥ 0.8 直接入库
- **置信度计算**: 启发式（JSON完整性 0.25 + 字段合法性 0.35 + 信息丰度 0.25 + 一致性 0.15），远期接入 DeepSeek logprobs
- **审核队列入口**: 知识中枢页面
- **文件大小上限**: 50MB，超限提示但允许继续
- **编码检测**: chardet 自动检测 + UTF-8 → GBK → latin-1 兜底链
- **PDF 双路径**: pypdf 提取文字层 → 文字层不足 → PaddleOCR 逐页识别

### 阶段一：内容准备深化

**目标：** 支持 8 种核心格式的智能检测 + 分层处理 + 元数据来源标记

**任务清单：**
- [ ] 1a. 文件类型检测层 `detect_file_type()` — 扩展名 + 内容头4字节验证，输出 `{tier, format, extraction_method, has_auto_metadata}`
- [ ] 1b. EPUB 处理（ebooklib）— 提取文本 + Dublin Core 元数据（title/author/publisher/ISBN/language/date）
- [ ] 1c. PDF 双路径处理 — pypdf 提取文字层 → 文字层不足 → PaddleOCR 逐页
- [ ] 1d. 编码自动检测（chardet）— UTF-8 → GBK → latin-1 兜底链
- [ ] 1e. 新格式支持 — .docx（python-docx）、.pptx（python-pptx）、.srt（去时间戳）、.html（BeautifulSoup title+meta）
- [ ] 1f. 元数据来源标记 — metadata 新增 `metadata_source` 字段: "file" | "llm" | "manual" | "inherit"
- [ ] 1g. 文件大小上限 — 50MB，超限提示但允许继续
- [ ] 1h. 页面 UI 调整 — Tab 1 扩展格式列表 + 自动识别结果预览；Tab 2 增加 OCR 质量标记；文件类型检测结果 banner
- [ ] 1i. 无文件场景源文件路径缺失处理 — 手动输入/OCR/Alembic 推送的内容无本地源文件，不记录 source_path

### 阶段二：元数据标注优化（待规划）

- [ ] 2a. 置信度计算（启发式 v1）
- [ ] 2b. 元数据合并策略（逐字段 file > llm > manual 优先级）
- [ ] 2c. LLM 分析结果展示增强（标注字段来源：📎文件 / 🤖AI）
- [ ] 2d. 低置信度视觉警告
- [ ] 2e. 5000 字截断提醒

### 阶段三：摄入执行重构（待规划）

- [ ] 3a. 真实进度回调（替换 time.sleep 假进度条）
- [ ] 3b. `doc_registry.json` — 文档注册表（doc_id → hash → status 映射）
- [ ] 3c. Dead Letter Queue — 失败文件副本 + status.json
- [ ] 3d. 摄入结果摘要卡片
- [ ] 3e. OCR 纠错提示强化

### 阶段四：审核队列（待规划）

- [ ] 4a. 知识中枢「待审核」区域
- [ ] 4b. needs_review 标记条目管理
- [ ] 4c. 批量通过/驳回
- [ ] 4d. 状态文件格式定义

### 阶段五：无 UI 管线（待规划）

- [ ] 5a. `prepare_content(interactive=False)` 统一入口
- [ ] 5b. Alembic → Athanor 传输协议定义 `{"text": "...", "origin": {"type": "bilibili", ...}}`
- [ ] 5c. 命令行工具: `python -m athanor review --list`

### 文件类型分层

| 层级 | 格式 | 自动元数据 | 提取方式 |
|:---:|------|:---:|------|
| 1 | EPUB | ✅ 标题/作者/出版社/ISBN | ebooklib → Dublin Core |
| 1 | PDF（文字层）| ✅ 标题/作者/主题 | pypdf → Document Info |
| 1 | HTML | ✅ title/meta | BeautifulSoup → head |
| 2 | TXT/MD/JSON/CSV/SRT/DOCX/PPTX | ❌ | 直接读 + LLM 推断 |
| 3 | 图片/扫描PDF | ❌ | PaddleOCR + LLM 推断 |
| 4 | 手动输入 | ❌ | 用户填写（默认值优化）|

### 不做
- 批量文件摄入（留给 v0.5.0 守望文件夹）
- EPUB/PDF 加密文件解密
- .doc（旧版 Word）/ .xlsx Excel 处理
- 守望文件夹触发策略
- 推送通知层（Server酱/邮件）

---

## 架构原则（不可变）

1. **非必要不用大模型** — 尽可能由固定程序完成（OCR/去重/引用编号/公式渲染）
2. **核心逻辑（kb_query.py）与 UI 完全解耦** — 面向未来手机端交互
3. **输出统一 JSON 结构化数据** — search/ingest/answer 返回值均为 dict
4. **配置用环境变量** — KB_LLM_BASE_URL/KEY/MODEL, KB_EMBED_MODEL 等
5. **本地优先** — 向量库本地、嵌入模型本地，仅 LLM 合成需联网

---

## 文档版本说明

本文件追踪 **项目版本**（v0.1.0 → v0.2.0 → …）。

- `docs/schema.md` 追踪 **字段设计文档版本**（v1.0 → v2.0 → v4.0），两者独立演进。
- `CHANGELOG.md` 追踪 **kb_query.py 的语义化版本**，与项目版本保持一致。
- `WEB_UI_PLAN.md` 为 v0.2.0 时期的 UI 任务清单，已完成，保留作为历史记录。

---

## 相关文件索引

| 文件 | 用途 |
|------|------|
| `PROJECT_PLAN.md` | 主计划（本文件） |
| `kb_query.py` | 核心引擎（`__version__` 字段同步于此） |
| `README.md` | 项目门面 |
| `CHANGELOG.md` | 版本变更日志 |
| `docs/schema.md` | 字段设计文档 |
| `WEB_UI_PLAN.md` | v0.2 Web UI 任务清单（已归档） |
| `DEVELOPMENT_HISTORY.md` | 开发过程记录 |
| `COMPARISON.md` | 同类工具对比 |
