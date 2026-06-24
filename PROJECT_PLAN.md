# Citrinitas — 项目主计划

> 本文档管理功能路线图和设计决策。版本变更记录见 `CHANGELOG.md`，Bug 跟踪改用 GitHub Issues。

最后更新: 2026-06-24 (v1.0.0 ✅ 开发完成 — 剩余验证)

---

## 当前状态

- 当前版本：**v1.0.0 🔍 开发完成，待最终验证**（A1-A5 全部完成，代码质量审查已通过）
- 活跃 Bug：**0**
- Git 状态：main 分支，代码已推送到 GitHub (commit 9978c1a)

---

## 段落索引（grep 关键词）

| 想找什么 | grep 关键词 |
|-----------|-------------|
| 当前状态 | `## 当前状态` |
| 版本路线图 | `## 一、版本路线图` |
| 当前版本详情 | `## 二、当前版本` |
| 设计决策 | `## 三、设计决策` |
| 竞品学习 | `## 四、竞品学习路线` |
| 架构原则 | `## 五、架构原则` |
| 远期待办 | `## 六、远期待办` |
| 管理文件体系 | `## 七、管理文件体系` |
| 代码重构路线 | `## 八、代码质量重构路线` |

---

## 一、版本路线图

> 按「地基 → 框架 → 墙体 → 装修 → 交付」逐层递进。

| 版本 | 状态 | 层级 | 代号 | 核心交付 |
|------|:----:|:--:|------|---------|
| v0.1.0 | ✅ | 地基 | 核心引擎 | CLI 向量搜索 + LLM 问答 + OCR + KaTeX |
| v0.2.0 | ✅ | 地基 | Web UI MVP | NiceGUI 4 页面 |
| v0.3.0 | ✅ | 框架 | 分面分类 v4.0 | 36 字段分组 + 关系管理 |
| v0.4.0 | ✅ | 框架 | 智能摄入 | LLM 自动分类 + 两阶段管线 |
| v0.4.1 | ✅ | 框架 | 分面分类 v5.0 | UDC + temporal/epistemic + NiceGUI 迁移 |
| v0.4.2 | ✅ | 框架 | Bug 修复汇总 | 8 项 PATCH 修复 |
| v0.4.3 | ✅ | 框架 | 摄入管线修复 | 5 项 P1 修复 |
| v0.4.4 | ✅ | 框架 | 文档管理 + XSS 修复 | 文档管理页面 `/manage` + XSS 漏洞修复 |
| v0.4.5 | ✅ | 框架 | P1 问题修复 | 17 项 P1 修复 |
| v0.4.9 | ✅ | 框架 | P1 剩余问题修复 | D1+U7/S1/F4 修复 |
| v0.5.0 | ✅ | 框架 | L2 管道 | auto_classify 增强 + normalize_facet_values |
| v0.5.1 | ✅ | 框架 | 内存优化 | get_facet_stats 修复 |
| v0.6.0 | ✅ | 框架 | 卡片式结果面板 | 三层管道 + 配置驱动 UI + 来源徽章 |
| v0.6.1 | ✅ | 框架 | 代码质量重构 I | main.py 页面拆分（1213行→348行） |
| v0.7.0 | ✅ | 框架 | 摄入执行重构 | 阶段三 B1-B4 — ingest() 管道化 + 批量摄入 + 统一返回值 + Nigredo 钩子接口 |
| v0.7.1 | 🔧 | 框架 | OCR 功能修复 | P0 Bug 修复 — 安装 PaddleOCR 3.7 + 修复 on_ocr 回调 + 加「开始识别」按钮 |
| v0.8.0 | ✅ | 墙体 | 搜索优化 + 审核队列 | 混合检索 + 重排序 + 置信度路由 UI 落地 |
| v0.9.0 | ✅ | 装修 | 知识库综合管理 | 侧边栏5→4 + 仪表盘+时间线 + 文档浏览器 + 批量摄入 + 详情页 |
| v1.0.0 | 🔧 | 交付 | 无 UI 管线 | 阶段五 + YAML 配置化 + 桌面一键打包 |
| v1.1.0 | 🔮 | 交付 | 知识关系网 + 检索增强 | NetworkX + Plotly + QA 自动生成 |
| v1.2.0 | 🔮 | 交付 | 移动端 | 微信 Bot + 移动端适配 |

---

## 二、当前版本

### v0.6.0 ✅ 已完成（2026-06-21 验收通过）

### 目标

重构元数据标注管道：从单步 LLM 分类升级为三层并行管道（文件元数据 + 规则引擎并行 → LLM 兜底缺口 → 程序计算置信度），实现可复现的标签生成。同步完成结果面板 UI 重构（卡片式 + 来源徽章 + 高级选项折叠）。

### 摄入管道五阶段路线图

> 摄入管道按五个阶段递进开发，每个阶段独立验收。

| 阶段 | 名称 | 状态 | 版本 | 核心交付 |
|:----:|------|:----:|:----:|---------|
| 一 | 内容准备 | ✅ 完成 | v0.4.0–v0.5.1 | 文件上传 / OCR / 手动输入 + 基础 auto_classify + 入库检索 |
| 二 | 元数据标注 | ✅ 已完成 | v0.6.0 | 三层并行管道 + 规则引擎 + 来源徽章 + 置信度路由 |
| 三 | 摄入执行重构 | ✅ 完成 | v0.7.0 | ingest() 管道化（10 步可配置/可跳过）+ 批量摄入 + Nigredo 钩子接口 |
| 四 | 审核队列 | ✅ 已完成 | v0.8.0 | 置信度阈值可配置 + 待审核/死信队列 UI + 知识中枢审核入口 |
| 五 | 无 UI 管线 | 📋 待开始 | v1.0.0 | 守望文件夹 + 文件夹监控 + YAML 配置化 + 全自动摄入 |

### v0.6.0 已完成的工作

- [x] T1: 核心数据结构（SOURCE_CONFIDENCE / FIELD_WEIGHTS / SMART_DEFAULTS / AnnotatedField）
- [x] T2: 规则引擎（CLASSIFY_RULES 40+ 关键词 + 正则 + domain 多选）
- [x] T3: LLM 重构（temperature→0, call_llm_for_missing 仅补缺口）
- [x] T4: 合并仲裁（merge_parallel file>rule + fill_defaults）
- [x] T5: 置信度计算（calculate_confidence 程序计算）
- [x] T6: classify_document() 主函数（三层管道编排）
- [x] T7: UI 标注面板重构（来源徽章 + 删除 confirm_card）
- [x] T8: ingest() 适配（field_sources + overall_confidence 参数）
- [x] T9: 置信度路由（≥0.75/0.40-0.75/<0.40）
- [x] T10: 5000 字截断提醒

### v0.6.0 集成测试结果

| # | 测试项 | 结果 |
|---|--------|:----:|
| 1 | 纯规则匹配 + 可复现性（同输入同输出） | ✅ |
| 2 | auto_classify() 兼容包装（旧调用方不受影响） | ✅ |
| 3 | 文件元数据优先（file > rule > llm > default） | ✅ |
| 4 | 数学定理文本（evergreen + unverified 信号区分） | ✅ |

### 阶段一验收结果（2026-06-20）

**✅ 核心管道验收通过**：摄入 → auto_classify → normalize → 入库 → 检索 → 分面统计

**⚠️ UI 交互问题 4 项（归属阶段二）**：I016/I016a（按钮双重绑定+重复下拉菜单）、I017（L2 管道未传 metadata）、I018（死代码）→ **已在 v0.6.0 重构中解决**

---

### v0.7.0 ✅ 已完成（2026-06-21 验收通过）

### 目标

重构摄入执行管线：把 `ingest()` 从硬编码流水线拆成可配置管道，支持批量摄入，统一返回值格式，预留 Nigredo（馏析）预存储钩子接口。

### 做了什么

| 任务 | 内容 | 结果 |
|------|------|------|
| B1 | `ingest()` 管道化 | 拆成 10 个独立步骤（`_step_xxx(state)`），新增 `skip_steps` 参数支持跳过步骤 |
| B2 | `ingest_batch()` 批量摄入 | 新增函数，多个文件/文本依次走管道，返回汇总统计 |
| B3 | 统一返回值格式 | `build_payloads()` 返回值从 `tuple` 改为 `dict`（含 `ok/chunks/doc_id/content_hash` 等键） |
| B4 | Nigredo 钩子接口 | 新增 `config/hooks.py`（钩子注册表）+ `docs/pre_store_hook_spec.md`（合约规格）|

### 新增文件

| 文件 | 作用 |
|------|------|
| `config/hooks.py` | 预存储钩子注册表（`register_hook()` / `get_hooks()`）|
| `docs/pre_store_hook_spec.md` | 钩子合约规格（给未来接入的程序看的）|
| `ingest_pipeline.py` | `build_payloads()` 独立模块（B3 从 `kb_query.py` 迁出）|

### 管线步骤（10 步）

```
1. qdrant_check → 2. read_content → 3. dedup → 4. extract_images → 5. chunk
→ 6. embed → 7. pre_store_hooks → 8. build_payloads → 9. write_qdrant → 10. log_ingest
```

可跳过的步骤：`dedup`、`images`、`log_ingest`

### 验证结果

- ✅ 语法检查全部通过
- ✅ 导入链完整（无 NameError）
- ✅ 真实入库测试通过（Qdrant 在线，1 块文本成功入库）
- ✅ 钩子注册/获取正常
- ✅ `build_payloads()` 返回 dict 格式正确

### Nigredo 接口（远期规划）

馏析（Nigredo）远期任务已记录在 `D:\nigredo\docs\citrinitas-hook-interface.md`：
- 在馏析里实现钩子函数
- 从包裹里读出原始内容，补充视频元数据
- （可选）用结构化笔记替换原始字幕
- 把处理完的包裹传回熔知，继续入库流程

---

### v0.9.0 📋 知识库综合管理（2026-06-23 规划）

### 竞品调研

对标 RAGFlow / Dify 2.0 / LLM Wiki / AnythingLLM 四个标杆产品，提取共同规律：
- 三标配页面：仪表盘（一眼看清状态）+ 浏览器（搜索过滤浏览）+ 日志/活动记录
- 关键设计：文档级开关控制、管道节点可见性、操作时间线、知识库健康检查

### 目标

把当前零散的 5 个入口（/ 摄入、/search 搜索、/manage 管理、/hub 中枢、/config 配置）
整合为 4 个统一入口：**摄入 / 搜索 / 知识库管理 / 设置**。

### 任务清单

| # | 任务 | 内容 | 📍节点 |
|:-:|------|------|:--:|
| D1 | 侧边栏 5→4 合并 | ui_shared.py 删 /manage 入口 → 内容并入 /hub 新增「浏览」标签 | 导航 |
| D2 | 仪表盘重设计 | /hub 概览标签：卡片式统计 + JSON 操作时间线 + 快速入口按钮 | 知识中枢 |
| D3 | 文档浏览器 | /hub 浏览标签：全文搜索 + 4 分面过滤 + 排序 + 批量删除 | 知识管理 |
| D4 | 文档详情页 | `/doc/{id}` 独立页面：28 字段完整展示 + 分块列表 + 来源追踪 + 关系链 | 知识管理 |
| D5 | 批量上传 | / 摄入页 multiple=True + 文件级进度追踪 + 结果汇总卡片 | 摄入 |
| D6 | 操作时间线后端 | JSON 格式 `local_data/activity_log.jsonl`，摄入/删除/审核/死信自动追加 | 知识中枢 |

### 设计决策

- ✅ 知识库管理 = 一个页面 4 个标签（概览/浏览/待审核/死信），不新建页面
- ✅ 文档详情 = `/doc/{id}` 独立子页面（不在侧边栏暴露，从浏览标签点入）
- ✅ 弹窗保留 → 快速确认；独立页面 → 深入研究
- ✅ 操作时间线用 JSON（JSON Lines），程序可精确查询，前端渲染为好看的时间线
- ✅ 竞品标杆：RAGFlow（卡片式仪表盘）+ LLM Wiki（操作日志）+ Dify（管道可视化）

---

### v1.0.0 🔍 无 UI 管线 + 一键部署（2026-06-24 代码完成 — 待最终验证）

### 目标

把 Citrinitas 从「开发者工具」变成「任何人双击就能用」的一站式知识引擎。

### 核心交付（A1-A5）

| # | 任务 | 内容 | 文件 |
|:-:|------|------|------|
| **A1** ✅ | `install.ps1` 一键部署 | 检测 Python 3.11+、创建 venv、安装依赖、初始化 Qdrant 目录、复制 .env.example→.env | 新建 |
| **A2** ✅ | 增强 `run.bat` | Qdrant/Ollama 健康检查 + 依赖完整性检测 + 守望守护进程启动 + 优雅关闭顺序 | run.bat |
| **A3** ✅ | YAML 配置化 | 管道参数从代码移到 `pipe_cfg.yaml`（11 项），`config/settings.py` 加载器，`.env` 覆盖 YAML，P1-3 验证/P2-3 边界文档/P2-6 变更检测 | 新建 + 4 模块改造 |
| **A4** ✅ | 守望文件夹 | `watch/` 目录自动监控摄入（watchdog），文件完整性检测，并发安全，死信队列 | watcher_v2.py |
| **A5** ✅ | OCR 接入管道 | 图片/扫描件→OCR 识字→正常走管道，PaddleOCR 预热，混合 PDF 支持 | kb_query.py + text_pipeline.py |

### 缺口清单（四轮审查合并，去重后 42 项）

> 2026-06-23 A2(链路追踪) + A3(防御纵深) + A4(交叉校验) + A5(集成/并发/恢复) 四轮审查完成。
> 全部纳入 v1.0.0 执行范围。P2 远期待办可延后到 v1.1.0。

#### 🔴 P0 — 阻断（13 项）

| # | 归属 | 缺口 | 审查轮 |
|---|:--:|------|:--:|
| P0-01 | A2 | **Qdrant 启动后无健康检查** — 只 `timeout /t 3`，可能没启动完就开 Web UI | A1 |
| P0-02 | A2 | **Ollama 完全无检查** — run.bat 不检查 Ollama 是否运行 | A1 |
| P0-03 | A4 | **无 staging 目录** — 文件处理中仍留在 watch/，失败后被重复捡起，死循环 | A3 |
| P0-04 | A4 | **ingest() 无顶层 try/except** — Python 异常会崩溃 watcher 线程，静默停止 | A4 |
| P0-05 | A4 | **孤儿 staging 恢复缺失** — 崩溃后 staging 文件永远无人处理 | A5 |
| P0-06 | A4 | **watcher 线程静默死亡** — daemon 崩溃无监控，UI 显示 enabled 实际已死 | A5 |
| P0-07 | A4 | **基础设施故障无降级** — Ollama/Qdrant 挂了 → 所有文件打入 DLQ，恢复后需手动移回 | A3 |
| P0-08 | A4 | **ingest() 无并发保护** — watcher + 手动上传同时调用 ingest()，嵌入超载 | A5 |
| P0-09 | A4 | **install.ps1 目录名旧设计** — `watch\processed` / `watch\failed`，新设计用 `watch_staging` 等 | A5 |
| P0-10 | A4 | **config/settings.py 零 watch 配置** — poll_interval / dlq_max 等无处可读 | A5 |
| P0-11 | A4 | **hub.py DLQ 只读 JSON 格式** — 守望 DLQ 存原始文件 + .meta.json，Hub 看不到 | A4 |
| P0-12 | A4 | **处理后原文件未定义** — 成功后留在 watch/ → 重启重复摄入 | A2 |
| P0-13 | A4 | **临时文件未过滤** — Office ~$xxx.docx / .part / .crdownload 被 watchdog 捡到 | A2 |

#### 🟡 P1 — 严重（19 项）

| # | 归属 | 缺口 | 审查轮 |
|---|:--:|------|:--:|
| P1-01 | A4 | **DLQ 磁盘无保护** — watch_dead_letter/ 可能无限膨胀 | A2 |
| P1-02 | A4 | **DLQ 同名文件覆盖** — 两次同名文件都失败，第二个覆盖第一个 | A2 |
| P1-03 | A4 | **OCR 就绪检查缺失** — 守望捡到图片时 PaddleOCR 可能还没加载模型 | A2 |
| P1-04 | A4 | **来源标记未区分** — metadata 缺少 ingestion_source: "watch" | A2 |
| P1-05 | A4 | **文件锁无重试** — Word 打开的文件复制到 watch/ 直接 PermissionError | A3 |
| P1-06 | A4 | **系统文件未过滤** — thumbs.db / desktop.ini 也会被捡到 | A3 |
| P1-07 | A4 | **多实例检测缺失** — 两个 run.bat 同时跑 → 两个 watcher 抢同一文件 | A3 |
| P1-08 | A4 | **磁盘满降级** — .meta.json 写入失败时静默，文件卡在 staging | A3 |
| P1-09 | A4 | **FLOWCHART C3 编码失败路径不可达** — latin-1 兜底让整条分支作废 | A4 |
| P1-10 | A4 | **run.bat 目录名不一致** — 第 162 行打印 watch\failed\，与设计不符 | A4 |
| P1-11 | A4 | **LLM API 未纳入健康检查** — classify_document() 依赖 DeepSeek，挂了全入 DLQ | A4 |
| P1-12 | A4 | **DLQ 操作按钮不兼容** — 手动修正/重新上传 只适配 JSON 格式 DLQ | A5 |
| P1-13 | A4 | **activity_log 缺少 watch 专属 action** — 无法区分手动失败 vs 守望失败 | A5 |
| P1-14 | A4 | **STATE dict 非线程安全** — watcher 线程写 STATE，NiceGUI 同时读 | A5 |
| P1-15 | A4 | **写入完成检测 2 秒不靠谱** — 大文件/网络盘不够，小文件浪费 | A5 |
| P1-16 | A4 | **无背压控制** — 一口气丢 50 个文件队列无限增长 | A5 |
| P1-17 | A4 | **watcher+手动 并发 Ollama 超载** — 同时嵌入两份数据 | A5 |
| P1-18 | A4 | **ingest_log 与 Qdrant 可能不一致** — _step_log_ingest 在 write_qdrant 之后 | A5 |
| P1-19 | A4 | **磁盘满 .meta.json 写入静默失败** — activity_log 吞异常 | A5 |

#### 🟢 P2 — 体验（10 项，可延至 v1.1.0）

| # | 归属 | 缺口 | 审查轮 |
|---|:--:|------|:--:|
| P2-01 | A4 | DLQ 按日期分子目录 | A2 |
| P2-02 | A4 | /hub 实时显示 DLQ 条目数量徽章 | A2 |
| P2-03 | A4 | 大文件上限保护（默认 50MB） | A1 |
| P2-04 | A4 | 处理超时保护（单文件 > 10 分钟入 DLQ） | A3 |
| P2-05 | A4 | 原文件时间戳保留到 metadata | A3 |
| P2-06 | A4 | DLQ 错误中文化（.meta.json 的 error 字段） | A3 |
| P2-07 | A4 | ingestion_source 字段标准化（↓ P1-04 强制执行后自然解决） | A4 |
| P2-08 | A4 | run.bat 步骤编号跳号修复（缺 [4/8]） | A4 |
| P2-09 | A4 | FLOWCHART 版本日期过旧（v3 2026-06-17 → v5 2026-06-23） | A4 |
| P2-10 | A4 | 可配置的文件扩展名白名单 | A2 |

> ⚠️ A5（OCR 接入管道）未纳入本轮审查，其缺口（P0-6/P1-1/P2-5）独立处理。

### 设计决策（2026-06-23 更新）

| 决策点 | 结论 |
|--------|------|
| 守望文件夹启动 | run.bat 自动启动守护进程，用户无感知 |
| 文件流目录 | watch/(投放) → staging/(处理中) → processed/(成功) / dead_letter/(失败) |
| 并发安全 | threading.Lock 保护 ingest() + 串行队列消费（P0-08 修复） |
| 文件完整性 | 每 500ms 轮询文件大小，连续 2 次不变 → 认为写入完成（P1-15 修复） |
| 基础设施降级 | Qdrant/Ollama 不通 → watcher 暂停处理，每 30s 重试，不通不入 DLQ（P0-07） |
| DLQ 格式 | 置信度 DLQ → JSON；守望 DLQ → 原始文件 + .meta.json（P0-11 Hub 统一展示） |
| DLQ 清理 | 自动：>30 天删除；手动：Hub UI 逐条操作（P1-01 磁盘保护 500MB 上限） |
| 孤儿恢复 | 启动时扫描 staging/ → 文件移回 watch/ 重新处理（P0-05） |
| watcher 线程监控 | 30s 心跳检测，死了自动告警 + activity_log（P0-06） |
| 优雅关闭顺序 | 守望守护进程 → Web UI → Qdrant → Ollama |
| 关闭序列 | Ctrl+C 触发，超时 10 秒后强杀 |
| 文档同步 | FLOWCHART.md 新增 F_WATCH + DL_WATCH 节点及连线（P2-09） |

### 验收标准

- [ ] `install.ps1` 双击后 5 分钟内完成全部安装 + 验证通过
- [ ] `run.bat` 双击后自动启动 Qdrant + Ollama（如有）+ Web UI + 守望守护进程
- [ ] 丢一个 .txt 到 `watch/`，30 秒内出现在知识库搜索结果里
- [ ] 丢一张扫描页到 `watch/`，自动 OCR → 入库 → 可搜索
- [ ] OCR 失败的文件出现在「死信队列」UI，不静默丢失
- [ ] 修改 `pipe_cfg.yaml` 后重启服务，参数生效
- [ ] 同时丢 5 个文件到 watch/，全部稳定入库，不丢数据

---




> 可追溯的设计决策记录，避免未来重蹈覆辙。

### v0.6.0 决策（2026-06-20 确认）

| 决策点 | 结论 |
|--------|------|
| 管道架构 | 三层并行：file + rule 独立并行 → LLM 仅兜底缺口字段 → 程序计算置信度 |
| LLM 角色 | 兜底而非主力——仅对 file/rule 未覆盖的字段推理，不再生成 confidence |
| 确定性 | temperature=0，保证同输入永远同输出 |
| 置信度计算 | 程序计算（Σ 字段权重 × 来源置信度），非 LLM 自报 |
| 来源优先级 | file(1.0) > user(1.0) > rule(0.85) > llm(0.60) > default(0.0) |
| 置信度路由 | ≥0.75 直接入库 / 0.40–0.75 待审核 / <0.40 死信队列 |
| domain 规则 | 多选——收集所有命中值去重，非首次命中即返回 |
| auto_classify 兼容 | 降级为薄包装调用 classify_document()，旧调用方零改动 |
| I016-I019 处理 | 不修 Bug，直接替换代码——在重构中自然消失 |

### v0.5.0 决策（2026-06-20 确认）

| 决策点 | 结论 |
|--------|------|
| L2 管道 | 从 `metadata` 字段（title/author/keywords/source）提取文本，使用 `keyword_domain_map` 推断 UDC 主类 |
| 模糊映射 | `normalize_facet_values()` 使用 `FUZZY_FACET_MAPPING` 表（精确/大小写不敏感/部分匹配） |
| 异常处理 | 所有 `except:pass` 改为 `except Exception as e:` 并记录 `logger.warning` |
| content_hash | 使用 SHA256 前 32 位十六进制字符（原 16 位，碰撞风险高） |

### v0.4.5 决策（2026-06-15 确认）

| 决策点 | 结论 |
|--------|------|
| 元数据优先级 | 文件自带 > LLM 推断 > 用户手动 |
| 置信度路由 | < 0.5 审核队列；0.5–0.8 入库 + needs_review；≥ 0.8 直接入库 |
| 置信度计算 | 启发式 (JSON完整性 0.25 + 字段合法性 0.35 + 信息丰度 0.25 + 一致性 0.15) |
| 审核队列入口 | 知识中枢页面 |
| 文件大小上限 | 50MB，超限提示但允许继续 |
| 编码检测 | chardet → UTF-8 → GBK → latin-1 兜底链 |
| PDF 双路径 | pypdf 提取文字层 → 不足时 PaddleOCR 逐页 |

### v0.4.5 不做

- 批量文件摄入（v0.9.0 批量摄入 UI）
- EPUB/PDF 加密文件解密
- .doc（旧版 Word）/ .xlsx Excel 处理
- 守望文件夹触发策略
- 推送通知层（Server酱/邮件）

### v0.7.0 决策（2026-06-16 确认，原 v0.6.0）

| 决策点 | 结论 |
|--------|------|
| 图谱后端 | NetworkX（零依赖），GEXF 序列化持久化 |
| 数据源 | 零 LLM 建图：Qdrant relations → NetworkX |
| 数据兜底 | relations 为空时，向量 Top-K 相似度生成 `similar` 边 |
| 可视化 | Plotly 力导向图，NiceGUI `ui.plotly` 渲染 |
| 嵌入位置 | 知识中枢页面 |
| 同步策略 | 惰性同步：dirty 标记 → 打开图谱页按需重建 |
| 节点着色 | domain 颜色 + epistemic_status 边框线型 |
| 边着色 | relation_type 颜色区分 |

---

## 四、竞品学习路线（2026-06-16 研究产出）

> 详细分析见 `docs/competitor-research-2026-06-16.md` 和 `docs/knowledge-graph-research-2026-06-16.md`

### 三条启发

| # | 启发方向 | 学自 | 核心想法 | Citrinitas 切入点 | 落地版本 |
|---|------|------|---------|-----------------|:--:|
| 1 | 知识关系网 | RAGFlow | NetworkX 内存图，实体+关系提取+图遍历 | 从已有关系字段建图（零 LLM），分面分类天然着色 | v1.1.0 |
| 2 | QA 自动生成 | FastGPT | 文档→LLM 拆成问答对→向量化 | 嵌入摄入管线，作为可选开关 | v1.1.0 |
| 3 | 管线配置化 | Dify | 摄入步骤 YAML 声明 | 步骤可配置/可跳过/可调参 | v1.0.0 |

### 学习优先级

| 优先级 | 内容 | 难度 | 落地 |
|:--:|------|:--:|:--:|
| 1 | 知识关系网：Schema 定稿 + NetworkX + 可视化 | 🟡 中 | v1.1.0 |
| 2 | API 熔断机制 | 🟢 低 | v0.8.0 |
| 3 | QA 自动生成摄入模式 | 🟢 低 | v1.1.0 |
| 4 | LLM 关系发现（按需触发） | 🟡 中 | v1.1.0 |
| 5 | 管线 YAML 配置化 | 🟢 低 | v1.0.0 |
| 6 | 双队列异步摄入 | 🟡 中 | v0.9.0 |
| 7 | 插件协议（MCP/OpenAPI） | 🔴 高 | v1.0.0 |
| 8 | 工作流可视化编排 | 🔴 高 | v1.0.0 |
| 9 | 桌面端一键打包 | 🟡 中 | v1.0.0 |

### 不做什么

- ❌ 照搬 GraphRAG 社区发现+摘要（个人 KB 不需要，LLM 成本高）
- ❌ 引入 Neo4j（NetworkX 零依赖足够）
- ❌ 从零实体提取（分面分类已定义知识维度）
- ❌ 完整的可视化工作流编辑器（YAML 配置足够）

---

## 五、架构原则（不可变）

1. **非必要不用大模型** — 尽可能由固定程序完成
2. **核心逻辑与 UI 完全解耦** — 面向未来多端交互
3. **输出统一 JSON 结构化数据** — search/ingest/answer 返回值均为 dict
4. **配置用环境变量** — KB_LLM_BASE_URL/KEY/MODEL, KB_EMBED_MODEL 等
5. **本地优先** — 向量库本地、嵌入模型本地，仅 LLM 合成需联网

---

## 六、远期待办

> 不在当前版本计划中，作为未来参考。

### 搜索词 → 分面自动推断

LLM 解析搜索词自动生成分面过滤条件（如 "齿轮国标" → domain:["6"] + content_type:"standard"）。

### 个人内容分类深化

当前 content_type 有 `personal_note` 兜底，但个人生活文件分类颗粒度不足：
- `content_type` 可扩展子类：`medical_record` / `financial_doc` / `diary`
- 配套隐私/访问权限机制（`access_level` 落地实现）
- domain 推断规则优化：`personal_note` 类型的 domain 默认 → 哲学/心理学(1)

### FPF 信任聚合（WLNK）→ 并入 Albedo

arxiv 2601.21116 WLNK 原则不放在 Citrinitas，作为 Albedo（炼真）的核心功能。

### project_source 升级路径

当前为普通自由文本字段。未来可升级为分面（Payload Index），需配合 LLM 项目推断。

### 关键词→UDC 映射增强

当前 L3 关键词→UDC 映射表仅 52 条，待积累后增强为规则引擎。

### normalize_facet_values() 独立化

当前 auto_classify() 内联校验。未来独立为函数，统一入口供所有摄入路径调用。

### 旧域数据迁移

执行 `DOMAIN_MIGRATION_MAP`，为历史数据补充 temporal_nature/epistemic_status 默认值。

### 🔬 待深入研究（2026-06-18 标记）

> 以下问题已在 v0.4.3 做了最小可行实现，未来需做竞品调研/论文检索/技术验证后升级。

| # | 问题 | 状态 | 复杂度 | 未来研究方向 |
|---|------|:--:|:--:|------|
| R1 | **切块 overlap 机制** | ✅ v0.4.3 尾部→头部拼接 | 🟡 中 | 句边界语义感知 vs 固定字符窗口；各竞品（RAGFlow/Dify/LlamaIndex）的 overlap 策略对比 |
| R2 | **图片引用多格式提取** | ✅ v0.4.3 Markdown + HTML + 自有格式 | 🟡 中 | OCR 内嵌图的统一提取管道；图片与文本 chunk 的关联保持；Base64 内联图片支持 |

---

## 七、管理文件体系

| 文件 | 用途 |
|------|------|
| `PROJECT_PLAN.md` | 功能路线图 + 设计决策（本文件） |
| `CHANGELOG.md` | 版本变更日志 |
| `ISSUES.md` | Bug 跟踪 |
| `README.md` | 项目门面 |
| `docs/schema.md` | 字段设计文档 |
| `WEB_UI_PLAN.md` | v0.2 Web UI 任务清单（已归档） |
| `DEVELOPMENT_HISTORY.md` | 开发过程记录 |
| `COMPARISON.md` | 同类工具对比 |

---

## 八、代码质量重构路线（2026-06-23 修订）

> **本节的重构任务已纳入版本路线图（见第一节）**，此处仅记录详细分工与验收标准。
> 重构原则：**验收通过后再动，渐进式拆分，不一次性大改**。

### 重构任务与版本对应关系

| 版本 | 重构内容 | 对应文件 |
|------|---------|---------|
| v0.6.1 | main.py 页面层拆分 | main.py → pages/*.py |
| v0.7.0 | kb_query.py 拆分 + 统一返回值格式 | kb_query.py → 5 个独立模块 |
| v0.8.0 | 搜索优化（search_engine.py 重排序 + 混合检索）| search_engine.py + 重排序模块 |
| v0.9.0 | 审核队列 UI（hub/manage 优化）| doc_manager.py + hub/manage 页面 |
| v1.0.0 | 代码重构收尾 + YAML 配置化 + 桌面打包 | 规范统一 + config/settings.py + PyInstaller |

### 问题定位

| # | 问题 | 位置 | 严重程度 | 状态 |
|---|---|---|---|---|
| 1 | `kb_query.py` 五层职责混在一起 | `kb_query.py` | 🔴 P0 | ✅ 已修复 (A1-A5 拆分) |
| 2 | `page_ingest()` 366 行，UI+逻辑不分 | `main.py:294` | 🔴 P0 | ✅ 已修复 (v0.6.1 页面拆分) |
| 3 | `ingest()` 302 行，做了分块+嵌入+存储三件事 | `kb_query.py` | 🟡 P1 | ✅ 已修复 (T1: → ingest_pipeline.py) |
| 4 | `classify_document()` 159 行，三层管道挤在一起 | `kb_query.py` | 🟡 P1 | ✅ 已修复 (A5+T2: 拆分+验证抽离) |
| 5 | 返回值格式不统一 | 全局 | 🟡 P1 | ✅ 已修复 (T3: 统一 `{"ok": bool, ...}`) |
| 6 | `panel_funcs.py` 编辑对话框 99 行，可拆分 | `panel_funcs.py` | 🟢 P2 | ✅ 已修复 (T4: _build_edit_widget) |
| 7 | `config/classifications.py` 720 行，主要是数据 | `config/` | 🟢 P2 | ✅ 已修复 (T5: → config/normalize.py) |

### 三步重构路线

#### 第一步：`main.py` 页面层拆分（v0.6.1，低风险）

把每个页面拆成独立模块，不影响核心逻辑：

```
main.py (1213行) → 精简为路由+侧栏 (~300行)
pages/
  ├── ingest.py    (page_ingest + 回调 + panel_funcs 引用)
  ├── search.py    (page_search + 回调)
  ├── hub.py       (page_hub)
  ├── manage.py    (page_manage)
  └── config.py   (page_config)
```

**验收标准**：拆分后功能不变，每个页面模块可独立编辑。

#### 第二步：`kb_query.py` 渐进式拆分（v0.7.0，✅ 已完成）

不一次性大拆，随版本推进迁移：

```
kb_query.py (3958行) → 拆为：
├── qdrant_client.py    Qdrant 连接/集合/CRUD 操作
├── text_pipeline.py     OCR/提取/分块/嵌入
├── classify_pipeline.py 分类三层管道/规则引擎/置信度
├── search_engine.py    搜索/问答/HTML 报告渲染
├── doc_manager.py      文档 CRUD
└── kb_query.py        统一入口，重新导出各模块
```

**迁移顺序**（按依赖从低到高）：
1. `doc_manager.py`（无内部依赖，先拆）
2. `qdrant_client.py`（被 doc_manager 和 ingest 依赖）
3. `text_pipeline.py`（被 ingest 依赖）
4. `search_engine.py`（被页面搜索依赖）
5. `classify_pipeline.py`（最后拆，依赖最多）

**每步验收**：拆完一个模块，跑通摄入+搜索完整流程。

#### 第三步：代码规范统一（随版本随修，低风险）

随 Bug 修复和新功能开发逐步统一：

- **返回值统一**：所有函数返回 `{"ok": bool, "data"?: ..., "error"?: str}`
- **错误处理统一**：禁止 `except: pass`，必须 `logger.warning(...)` 或 `raise`
- **配置集中管理**：`.env` 或 `config/settings.py`，不再用全局变量
- **超长函数拆分**：>80 行的函数必须拆分子函数，每个子函数单一职责

#### 第四步：搜索优化（v0.8.0，中风险）

搜索相关函数增加重排序 + 混合检索逻辑：

```
search_engine.py（增强模块）
├── search()              向量检索 + BM25 关键词 + 重排序
├── answer()              LLM 合成 + 引用编号
├── get_facet_stats()     分面统计
└── _render_report_html() HTML 报告渲染
```

**新增**：
- `reranker.py`：重排序模块（`bge-reranker-v2-m3` 本地运行）
- 混合检索：向量 Top-20 + BM25 Top-20 → 合并去重 → 重排序 → 返回 Top-K

**验收标准**：搜索结果相关性提升（人工评估），重排序耗时 < 500ms。

#### 第五步：审核队列 UI（v0.9.0，低风险）

`hub()` + `manage()` 页面新增审核队列入口：

- hub 页面：新增「📋 待审核」和「🗑️ 死信队列」标签页
- manage 页面：文档列表显示置信度进度条
- 审核操作：通过并入库 / 编辑后入库 / 丢弃

**验收标准**：审核队列 UI 可操作，置信度路由正确（≥0.75/0.40-0.75/<0.40）。

### 不做的事

- ❌ 一次性大拆 `kb_query.py`（风险太高，容易引入新 bug）
- ❌ 重写测试框架（当前阶段先手动验收，后续补单元测试）
- ❌ 引入类型检查（mypy/pyright）——有成本，收益低

### 当前版本（v0.7.1）验收通过，进入 v0.8.0 规划

---

## 九、v0.8.0 规划（搜索优化 + 审核队列 + 性能优化）

> v0.8.0 是"墙体"层——在框架完成后，提升搜索质量和入库质量控制。

### 目标

1. **搜索优化**：混合检索（向量 + BM25 关键词）+ 重排序（使用嵌入模型计算相似度重新排序）
2. **审核队列**：置信度路由落地（待审核 / 死信队列 UI）

### 任务清单（方案 A — 推荐）

| 编号 | 任务 | 内容 | 优先级 | 状态 | 预计工作量 |
|:----:|------|------|:--:|:--:|:--:|
| **S1.1** | 混合查询 | 使用 Qdrant 原生 query API（prefetch + RRF fusion） | P0 MVP | ✅ 已完成（2026-06-23） | - |
| **S1.2** | 重新摄入数据 | 删除旧集合，重建（含量化+稀疏向量），摄入测试数据验证 | P0 MVP | ✅ 已完成（2026-06-23） | - |
| **S1.3** | Grouping API | 按 `doc_id` 分组去重，每文档只保留最佳 chunk | P0 高收益 | ✅ 已完成（2026-06-23） | - |
| **S1.4** | 量化（Quantization） | 启用 int8 标量量化，降低内存占用 75% | P0 高收益 | ✅ 已完成（2026-06-23） | - |
| **S1.5** | ACORN 过滤 | 提升严格过滤条件下的召回率 | P1 | ✅ 已完成（2026-06-23） | - |
| **S2** | 重排序 | Top-K 结果用嵌入模型重新打分排序（使用 qwen3-embedding:4b） | P0 MVP | ✅ 已完成（2026-06-23） | - |
| **S3** | 重排序模型可配置 | 引擎配置页面可选重排序模型（开关/模型/Top-N） | P2 锦上添花 | ✅ 已完成（2026-06-23） | - |
| **R1** | 审核队列后端 | 阈值可配置（`.env`）+ 三档路由（≥高阈值直接入库 / 中间待审核 / <低阈值死信） | P0 MVP | ✅ 已完成（2026-06-23） | - |
| **R2** | 待审核队列 UI | hub 页新增「📋 待审核」标签页，显示置信度进度条，支持通过/丢弃 | P0 MVP | ✅ 已完成（2026-06-23） | - |
| **R3** | 死信队列 UI | hub 页新增「🗑️ 死信队列」标签页，支持手动修正/重新上传/永久删除 | P0 MVP | ✅ 已完成（2026-06-23） | - |

**总工作量**：约 25.5h  
**预计完成时间**：4-5 天（按 6h/天计算）

### S1 详细方案（混合检索）

**实现方式**：Qdrant Query API (`/points/query`) + prefetch + RRF fusion

**请求结构**：
```json
POST /collections/{collection}/points/query
{
    "prefetch": [
        {"query": dense_vec, "limit": top_k * 2},
        {"query": sparse_vec, "using": "bm25", "limit": top_k * 2}
    ],
    "query": {"fusion": "rrf"},
    "limit": top_k,
    "filter": {...}
}
```

**降级策略**：稀疏向量生成失败 → 自动降级为纯稠密查询（单 prefetch）

**实现方式**（Qdrant 8.3+ 支持 `hybrid` 检索）：
```python
# 方案 A：Qdrant 原生 hybrid（推荐）
search_body = {
    "vector": query_vec,
    "parse_vector": {"text": query_tokens},  # BM25
    "limit": top_k,
    ...
}

# 方案 B：手动合并（兼容旧版 Qdrant）
vec_results = vector_search(query_vec, top_k=20)
bm25_results = bm25_search(query, top_k=20)
merged = merge_and_dedup(vec_results, bm25_results)
reranked = rerank(query, merged[:20])
return reranked[:top_k]
```

**验收标准**：搜索结果相关性提升（人工评估）

### S2 详细方案（重排序）

**重排序模型**：`bge-reranker-v2-m3`（北京智源，0.5B 参数，中英双语）

**调用方式**（Ollama 本地运行）：
```python
import ollama

query = "齿轮模数怎么选"
docs = [chunk["text"] for chunk in top20_chunks]

# Ollama embed API（bge-reranker 返回 embedding）
response = ollama.embed(
    model="dengcao/bge-reranker-v2-m3",
    input=[query] + docs
)
# response["embeddings"][0] = query 向量
# response["embeddings"][1:] = docs 向量
# 计算余弦相似度，重新排序
```

**集成位置**：`search()` 函数，向量/BM25 检索之后，返回之前

**验收标准**：
- `ollama list` 显示 `dengcao/bge-reranker-v2-m3`
- 搜索结果排序质量提升（人工评估）
- 重排序耗时 < 500ms（RTX 3080）

### S3 详细方案（重排序模型可配置）

**修改文件**：`pages/config.py`（引擎配置页面）

**新增设置项**：
- 重排序模型（下拉选择）：`bge-reranker-v2-m3` / `bge-reranker-large` / `none`（关闭）
- 重排序 Top-N（数字输入）：默认 20
- 重排序启用开关（布尔）：默认开启

**存储方式**：`.env` 或 `config/settings.py`

### R1 详细方案（审核队列后端）

**当前状态**：`classify_document()` 返回 `overall_confidence`，但没有路由逻辑

**改造后**：
```python
# 置信度路由（三档）
confidence = result["overall_confidence"]

if confidence >= 0.75:
    # 直接入库
    await ingest(payloads, collection)
    return {"route": "auto_ingested", ...}

elif confidence >= 0.40:
    # 待审核队列
    await save_to_review_queue(payloads, confidence)
    return {"route": "needs_review", ...}

else:
    # 死信队列
    await save_to_dead_letter_queue(payloads, confidence)
    return {"route": "dead_letter", ...}
```

**存储方式**：
- 待审核队列：`review_queue.jsonl`（追加写入）
- 死信队列：`dead_letter.jsonl`（追加写入）

### R2 详细方案（待审核队列 UI）

**修改文件**：`pages/hub.py`（知识中枢页面）

**新增标签页**：「📋 待审核」（在「📊 集合概览」旁边）

**UI 内容**：
- 列表显示待审核条目（标题、来源、置信度、时间）
- 每条显示：预览文本（前 200 字）、分类标签、置信度进度条
- 操作按钮：「✅ 通过并入库」、「✏️ 编辑后入库」、「❌ 丢弃」

### R3 详细方案（死信队列 UI）

**修改文件**：`pages/hub.py`（知识中枢页面）

**新增标签页**：「🗑️ 死信队列」（在「📋 待审核」旁边）

**UI 内容**：
- 列表显示死信条目（标题、来源、置信度、时间、失败原因）
- 每条显示：原始文本、错误信息、分类标签
- 操作按钮：「✏️ 编辑后重新入库」、「❌ 永久删除」

### 验收标准

- [ ] S1: 混合检索合并结果正确，无重复
- [ ] S2: 重排序后 Top-5 相关性提升（人工评估）
- [ ] S3: 配置页面可切换重排序模型，立即生效.
- [ ] R1: 置信度三档路由正确（≥0.75/0.40–0.75/<0.40）
- [ ] R2: 待审核队列 UI 显示正确，操作按钮有效
- [ ] R3: 死信队列 UI 显示正确，操作按钮有效

---
