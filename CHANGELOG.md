# Changelog

> Citrinitas（熔知）版本变更日志。
> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
>
> **版本类型**: PATCH(修复) / MINOR(功能) / MAJOR(破坏)

---

## 版本号说明

> 本文档记录历史变更，版本号遵循 `PROJECT_PLAN.md` 的「版本路线图表」。
> 如两份文件版本号不一致，以 `PROJECT_PLAN.md` 为准。

### v0.5.0 定义变更记录

v0.5.0 初始规划为「快速开始优化」，实际执行时需求变更为「L2 管道（文件元数据→UDC 推断）+ `normalize_facet_values()` 模糊映射」。从 v0.6.0 起，版本规划严格按 PROJECT_PLAN.md 路线图表执行，不再中途变更定义。

### 版本类型定义

| 标签 | 含义 |
|------|------|
| `Added` | 新功能 |
| `Fixed` | Bug 修复 |
| `Changed` | 功能变更 |
| `Deprecated` | 即将移除的功能 |
| `Removed` | 已移除的功能 |
| `Security` | 安全问题 |

**历史版本说明**：v0.3.0 及之前版本在同一版本中混合了 Added 和 Fixed（未严格遵循 Semver PATCH/MINOR 分工）。从 v0.4.2 起严格执行：PATCH 版本只含 Fixed，MINOR 版本只含 Added/Changed/Removed。

---

## [1.1.0] — 2026-07-06

> **MINOR** — 架构重构（引入 Service 层）+ 错误日志规范（进行中）

### Added
- `services/ingest_service.py`: 从 `kb_query.py` 拆出摄入逻辑（架构重构 ADR-001）
- `services/__init__.py`: Service 层公共 API 重导出
- `docs/adr/ADR-001-introduce-service-layer.md`: 架构决策记录

### Changed
- **架构重构**：`kb_query.py` (655行) → `services/ingest_service.py` + `kb_query.py` (CLI facade)
- `classify_pipeline.py`: 新增 `route_by_confidence()` 函数（从 `kb_query.py` 移入）
- `kb_query.py`: 重写为 CLI facade，只做参数解析 + 调用 services
- `pages/ingest.py`: `import kb_query` → `from services.ingest_service import ingest` + `from classify_pipeline import route_by_confidence`
- `watcher/processor.py`: 同上
- 删除 `kb_query.py` 里 `get_facet_stats` 重复定义（改用 `search_engine.facets.get_facet_stats`）

### 下一步（错误日志规范 — 进行中）
- [ ] 统一 `logging.yaml` 配置
- [ ] 建立错误码体系（E001-E099 摄入 / E100-E199 搜索 / ...）
- [ ] 消灭 `except:pass`
- [ ] 增加日志查看器 UI

---

## [1.0.2] — 2026-07-06

> **PATCH** — Bug 修复 + 代码质量清理

### Fixed
- `utils/ui_shared.py`: `build_left_drawer()` 新增 `active_page` 参数，侧边栏导航链接根据当前页高亮
- `pages/hub/__init__.py`: 调用 `build_left_drawer(active_page="hub")` 不再崩溃
- `pages/search.py`: 补传 `active_page="search"`
- `pages/hub/detail.py`: 补传 `active_page="hub"`
- `pages/config.py`: 补传 `active_page="config"`
- `pages/manage.py`: 补传 `active_page="manage"`
- `utils/ui_shared.py`: 侧边栏新增「📄 文档管理」(`/manage`) 入口（此前为隐藏页面）

### Changed
- **`search_engine.py` (857行) → `search_engine/` 包** (5 modules)
  - `__init__.py` / `core.py` / `answer.py` / `utils.py` / `facets.py`
  - 外部调用方零感知：`from search_engine import search, answer` 不变
- `pages/search.py`: `import search_engine` → `from search_engine import search, answer, OUTPUT_DIR`
- `search_engine/answer.py`: `OUTPUT_DIR` 提升为模块级常量，通过包公共 API 导出

---

## [1.0.1] — 2026-06-28

> **代码质量清理 + API 规范化** — 死代码删除、3 个大文件拆分为独立包、run.bat 修复、公共 API 补全。

### Removed
- 删除死代码 `warmup.py`（110 行，PaddleOCR/Ollama 预热，zero references）
- 删除死代码 `sync_ima.py`（65 行，IMA knowledge base sync，zero references）
- 删除死代码 `watcher.py`（旧版，已由 `watcher/` 包替代）
- 删除 `scripts/check_llm.ps1`（不再需要）

### Changed
- **`watcher_v2.py` (1834行) → `watcher/` 包** (7 modules)
  - `__init__.py` / `state.py` / `utils.py` / `failures.py` / `processor.py` / `listener.py` / `migration.py`
  - 关键修复：子模块遗漏 `asyncio`/`STATE`/`log_activity` 导入（4 文件补全）
- **`pages/hub.py` (1418行) → `pages/hub/` 包** (8 modules)
  - `__init__.py` / `helpers.py` / `overview.py` / `browse.py` / `review.py` / `inbox.py` / `dlq.py` / `detail.py`
- **`text_pipeline.py` (1032行) → `text_pipeline/` 包** (6 files)
  - `ocr.py` / `extract.py` / `chunk.py` / `embed.py` / `analyze.py` / `__init__.py`
- `kb_query.__version__` 更新 `"0.7.0-dev"` → `"1.0.1"`
- `text_pipeline/__init__.py` 新增公共 API：`chunk_text()` 和 `embed_text()` 包装器
- 所有外部 importer 零感知，一行不改

### Fixed
- 修复 `run.bat` 调用已删除的 `warmup.py` 导致启动失败 (P0)
- 修复 `run.bat` 步骤编号不一致 ([x/8] 实为 10 步 → 统一为 8 步)
- 修复 `run.bat` 版本号 v1.0.0 → v1.0.1
- 修复 `run.bat` 守望目录显示：`data\watch\` → `data\inbox\`

---

## [1.0.0] — 2026-06-24

> **v1.0.0 L4 验收通过** — A1-A5 全部完成，代码质量审查通过，VFY-005 修复已验收。

### Added
- **A1** `install.ps1` 一键部署：检测 Python 3.11+、创建 venv、安装依赖、初始化目录结构、PaddleOCR 模型预热
- **A2** 增强 `run.bat`：Qdrant/Ollama 健康检查 + 依赖完整性检测 + 守望守护进程启动 + 优雅关闭顺序 + Step 7b 模型预热
- **A3** YAML 配置化：`config/settings.py` 加载器（11 项可配置参数），`pipe_cfg.yaml` 默认配置，`.env` 覆盖 YAML
- **A4** 守望文件夹 v2：`watcher.py` 统一收件箱 + JSONL 状态追踪 + 内容驱动保留策略 + 15 种故障 x 5 种策略
- **A5** OCR 接入管道：
  - `text_pipeline.extract_text()` 新增图片格式支持（.jpg/.jpeg/.png/.bmp/.tiff/.tif/.webp）
  - `text_pipeline.extract_text()` 新增混合 PDF 支持（先提取文本，失败则用 OCR）
  - `run.bat` 新增 Step 7b 模型预热步骤
- watch_v2：新增 `analyze_page_content()` 逐页内容分析函数
- watch_v2：新增队列溢出文件定期救援扫描 `_rescue_orphaned_files()`
- hub 页面：watch_v2 状态监控入口

### Fixed
- **VFY-005** `run.bat` 扁平结构重写已通过 L4 用户验收
- `run.bat` 第132行硬编码 `D:\qdrant\qdrant.exe` 路径 → 替换为自动检测逻辑
- `run.bat` PowerShell 语法错误 → 重写
- `run.bat` 中文乱码 → 第2行加 `chcp 65001 > nul`
- `run.bat` Step 2 包导入测试缺失 PaddleOCR → 增加检测
- `run.bat` Step 5 标注错误（两个"5b"）→ 第 150 行改为"5c"
- `run.bat` `for /f` 读取含空格路径失败 → 统一加 `usebackq` 参数
- `run.bat` 嵌套 `( )` 块中 `%ERRORLEVEL%` stale 值 → 重写为扁平 goto 结构
- `run.bat` 正常退出后错误落入 `:error_exit` → 加 `goto :eof`
- `run.bat` Step 1 端口 8080 清理不可靠（Bug #471）
  - 新增 `scripts/port_cleanup.ps1`: Get-NetTCPConnection + taskkill /F 三层杀戮
- `run.bat` Step 5 Qdrant 僵尸进程未处理（Bug #471）
  - `qdrant_helper.ps1` detect 新增 ZOMBIE 检测 + 自动重启
- `run.bat` Step 5 调用 `qdrant_helper.ps1 -Action start` 失败 → 新增 `start` action
- `run.bat` Step 3 配置哈希文件写入权限错误（Bug #471）→ 改用 TEMP
- 修复 Qdrant 检测 PowerShell stdout 污染导致误判（Bug #467）
- 修复搜索结果文档名称显示"未知"（Bug #468）→ 4 文件兜底填充
- `main.py` Qdrant 连接重试（3 次/5s）→ 避免启动竞争
- `text_pipeline.py` 硬编码路径 → 动态获取 `sys.executable`
- `kb_query.py` `get_facet_stats()` 变量名错误 → 修正
- `kb_query.__version__` 版本号 → `"1.0.1"`
- `text_pipeline/__init__.py` 公共 API 补全 → `chunk_text()` / `embed_text()`
- watch_v2：`classify_document()` 参数名错误 → 全功能修复
- watch_v2：成功后不写 done 状态 → keep_file 重启重复处理修复
- watch_v2：needs_review 状态刚写入就被自删 → 修复
- watch_v2：重复文件留在 inbox 导致无限循环 → 修复
- watch_v2：`analyze_page_content()` 不传配置阈值 → 修复
- watch_v2：基础设施故障改为立即 retry 不阻塞
- watch_v2：OCR 就绪检查改用轮询代替热循环
- watch_v2：全模块 `except Exception` → 精确异常类型（20+ 项）
- watch_v2：`_cleanup_expired_states` 重写为两遍流式扫描 + 原子替换
- watch_v2：`_load_state` 锁粒度优化
- watch_v2：`_pending_removals` 集合加锁消除三路竞争
- watch_v2：`_remove_state` 参数从 filehash 改为 filepath 消除悬空状态
- watch_v2：`_rescue_orphaned_files` 增加重试上限 + infra 检查
- watch_v2：优雅关闭支持（SIGINT/SIGTERM + 状态修复）
- embed 容错：批量嵌入失败回退逐条时非首个块零向量占位
- 搜索阶段 P1：`_sanitize_html()` 白名单 XSS 防御
- 搜索阶段 P1：分组去重改为保留 Top-N chunks/文档
- 搜索阶段 P1：`get_facet_stats()` 加 TTL 缓存
- 混合搜索：稀疏向量命名向量格式修复（4/4 测试通过）
- 代码质量重构：`search_engine.py` / `watcher.py` / `kb_query.py` / `ingest_pipeline.py` 函数拆分

---

## [v0.9.0] — 2026-06-23

### Added
- **D1 侧边栏 5→4** — 删除「文档管理」和「知识中枢」入口，合并为「📚 知识库管理」
- **D2 仪表盘重设计** — 卡片式 4 列统计（总文档/待审核/死信/知识库）+ 20 条活动时间线 + 快速入口
- **D3 文档浏览器** — `/hub` 新增「浏览」标签：全文搜索 + 4 分面过滤 + 排序 + 批量删除 + 快览弹窗
- **D4 文档详情页** — `/doc/{id}` 独立页面：28 字段分组 + 分块列表 + 来源追踪
- **D5 批量上传** — 摄入页 `multiple=True` + 全自动管路（提取→分类→入库）+ 结果卡片
- **D6 操作时间线** — JSON Lines 格式 `activity_log.jsonl`，操作自动追加
- **activity_log.py** — 新建 `utils/activity_log.py` 模块（`log_activity()` + `read_recent_activities()`）

### Changed
- `/hub` 标签从 3 个（概览/待审核/死信）扩展为 4 个（概览/浏览/待审核/死信）
- 知识库管理（创建/清空/切换）折叠至仪表盘底部展开区

### Fixed
- `ui.slider` 不支持 `label` 参数（NiceGUI 3.13.0 API 变更）→ 用 `ui.markdown` 替代

---

## [v0.8.0] — 2026-06-22

> **搜索优化 + 审核队列** — 混合检索 + 重排序 + 置信度路由 UI 全线落地。

### Added
- S1 混合查询：原生 Qdrant Query API（prefetch + RRF fusion），稠密向量 + BM25 并行搜索
- S1.3 Grouping API：按 doc_id 分组去重，每文档只保留最佳 chunk
- S1.4 量化：int8 标量量化，内存降低约 75%
- S1.5 ACORN 过滤：搜索带过滤条件时自动启用
- S2 重排序：嵌入模型对 Top-K 结果重新打分
- S3 重排序可配置：引擎配置页面新增「🔀 重排序」标签页
- R1 置信度阈值可配置：引擎配置「⚙️ 系统」标签页高/低阈值滑动条
- R2 待审核队列 UI：知识中枢新增「📋 待审核」标签页
- R3 死信队列 UI：知识中枢新增「🗑️ 死信队列」标签页
- doc_manager.py 增强：`list_documents()` 新增 overall_confidence/needs_review/content_preview 字段

### Fixed
- 向量格式：`ingest_pipeline.py` 中稠密与稀疏向量字段分离
- 摄入管线：`_step_build_payloads` 补充 sparse_vectors 传参
- 移除：旧 `hybrid_search()` 和 `_keyword_search()`（被原生 query API 替代）

### Changed
- 版本路线调整：知识关系网推迟至 v1.1.0

---

## [v0.7.0] — 2026-06-21

### Fixed
- #1 P0: `kb_query.py` 五层职责混在一起
- #2 P0: `page_ingest()` 366 行
- #3 P1: `ingest()` 302 行
- #4 P1: `classify_document()` 159 行
- #5 P1: 返回值格式不统一
- #6 P2: `panel_funcs.py` 编辑对话框 99 行
- #7 P2: `config/classifications.py` 720 行

---

## [v0.6.1] - 2026-06-21

> **代码质量重构 I** — main.py 页面拆分，降低主文件复杂度。

### Changed
- `main.py` 从 1213 行精简到 348 行（减少 71%）
  - 页面函数拆分到 `pages/*.py` 独立模块：
    - `pages/ingest.py` — 文档注入页面（/）
    - `pages/search.py` — 智能检索页面（/search）
    - `pages/hub.py` — 知识中枢页面（/hub）
    - `pages/config.py` — 引擎配置页面（/config）
    - `pages/manage.py` — 文档管理页面（/manage）
  - 共享状态移到 `utils/state.py`（STATE 字典）
  - 共享 UI 函数移到 `utils/ui_shared.py`（render_chunk_card）

---

## [v0.6.0] - 2026-06-21

> **摄入管道阶段二：元数据标注优化** — 三层并行管道替代单步 LLM 分类。

### Added
- 三层并行分类管道 `classify_document()`
  - **Layer 1（并行推断）**: `extract_file_fields()` + `match_all_rules()`
  - **Layer 2（合并仲裁+兜底）**: `merge_parallel()` → `call_llm_for_missing()` → `fill_defaults()`
  - **Layer 3（程序计算置信度）**: `calculate_confidence()` 不依赖 LLM 自报
- 规则引擎 `CLASSIFY_RULES`（`config/classifications.py`）
  - 覆盖 4 个分面字段 + 40+ 关键词/正则模式
- AnnotatedField 数据结构：`{value, source, confidence}`
- 来源徽章 UI：📎 file / 📐 rule / 🤖 llm / 👤 user / ⚙️ default
- 置信度路由：>=0.75 直接入库 / 0.40-0.75 待审核 / <0.40 死信队列
- 字段权重常量 `FIELD_WEIGHTS` + 智能默认值 `SMART_DEFAULTS`
- 手动输入 5000 字截断提醒

### Changed
- `_call_llm_api()` temperature: 0.3 → 0（确定性输出）
- `auto_classify()` 降级为薄包装
- 结果面板 UI 重构：下拉菜单 → 卡片式面板（`panel_funcs.py`）
  - 19 字段 5 组展示 + 配置驱动渲染 + 点击编辑 + 置信度进度条
- Layer 0 自动填充分离：`detect_language()` + `project_source` 系统填入

### Fixed
- `do_ingest()` 引用已删除 UI 变量 → 重写读取 `PANEL_VALUES`
- 卡片无点击效果 → 添加 `on("click")` 事件绑定
- 编辑后面板不刷新 → `_refresh_panels()`
- 来源徽章文字过长 → 纯图标 + 颜色编码

---

## [v0.5.1] - 2026-06-20

### Fixed
- `get_facet_stats()` 全量 scroll 优化：移除内存积累，改为逐批聚合计数
- G2 遗留语法错误修复：`keyword_domain_map` 后悬空重复字典清除

---

## [v0.5.0] - 2026-06-20

### Added
- G2: L2 管道实现（文件元数据→UDC 推断）
  - 从 metadata 字段（title/author/keywords/source）提取文本
  - 使用 `keyword_domain_map` 推断 UDC 主类

### Fixed
- G1: `normalize_facet_values()` 增强（模糊映射表）
  - 新增 `FUZZY_FACET_MAPPING` 模糊映射表（4 个分面字段）
- C10: 为 6 处 `except:pass` 添加日志记录
- D4: `_text_hash()` 16-bit → 32-bit
- F6+S3: `search()` 返回 `content_hash` 字段
- S4: `search()` 返回 `doc_uid` 字段

---

## [v0.4.9] - 2026-06-20

### Fixed
- P1 问题修复（D1/U7/S1/F4）：
  - D1+U7: `trust_score` 统一为 0-5 刻度
  - S1: Payload Index 补充 `needs_review` 字段
  - F4: `search_by_doc_id()` 返回 `needs_review` 字段
  - D2: 实现 `detect_encoding()` 函数（chardet + 兜底链）
- `schema.md` 更新为 0-5 刻度

---

## [v0.4.8] - 2026-06-19

### Fixed
- U4: 搜索结果卡片显示新字段
- F4: `search_by_doc_id()` 返回 `needs_review` 字段
- 新增 `render_chunk_card()` 统一调用

---

## [v0.4.7] - 2026-06-19

### Fixed
- F5: `list_documents()` 支持 `needs_review` 过滤 + UI 审核状态过滤器
- C11: `PROJECT_PLAN.md` 更正 1f 标记
- F7: `kb_query.py` 标记 6 个未使用函数为废弃

---

## [v0.4.6] - 2026-06-19

### Fixed
- U2+U3: 阶段2 AI 分析后显示确认卡片

---

## [v0.4.5] - 2026-06-18

### Fixed
- P1 问题修复（17项）：metadata 合并 / 中文切片保护 / 编码检测 / 废弃字段清理 / 文档格式提取 / JSON 嵌套提取 / 枚举守卫 / 自动分类 / Payload Index 创建

### Changed
- 项目命名重构：Athanor → Citrinitas
  - main.py / run.py / run.bat 标题更新
  - Qdrant 集合名 `athanor_v1` 保留不变

### Fixed
- 启动崩溃：Qdrant 离线时 `_r` 未定义 NameError

### Added
- 新增 BLUEPRINT.md + FLOWCHART.md

---

## [v0.4.4] - 2026-06-18

### Fixed
- XSS 漏洞：`_format_evidence_text()` 和 `_render_report_html()` 转义修复

### Added
- 新增文档管理页面 `/manage` + `kb_query.py` 文档管理函数
- 侧边栏新增「📄 文档管理」导航链接

---

## [v0.4.3] - 2026-06-18

### Fixed
- language 字段永远默认 "zh" → Unicode 区块统计真检测
- `_split_long_paragraph()` 从未使用 overlap 参数 → 相邻 chunk 重叠拼接
- embed 逐条回退时单条失败整批丢弃 → 跳过失败块
- source 字段极端路径 None → 加兜底
- `_extract_images()` 仅识别 `[image: path]` → 三段提取

---

## [v0.4.2] - 2026-06-17

### Fixed
- LLM 配置因 `.env` 加载顺序导致永远为空 → `os.environ.get()` 实时读取
- WebSocket 超时导致搜索时 connect lost → `reconnect_timeout=120`
- 系统状态一直显示离线 → QDRANT_URL 改为 `127.0.0.1` + 动态初始化
- 完整报告 `file://` 链接浏览器安全策略阻止 → `/reports/{filename}` FileResponse 路由
- 端口冲突反复出现 → `run.bat` 自动杀旧进程
- ocr_image() 公共入口函数缺失 → 创建包装函数
- search() 返回字段名不匹配 → 统一字段名
- ingest() 参数错误 → text 内容改为关键字参数

---

## [v0.4.1] - 2026-06-15

### Added
- 分面分类 v5.0：UDC 9 主类替代自定义 9 域
- temporal_nature / epistemic_status 分面
- NiceGUI SPA 迁移
- auto_classify() 四层管道增强

### Changed
- domain 分面：9 大中文主题域 → UDC 9 主类
- Web UI：Streamlit 多页面 → NiceGUI 单文件 SPA

### Removed
- objectivity 字段 / project_source 硬编码选项

---

## [v0.4.0] - 2026-06-15

### Added
- LLM 自动分类 + 两阶段摄入管线
- 共享表单组件 utils/ingest_ui.py
- AI 分析结果可视化：5 列度量卡片

### Changed
- 文档注入页面重构：660 行 → ~240 行

---

## [v0.3.0] - 2026-06-15

### Added
- 分面分类 v4.0：15 种内容类型 x 9 大主题域 x 6 级生命周期
- 通用关系字段：8 种关系类型
- 知识管理面板 + 分面统计仪表盘

### Changed
- 字段精简：49 → 36 字段
- Qdrant Payload Index 从 0 扩展到 11 个

### Fixed
- Qdrant facet filter should/min_should 语法失效
- update_metadata PUT /points 404
- 多个 UI 拼写错误

### Removed
- content_stage / task_id / updated_at / quality_score / category 废弃字段

---

## [v0.2.0] - 2026-06-14

### Added
- Streamlit 多页面架构（app.py + 4 页面导航）
- 文档注入/智能检索/知识中枢/引擎配置页面
- 核心逻辑（kb_query.py）与 UI 层完全分离
- LLM 后端切换至 DeepSeek API

---

## [v0.1.0] - 2026-06-14

### Added
- OCR 摄入功能（PaddleOCR / PPStructureV3）
- 向量搜索（Qdrant + qwen3-embedding:4b）
- LLM 合成（DeepSeek API）+ 引用标注
- 表格行拆分 + 引用重编号
- KaTeX 服务端公式渲染
- HTML 报告生成 + 去重过滤（SHA256）

---
