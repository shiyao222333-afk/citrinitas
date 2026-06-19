# Changelog

> Citrinitas（熔知）版本变更日志。
> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
>
> **版本类型**: PATCH(修复) / MINOR(功能) / MAJOR(破坏)

---

## [Unreleased]

### Fixed
- 🔧 P1 问题修复（F5/C11/F7）：
  - F5: 文档管理页面添加审核状态过滤器（后端 list_documents() 支持 needs_review 参数）
  - C11: PROJECT_PLAN.md 更正 1f 标记（metadata_source 已废弃）
  - F7: kb_query.py 标记 6 个未使用函数为废弃（将在 v0.5.0 删除）

---

## [v0.4.6] - 2026-06-19

### Fixed
- 🔧 P1 问题修复（U2, U3）：
  - U2: 文件元数据现通过 AI 分析确认卡片展示
  - U3: AI 分析结果现通过确认卡片展示，用户可在摄入前查看/修改
  - 新增"AI 分析"确认卡片（阶段二），展示文件元数据 + AI 推断结果

---

## [v0.4.6] - 2026-06-19

### Fixed
- 🔧 P1 问题修复（U2, U3）：
  - U2: 文件元数据现通过 AI 分析确认卡片展示，用户可查看并确认文件自带元数据
  - U3: AI 分析结果现通过确认卡片展示，用户可在摄入前查看、修改、确认元数据
  - 新增"AI 分析"确认卡片（阶段二），展示文件元数据 + AI 推断结果，用户确认后再摄入

---

### Fixed — 2026-06-19
- 🔧 P1 问题修复（17项）：
  - F1: `metadata.update()` 全量合并 AI 分类结果（替代选择性合并）
  - F2: 添加 `_safe_slice_point()` 函数（中文字符切片保护）
  - D2: 实现 `detect_encoding()` 函数（chardet + 兜底链）
  - E1: 清理所有 `book/chapter/page` 废弃字段引用 + 删除死代码 `_source_to_meta()`
  - E2: 实现 `extract_text()` 支持 .txt/.md/.json/.csv/.docx/.html/.srt/.pdf
  - F4: 实现 `_extract_json_block()` 支持嵌套 JSON 提取
  - C1: `CONTENT_TYPES` 实际 15 种（注释已正确）
  - G1: 实现 `normalize_facet_values()` 枚举守卫函数（`config/classifications.py`）
  - G2: `auto_classify()` 实现 L1-L3 简单规则 + 调用 `normalize_facet_values()`
  - C2: `_ensure_collection()` 现创建 Payload Index（9 个分面 + 过滤字段）
  - D1: `trust_score` 统一为 0-5 整数（UI + 后端）
  - E4: `source_path` 存储原始文件名（已正确）

### Changed — 2026-06-19
- 🔄 项目命名重构：Athanor → Citrinitas（代码内部全量改名）
  - main.py / run.py / run.bat：标题 / 打印 / 窗口名更新
  - config / utils / classifications：注释更新
  - sync_ima.py：所有引用更新
  - .codebuddy/CODEBUDDY.md：启动路径更新
  - venv 重建为 `D:\citrinitas\venv`
  - Qdrant 集合名 `athanor_v1` 保留不变（避免数据迁移）

### Fixed — 2026-06-19
- 🐛 启动崩溃：Qdrant 离线时 `_r` 未定义 NameError

### Added — 2026-06-19
- ✨ 新增 BLUEPRINT.md（项目宪法）
- ✨ 新增 FLOWCHART.md（数据流程图 + 节点定义）

---

## [v0.4.4] - 2026-06-18

### Fixed
- 🐛 XSS 漏洞：`_format_evidence_text()` 和 `_cell_html()` 未转义用户内容 → 先 `_html.escape()` 再还原 `$...$` 和 `[image:...]`
- 🐛 `_render_report_html()` 中 synthesis 未转义 → 同样先 escape 再还原公式

### Added
- ✨ 新增文档管理页面 `/manage`：文档列表（分页）+ 查看详情 + 删除（含确认对话框）
- ✨ `kb_query.py` 新增文档管理函数：`list_documents()` / `get_document()` / `delete_document()` / `update_document()`
- ✨ 侧边栏新增「📄 文档管理」导航链接

---

## [v0.4.3] - 2026-06-18

### Fixed
- 🐛 language 字段永远默认 "zh" → Unicode 区块统计真检测（中/英/日/韩）
- 🐛 `_split_long_paragraph()` 从未使用 overlap 参数 → 相邻 chunk 尾部→头部重叠拼接
- 🐛 embed 逐条回退时单条失败整批丢弃 → 跳过失败块，≥50% 成功才写库
- 🐛 source 字段在极端路径下可能为 None → 加 `or "unknown"` 兜底
- 🐛 `_extract_images()` 仅识别 `[image: path]` → 新增 Markdown `![...](path)` + HTML `<img>` 三段提取

---

## [v0.4.2] - 2026-06-17

### Fixed
- 🐛 answer() 中 LLM 配置因 `.env` 加载顺序导致永远为空 → 改为 `os.environ.get()` 实时读取
- 🐛 WebSocket 超时导致搜索时 connect lost → `reconnect_timeout=120`
- 🐛 系统状态一直显示离线 → QDRANT_URL 改为 `127.0.0.1` + 动态初始化 + 定时刷新
- 🐛 完整报告 `file://` 链接浏览器安全策略阻止访问 → 新增 `/reports/{filename}` FileResponse 路由
- 🐛 端口冲突反复出现 → `run.bat` 自动杀旧进程
- 🐛 `ocr_image()` 公共入口函数缺失 → 创建包装函数
- 🐛 `search()` 返回字段名不匹配 → `results`→`chunks`, `highlights`→`synthesis`
- 🐛 `ingest()` 参数错误 → text 内容改为 `text=` 关键字参数

---

## [v0.4.1] - 2026-06-15

### Added
- ✨ 分面分类 v5.0：UDC 9 主类（国际十进分类法）替代自定义 9 域
- ✨ temporal_nature 分面：evergreen / timeboxed / transient
- ✨ epistemic_status 分面：L0 猜想 / L1 逻辑验证 / L2 实证验证
- ✨ udc_code 普通字段：LLM 自由输出 UDC 细分码 / 复合类号
- ✨ NiceGUI SPA 迁移：FastAPI + Vue + Quasar + WebSocket
- ✨ auto_classify() 增强：四层管道（模板 → 文件元数据 → 关键词 → LLM）
- ✨ normalize_facet_values() 枚举守卫
- ✨ DOMAIN_MIGRATION_MAP：旧 9 域 → UDC 9 主类迁移映射

### Changed
- 🔄 domain 分面：9 大中文主题域 → UDC 9 主类（0-9）
- 🔄 lifecycle + project_source 降级为普通字段
- 🔄 Payload Index：lifecycle/project_source → temporal_nature/epistemic_status
- 🔄 Web UI：Streamlit 多页面 → NiceGUI 单文件 SPA（main.py）
- 🔄 旧 Streamlit 文件归档至 `_archive/`

### Removed
- ❌ objectivity 字段（被 content_type + epistemic_status 联合覆盖）
- ❌ project_source 硬编码 5 项选项（改为自由文本）

---

## [v0.4.0] - 2026-06-15

### Added
- ✨ LLM 自动分类：auto_classify(text) 推断 content_type/domain/keywords 等
- ✨ 两阶段摄入管线：内容确认 → AI 分析 + 微调 → 入库
- ✨ 共享表单组件：utils/ingest_ui.py，消减 ~200 行重复代码
- ✨ AI 分析结果可视化：5 列度量卡片
- ✨ 智能默认值：手动输入默认 idea，文件/OCR 默认 knowledge

### Changed
- 🔄 文档注入页面重构：660 行 → ~240 行
- 🔄 三 Tab 表单去重

### Fixed
- 🐛 无本地源文件场景 source_path 处理

---

## [v0.3.0] - 2026-06-15

### Added
- ✨ 分面分类 v4.0：15 种内容类型 × 9 大主题域 × 6 级生命周期
- ✨ 通用关系字段：8 种关系类型
- ✨ 分组字段：timeline/origin/stats
- ✨ 知识管理面板 + 分面统计仪表盘
- ✨ 5 个新增 API + 搜索结果富展示
- ✨ 12 个预留扩展字段

### Changed
- 🔄 字段精简：49 → 36 字段
- 🔄 Qdrant Payload Index 从 0 扩展到 11 个
- 🔄 set_payload API 替代旧 PUT /points
- 🔄 _source_to_meta() 标记弃用

### Fixed
- 🐛 Qdrant facet filter should/min_should 语法失效 → must + match
- 🐛 update_metadata PUT /points 404 → POST /points/payload
- 🐛 ingest title=None fallback 不生效
- 🐛 search_multi source 字段名错误（file_name → source）
- 🐛 智能检索页 selected_cols 拼写 → selected_col
- 🐛 关于页两个 col2 列冲突

### Removed
- ❌ content_stage / task_id / updated_at / quality_score / category（旧层级分类字段）
- ❌ book / chapter / page 扁平字段

---

## [v0.2.0] - 2026-06-14

### Added
- ✨ Streamlit 多页面架构（app.py + 4 页面导航）
- ✨ 文档注入页面：上传 / OCR / 手动输入 + LLM 优化
- ✨ 智能检索页面：搜索 + AI 问答合并，跨库多选
- ✨ 知识中枢页面：卡片仪表盘 + 首次建库向导
- ✨ 引擎配置页面：LLM 预设 + 嵌入模型管理
- ✨ st.dialog 原生弹窗确认
- ✨ 缓存优化 + 像素火焰背景动画

### Changed
- 🔄 核心逻辑（kb_query.py）与 UI 层完全分离
- 🔄 配置用环境变量 + .env
- 🔄 LLM 后端切换至 DeepSeek API

### Fixed
- 🐛 8 个严重 Bug + 7 个重要 Bug（详见 ISSUES.md）

---

## [v0.1.0] - 2026-06-14

### Added
- ✨ OCR 摄入功能（PaddleOCR / PPStructureV3）
- ✨ 向量搜索（Qdrant + qwen3-embedding:4b）
- ✨ LLM 合成（DeepSeek API）+ 引用标注
- ✨ 表格行拆分 + 引用重编号
- ✨ KaTeX 服务端公式渲染
- ✨ HTML 报告生成 + 去重过滤（SHA256）

---

## 版本说明

| 标签 | 含义 |
|------|------|
| `Added` | 新功能 |
| `Fixed` | Bug 修复 |
| `Changed` | 功能变更 |
| `Deprecated` | 即将移除的功能 |
| `Removed` | 已移除的功能 |
| `Security` | 安全问题 |

**历史版本说明**：v0.3.0 及之前版本在同一版本中混合了 Added 和 Fixed（未严格遵循 Semver PATCH/MINOR 分工）。从 v0.4.2 起严格执行：PATCH 版本只含 Fixed，MINOR 版本只含 Added/Changed/Removed。
