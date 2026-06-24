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

## [v1.0.0] — 2026-06-24

> **v1.0.0 开发完成，待最终验证** — A1-A5 全部完成，代码质量审查通过。

### Added
- **A1** `install.ps1` 一键部署：检测 Python 3.11+、创建 venv、安装依赖、初始化目录结构、PaddleOCR 模型预热
- **A2** 增强 `run.bat`：Qdrant/Ollama 健康检查 + 依赖完整性检测 + 守望守护进程启动 + 优雅关闭顺序 + Step 7b 模型预热
- **A3** YAML 配置化：`config/settings.py` 加载器（11 项可配置参数），`pipe_cfg.yaml` 默认配置，`.env` 覆盖 YAML
- **A4** 守望文件夹 v2：`watcher_v2.py` 统一收件箱 + JSONL 状态追踪 + 内容驱动保留策略 + 15 种故障 × 5 种策略
- **A5** OCR 接入管道：
  - `text_pipeline.extract_text()` 新增图片格式支持（.jpg/.jpeg/.png/.bmp/.tiff/.tif/.webp，自动调用 `ocr_image()`）
  - `text_pipeline.extract_text()` 新增混合 PDF 支持（先提取文本，失败则用 OCR 逐页识别）
  - 新增 `warmup.py` 模型预热脚本（PaddleOCR + Ollama 嵌入模型，避免首次调用慢）
  - `run.bat` 新增 Step 7b 模型预热步骤（启动 Web UI 前预热）
- watch_v2：新增 `analyze_page_content()` 逐页内容分析函数（5 信号判定可删性）
- watch_v2：新增队列溢出文件定期救援扫描 `_rescue_orphaned_files()`
- hub 页面：watch_v2 状态监控入口

### Fixed
- watch_v2：修复 `classify_document()` 参数名错误导致全功能崩溃
- watch_v2：_cleanup_expired_states 的 CLEANUP_INTERVAL 外部化为配置项 WATCH_V2_CLEANUP_INTERVAL (P3-1)
- watch_v2：OCR 回退对多页 PDF 含多张图片时重复调用 _ocr_image，添加结果缓存避免重复 OCR (P3-2)
- watch_v2：_rescue_orphaned_files() 可能把已在队列中的文件重复入队，添加 _queued_files 集合跟踪 (P3-3)
- watch_v2：_check_lock_file() 使用 ctypes.windll（Windows 专用），替换为 os.kill(pid, 0) 跨平台兼容 (P3-4)
- watch_v2：基础设施重检间隔 loop_count % 15 硬编码外部化为 WATCH_V2_INFRA_RETRY_INTERVAL 配置项 (P3-5)
- watch_v2：精确化 5 处 except Exception 为具体异常类型，剩余 2 处添加注释说明防御性兜底原因 (P3-6)
- watch_v2：修复成功后不写 done 状态导致 keep_file 重启重复处理
- watch_v2：修复 needs_review 状态刚写入就被 `_remove_state()` 自删
- watch_v2：修复重复文件留在 inbox 导致无限循环
- watch_v2：修复 `analyze_page_content()` 不传配置阈值导致参数架空
- config：`_print_summary()` 改为打印 v2 配置项（原打印 v1 错误配置）
- config/watch_v2：删除死代码 `WATCH_V2_POLL_INTERVAL` 和 `WATCH_V2_KEEP_FILE`
- main：`os._exit(0)` 前调用 `stop_watcher_v2()` 优雅释放锁资源 (#329, B10)
- watch_v2：基础设施故障改为立即 retry 不阻塞处理循环 (#330, B13)
- hub.py：删除无锁 file_state.jsonl 重复实现，统一委托 watcher_v2 (#331, B19/B29)
- watch_v2：`_process_file()` 内重复导入提升至模块顶部 (#332, B25)
- watch_v2：`_cleanup_expired_states()` 新增频率控制与去重优化 (#333, B40/B41/B48)
- watch_v2：`_process_file` 添加 cancel_event 取消信号，超时线程优雅退出 (#334)
- watch_v2：`_process_file_with_timeout` 超时后检查策略并重新入队 (#335)
- watch_v2：`_remove_state()` 改为延迟批量删除，消除每文件全量 I/O 重写 (#336)
- watch_v2：`_rescue_orphaned_files()` 增加基础设施检查，避免 infra down 时无效救援循环 (#337)
- watch_v2：`_pending_removals` 集合加 `_state_lock` 保护，消除三路竞争条件 (#338)
- watch_v2：`_process_file` 增加 3 个取消检查点（提取后/分类前/摄入前），加快超时响应 (#339)
- watch_v2：`_file_ready` 改为 3 状态返回值（ready/not_ready/not_a_file），消除异常静默吞没 (#340)
- watch_v2：`_persist_overflow_file` 文件名改用日期戳，filename.log 加日期防止日志被覆盖 (#341)
- watch_v2：`_remove_state` 新增重复文件自动清理功能，删除 dup_{hash} 标记文件 (#342)
- watch_v2：`_migrate_v1_state` 日志级别从除错误改为警告，修正迁移成功判断逻辑 (#343)
- watch_v2：pipeline_results 传递增加空值守卫，避免 KeyError 崩溃 (#344)
- watch_v2：文件复用到实际处理之间增加二次取消检查 (#345)
- watch_v2：文件删除后移动失败改用文件存在检查+content_hash 验证 (#346)
- watch_v2：inbox 文件复用逻辑加锁+exists 二次确认，消除 TOCTOU 竞态 (#347)
- watch_v2：`_remove_state` 参数从 filehash 改为 filepath，消除悬空状态 (#348)
- watch_v2：remove_state 增加延时重试 + exists 最终确认，避免 NFS 延迟误判 (#349)
- watch_v2：`_rescue_orphaned_files` 增加重试计数上限（max_retries=3），防止无限循环 (#350)
- watch_v2：OCR 就绪检查改用轮询代替热循环等待 (#351)
- watch_v2：`_handle_invalid` 新增重复文件自动清理 (#352)
- watch_v2：重复哈希文件在 `_process_file` 入口处立即 skip (#353)
- watch_v2：4 处 `except Exception: pass` 替换为精确异常+日志 (#354)
- watch_v2：`_processing_loop_v2` 主循环顶层异常守卫 catch-all→log+retry (#355)
- watch_v2：result_msg None 引发 TextPipeline.detect_language 崩溃 → 类型守护 (#356)
- watch_v2：`_load_state` 锁粒度优化 — 文件读取出锁，仅 _pending_removals.copy() 在锁内 (#379)
- watch_v2：extract_empty 后增加 OCR 回退检查 — PDF/图片重质内容文件不再被误判为无内容 (#380)
- watch_v2：`_cleanup_expired_states` 重写为两遍流式扫描 + `os.replace` 原子替换 — 彻底消除 OOM 风险 (#381, #382)
- watch_v2：两处 `daemon=True` 线程添加注释说明 content_hash 去重安全网原理 (#383)
- watch_v2：全模块 `except Exception` → 精确异常类型（OSError/RequestException/Empty/JSONDecodeError/ValueError）(#384)
- watch_v2：`queue.put(timeout=0.5)` 硬编码值外部化为 `WATCH_V2_QUEUE_PUT_TIMEOUT` 配置项 (#385)
- watch_v2：删除未使用的 STRATEGIES 字典（转为文档注释保留信息）(#386)
- 修复混合搜索（A5）：稀疏向量未存储到 Qdrant（命名向量格式错误）
  - 根因：`build_payloads()` 使用旧格式，Qdrant v1.10+ 忽略 `"sparse_vectors"`
  - 修复：`qdrant_client.create_collection()` 使用命名向量格式
  - 修复：`ingest_pipeline.build_payloads()` 使用命名向量格式
  - 修复：`search_engine.search()` prefetch 指定 `"using": "dense"`
  - 验证：4/4 测试点均正确存储，混合搜索正常工作
- **代码质量重构**：
  - `search_engine.py`：提取 `_build_qdrant_filter()`、`_query_qdrant_rrf()`、HTML渲染辅助函数，函数长度全部 < 50行
  - `watcher_v2.py`：将 `import kb_query` 从函数体内移到模块顶部
  - `kb_query.py`：新增 `route_by_confidence()` 共用函数（置信度三档路由）
  - `pages/ingest.py` / `watcher_v2.py`：使用 `kb_query.route_by_confidence()` 替换内联逻辑，消除重复
  - `ingest_pipeline.py`：提取 `_prepare_metadata()`、`_build_point()`，修复未使用导入
  - `watcher_v2.py`：提取 `_do_prechecks()`、`_do_ocr_fallback()`、`_do_classify()`、`_do_ingest()`、`_do_post_ingest()`，修复语法错误
- **A4 守望文件夹修复**（P0-P2 缺口全部修复）：
  - 修复 `classify_document()` 参数名错误导致全功能崩溃
  - 修复成功后不写 done 状态导致 keep_file 重启重复处理
  - 修复 needs_review 状态刚写入就被 `_remove_state()` 自删
  - 修复重复文件留在 inbox 导致无限循环
  - 修复 `analyze_page_content()` 不传配置阈值导致参数架空
  - 基础设施故障改为立即 retry 不阻塞处理循环
  - OCR 就绪检查改用轮询代替热循环等待
  - 全模块 `except Exception` → 精确异常类型
  - 队列溢出、孤儿恢复、状态清理等 20+ 项修复
- **A4 守望文件夹 P0-P2 bug 修复**（v1.0.0 最终验证前审查发现）：
  - 修复 7 处 `except Empty` → `except Full`（`queue.put()` 超时抛 `Full`，不是 `Empty`），队列满时文件不再静默丢失
  - 修复 `_scan_existing_files_v2()` 变量名错误（`filepath` → `fp`），重复入队检查恢复正常
  - 修复 `metadata` 缺少 `needs_review` 字段，UI 待审核标签页现在能正确展示守望文件夹产生的低置信度文件
  - 新增 `WatchHandlerV2.on_moved()` 方法，剪切粘贴文件到 `inbox/` 时正常触发处理
  - 修复 `WATCH_V2_INFRA_RETRY_INTERVAL` 重复定义（`config/settings.py` 第 275 行和第 297 行），`pipe_cfg.yaml` 配置项现在有效
  - **优雅关闭支持**（F6 — P2）：
    - 新增 `_signal_handler()` 信号处理器，`start_watcher_v2()` 注册 `SIGINT`/`SIGTERM`
    - `stop_watcher_v2()` 等待处理线程退出（最多 `PROCESS_TIMEOUT` 秒）
    - 新增 `_fix_incomplete_states()` 函数，优雅退出时把非终态改成 `retry`，下次启动时自动恢复

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
### Fixed
- #1 P0: `kb_query.py` 五层职责混在一起 ✅
- #2 P0: `page_ingest()` 366 行 ✅
- #3 P1: `ingest()` 302 行 ✅
- #4 P1: `classify_document()` 159 行 ✅
- #5 P1: 返回值格式不统一 ✅
- #6 P2: `panel_funcs.py` 编辑对话框 99 行 ✅
- #7 P2: `config/classifications.py` 720 行 ✅

---

## [v0.6.1] - 2026-06-21

> **代码质量重构 I** — main.py 页面拆分，降低主文件复杂度。

### Changed
- ♻️ `main.py` 从 1213 行精简到 348 行（减少 71%）
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

> **摄入管道阶段二：元数据标注优化** — 三层并行管道替代单步 LLM 分类，实现可复现的标签生成。

### Added
- ✨ 三层并行分类管道 `classify_document()`
  - **Layer 1（并行推断）**: `extract_file_fields()` 从文件元数据提取 + `match_all_rules()` 规则引擎匹配，两者独立并行
  - **Layer 2（合并仲裁+兜底）**: `merge_parallel()` 按优先级合并（file > rule）→ `call_llm_for_missing()` 仅对缺口字段调 LLM → `fill_defaults()` 填默认值
  - **Layer 3（程序计算置信度）**: `calculate_confidence()` 按字段权重 × 来源置信度计算，不依赖 LLM 自报
- ✨ 规则引擎 `CLASSIFY_RULES`（`config/classifications.py`）
  - 覆盖 4 个分面字段：content_type / domain / temporal_nature / epistemic_status
  - 40+ 关键词 + 正则模式（如 `GB/T\s*\d+` 匹配国标编号）
  - domain 多选特殊处理（收集所有命中值去重）
- ✨ AnnotatedField 数据结构：每个字段携带 `{value, source, confidence}`
  - source 取值：file / rule / llm / user / default
  - 来源置信度：file=1.0, rule=0.85, llm=0.60, user=1.0, default=0.0
- ✨ 来源徽章 UI：AI 分析后每个字段旁显示来源标记
  - 📎 file（蓝）/ 📐 rule（绿）/ 🤖 llm（琥珀）/ 👤 user（紫）/ ⚙️ default（灰）
- ✨ 置信度路由：≥0.75 直接入库 / 0.40–0.75 待审核 / <0.40 死信队列
- ✨ `ingest()` 新增 `field_sources` + `overall_confidence` 参数，写入 Qdrant payload
- ✨ 字段权重常量 `FIELD_WEIGHTS`：content_type 0.25 / domain 0.25 / temporal_nature 0.20 / epistemic_status 0.20 / keywords 0.10
- ✨ 智能默认值 `SMART_DEFAULTS`：缺口字段兜底填充
- ✨ 手动输入 5000 字截断提醒

### Changed
- 🔄 `_call_llm_api()` temperature: 0.3 → **0**（确定性输出，保证可复现性）
- 🔄 `auto_classify()` 降级为薄包装：内部调用 `classify_document()`，旧调用方零改动兼容
- 🔄 LLM 调用重构：`call_llm_for_missing()` 动态构建 prompt，仅要求生成缺口字段，不再要求 confidence
- 🔄 UI 重构 `do_ai_analyze()`：调用 `classify_document()`，填充主表单 + 显示来源徽章
- 🔄 UI 重构 `do_ingest()`：删除死代码合并逻辑，置信度路由改用程序计算值，用户修改字段标记 source="user"
- 🔄 **结果面板 UI 重构（T2~T7）**
  - 下拉菜单全部替换为**卡片式结果面板**（`panel_funcs.py`）
  - 19 个字段按 5 组展示：分面分类(4) / 内容标识(4) / 知识属性(6) / 来源信息(3) / 时间戳(2)
  - 高级选项折叠显示（`ui.expansion`），减少初始屏占用
  - 点击字段卡片弹出编辑对话框（按 `widget` 类型自适应：下拉/多选/输入/开关/滑块/日期）
  - 编辑后面板自动刷新，来源徽章更新为 👤 user
  - 面板顶部显示整体置信度进度条 + 来源统计
  - `FIELD_DISPLAY_CFG` 配置驱动渲染，新增 `field_cfg.py`
  - `do_ingest()` 改为读取 `PANEL_VALUES` 全局字典，不再依赖 UI 组件 `.value`
  - Layer 0 自动填充分离：`detect_language()` + `project_source` 系统自动填入，不占用 LLM 推断额度

### Fixed
- 🐛 `main.py` `do_ingest()` 引用已删除的 UI 变量（`domain`/`content_type` 等）→ 重写为读取 `PANEL_VALUES`
- 🐛 `panel_funcs.py` 卡片无点击效果 → 添加 `on("click")` 事件绑定
- 🐛 编辑后面板不刷新 → 编辑确认后调用 `_refresh_panels()`
- 🐛 来源徽章显示文字过长 → 改为纯图标 + 颜色编码

### Resolved (在重构中自然消失，非 Bug 修复)
- ✅ I016: AI 分析按钮双重 handler 绑定 → `on_ai_analyze` 整个函数删除
- ✅ I016a: 重复下拉菜单+重复入库按钮 → confirm_card 代码删除
- ✅ I017: do_ai_analyze 不传 metadata → `classify_document()` 签名含 `file_metadata` 参数
- ✅ I018: do_ingest 死代码合并逻辑 → 整段重写
- ✅ I019: AI 分析不可复现 → temperature=0 + 规则引擎扩充 + 程序计算置信度

---

## [v0.5.1] - 2026-06-20

### Fixed
- 🔧 S5: `get_facet_stats()` 全量 scroll 优化
  - 移除 `all_points = []` 内存积累，改为逐批聚合计数
  - 内存占用与知识库规模解耦（不再随点数增长）
- 🔧 G2 遗留语法错误修复：`keyword_domain_map` 后悬空重复字典片段清除

---

## [v0.5.0] - 2026-06-20

### Added
- ✨ G2: L2 管道实现（文件元数据→UDC 推断）
  - 从 `metadata` 字段（title/author/keywords/source）提取文本
  - 使用 `keyword_domain_map` 推断 UDC 主类
  - `keyword_domain_map` 移到 L2 前，L2/L3 共用
  - 如果 L2 已推断 domain，跳过 L3

### Fixed
- 🔧 G1: `normalize_facet_values()` 增强（模糊映射表）
  - 新增 `FUZZY_FACET_MAPPING` 模糊映射表（4 个分面字段）
    - `content_type`: 中文/英文变体 → 标准 key
    - `domain`: 中文描述/UDC 代码 → UDC 主类
    - `temporal_nature`: 中文描述 → evergreen/timeboxed/transient
    - `epistemic_status`: L0/L1/L2 简写/中文描述 → 标准 key
  - `normalize_facet_values()` 增强：优先查 `FUZZY_FACET_MAPPING`（精确/大小写不敏感/部分匹配）
- 🔧 C10: 为 6 处 `except:pass` 添加日志记录
  - L495: PPStructure 失败回退 PaddleOCR
  - L636: 批量嵌入失败回退逐条
  - L776: Payload 索引创建失败（可忽略）
  - L823: 集合创建异常（可忽略）
  - L991: 日志写入失败（可忽略）
  - L1012: scroll 单页失败（跳过）
- 🔧 D4: `_text_hash()` 16-bit → 32-bit（降低碰撞风险）
- 🔧 F6+S3: `search()` 返回 `content_hash` 字段
- 🔧 S4: `search()` 返回 `doc_uid` 字段

---

## [v0.4.9] - 2026-06-20

### Fixed
- 🔧 P1 问题修复（D1/U7/S1/F4）：
  - D1+U7: `trust_score` 统一为 0-5 刻度（0=未评级），`TRUST_SCORE_LABELS` 加入 `0` 键，`auto_classify` prompt 修正，结果加 clamp 防御
  - S1: Payload Index 补充 `needs_review` 字段（`_ensure_collection()` + `create_collection()`）
  - F4: `search_by_doc_id()` 返回 `needs_review` 字段
  - D2: 实现 `detect_encoding()` 函数（chardet + 兜底链）
- `schema.md` 更新为 0-5（两处）

---

## [v0.4.8] - 2026-06-19

### Fixed
- U4: 搜索结果卡片现显示新字段（content_type, domain, epistemic_status, temporal_nature, needs_review）
- F4: `search_by_doc_id()` 返回 `needs_review` 字段
- 新增 `render_chunk_card()` 辅助函数，三处搜索结果展示统一调用

---

## [v0.4.7] - 2026-06-19

### Fixed
- F5: `list_documents()` 支持 `needs_review` 过滤参数（后端）+ 文档管理页面添加审核状态过滤器（前端 UI）
- C11: `PROJECT_PLAN.md` 更正 1f 标记（`metadata_source` 已废弃）
- F7: `kb_query.py` 标记 6 个未使用函数为废弃（将在 v0.5.0 删除）

---

## [v0.4.6] - 2026-06-19

### Fixed
- U2+U3: 阶段2 AI 分析后显示确认卡片，用户可审核元数据再摄入
- 新增 AI 分析确认卡片（阶段二），展示文件元数据 + AI 推断结果

---

## [v0.4.5] - 2026-06-18

### Fixed
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

### Changed
- 🔄 项目命名重构：Athanor → Citrinitas（代码内部全量改名）
  - main.py / run.py / run.bat：标题 / 打印 / 窗口名更新
  - config / utils / classifications：注释更新
  - sync_ima.py：所有引用更新
  - .codebuddy/CODEBUDDY.md：启动路径更新
  - venv 重建为 `D:\citrinitas\venv`
  - Qdrant 集合名 `athanor_v1` 保留不变（避免数据迁移）

### Fixed
- 🐛 启动崩溃：Qdrant 离线时 `_r` 未定义 NameError

### Added
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
