# Citrinitas — 项目主计划

> 功能路线图 + 设计决策。版本变更记录见 `CHANGELOG.md`，Bug 跟踪用 GitHub Issues。
> 已完成版本的详细记录见 `CHANGELOG.md`，本文件只保留当前状态 + 未来规划。

最后更新: 2026-07-04

---

## 当前状态

- 当前版本：**v1.1.0 🔮**（架构重构 + 错误日志规范 — 进行中）
- 活跃 Bug：**0**
- 下个版本：**v1.2.0** — 闪念笔记
- Git 状态：main 分支

---

## 版本路线图

> 按「地基 → 框架 → 墙体 → 装修 → 交付」逐层递进。✅=已完成，🔮=待开发。

| 版本 | 状态 | 层级 | 核心交付 |
|------|:----:|:--:|---------|
| v0.1.0~v0.5.1 | ✅ | 地基+框架 | CLI搜索 + Web UI + 分面分类 v5.0 + 智能摄入 + 内存优化 |
| v0.6.0 | ✅ | 框架 | 卡片式结果面板 + 三层并行管道 + 来源徽章 |
| v0.7.0 | ✅ | 框架 | 摄入执行重构 + 批量摄入 + Nigredo 钩子接口 |
| v0.8.0 | ✅ | 墙体 | 混合检索 + 重排序 + 置信度路由 UI |
| v0.9.0 | ✅ | 装修 | 知识库综合管理（侧边栏5→4 + 仪表盘 + 浏览 + 批量摄入） |
| v1.0.0 | ✅ | 交付 | 无 UI 管线 + YAML 配置化 + 桌面一键打包 |
| v1.0.1 | ✅ | 交付 | 死代码清理 + 大文件拆分 + run.bat 修复 |
| **v1.1.0** | 🔮 | 交付 | **架构重构 + 错误日志规范** — Service 层解耦 UI/核心 + 统一日志 + 错误码体系 |
| v1.2.0 | 🔮 | 交付 | 闪念笔记（fleeting_note 类型 + 快速捕获 + 跳过 LLM 分类）+ 书库存储层（保留书本源文件；录入前归一化为统一格式；每块带章节/段落位置指针；书目录记书名/作者/系列/卷号/封面；搜索按源文件聚成「一本书/一套书」；题材用 tags 非分面） |
| v1.2.x | 🔮 | 交付 | 大文件断点续存（文字小说 EPUB/TXT 优先；源文件持久化 + 增量写归一化 + 记最后完成块，关机可续；与书库位置指针共用） |
| v1.3.0 | 🔮 | 交付 | 项目间通信 — REST API（ingest/search 端点）+ OpusMagnum 对接 |
| v1.4.0 | 🔮 | 交付 | 知识关系网 — NetworkX 图谱可视化 + QA 自动生成 + LLM 关系发现 |
| v1.5.0 | 🔮 | 交付 | 录入预处理 — 自动纠错 + 统一语言翻译 + 去除广告/抓取残留/无关内容；网页 URL 直接摄入 |
| v1.6.0 | 🔮 | 交付 | LLM 智能选择 — 用户可选云LLM / 本地小模型 / 机械程序 |
| v1.7.0 | 🔮 | 交付 | 性能优化 — 后台服务模式 + 内存优化 + 嵌入批处理 + 启动并行化 |
| v1.8.0 | 🔮 | 交付 | 知识保鲜 — 定期检查过期内容 + 提醒更新 + 批量重摄入 |
| v1.9.0 | 🔮 | 交付 | UI 美化 — 视觉升级 + 卡片式界面 + 暗色主题 + 响应式布局 |
| v1.10.0 | 🔮 | 交付 | Git 说明页面 — 版本历史 + 变更记录 + 开发者入口 |

---

## 下一版本：v1.1.0 架构重构 + 错误日志规范

**状态**：进行中（架构重构已完成，错误处理进行中）

**架构重构（已完成）**：
- ✅ 创建 `services/ingest_service.py`，从 `kb_query.py` 拆出摄入逻辑
- ✅ 把 `route_by_confidence` 移到 `classify_pipeline.py`
- ✅ 删除 `kb_query.py` 里的 `get_facet_stats` 重复定义
- ✅ 重写 `kb_query.py` 为 CLI facade
- ✅ 更新 UI 层调用方（`pages/ingest.py`, `watcher/processor.py`）
- 📁 ADR: `docs/adr/ADR-001-introduce-service-layer.md`

**错误日志规范（进行中）**：
- 问题：6 个模块各自 logging，无统一配置；无错误码；异常被吞（多处 `except: pass`）；watcher 日志黑盒
- 方案：三层结构 — 统一配置(logging.yaml) + 结构化错误格式(error_code/message/context/traceback) + 集中查看 UI(知识中枢新标签)
- 错误码分段：E001-E099 摄入 / E100-E199 搜索 / E200-E299 守望 / E300-E399 LLM / E400-E499 OCR / E900-E999 基础设施
- 实施优先级：P0 统一 logging.basicConfig + 消灭 except:pass → P1 错误码体系 + UI → P2 日志轮转

**待确认**：① 是否接入外部告警（Server酱/邮件）？ ② 日志放 `local_data/logs/` 还是项目根目录？

---

## 架构原则（不可变）

1. **非必要不用大模型** — 尽可能由固定程序完成
2. **核心逻辑与 UI 完全解耦** — 面向未来多端交互
3. **输出统一 JSON 结构化数据** — search/ingest/answer 返回值均为 dict
4. **配置用环境变量** — KB_LLM_BASE_URL/KEY/MODEL, KB_EMBED_MODEL 等
5. **本地优先** — 向量库本地、嵌入模型本地，仅 LLM 合成需联网

---

## 竞品学习要点

> 详细分析见 `docs/competitor-research-2026-06-16.md` 和 `docs/knowledge-graph-research-2026-06-16.md`

| 启发 | 学自 | 落地版本 |
|------|------|:--:|
| 知识关系网（NetworkX 内存图，零 LLM 建图） | RAGFlow | v1.4.0 |
| QA 自动生成（文档→问答对→向量化） | FastGPT | v1.4.0 |
| 管线 YAML 配置化 | Dify | ✅ v1.0.0 |

**不做**：GraphRAG 社区发现（成本高） / Neo4j（NetworkX 够用） / 从零实体提取 / 可视化工作流编辑器

---

## 远期待办

> 不在当前版本计划中，作为未来参考。

- **搜索词→分面自动推断** — LLM 解析搜索词自动生成分面过滤（如 "齿轮国标" → domain:["6"] + content_type:"standard"）
- **个人内容分类深化** — content_type 扩展子类（medical_record / financial_doc / diary）+ 隐私权限机制
- **FPF 信任聚合（WLNK）** — 不放 Citrinitas，作为 Albedo 核心功能
- **project_source 升级** — 从普通字段升级为分面（Payload Index）
- **关键词→UDC 映射增强** — 当前仅 52 条，待积累后增强为规则引擎
- **normalize_facet_values() 独立化** — 当前内联校验，未来独立为统一入口函数
- **旧域数据迁移** — 执行 DOMAIN_MIGRATION_MAP，补充 temporal_nature/epistemic_status 默认值

---

## 代码质量待办

> 已完成的重构见 CHANGELOG.md。以下为尚未完成的项。

| # | 问题 | 位置 | 严重度 | 状态 |
|---|------|------|--------|------|
| 11 | `watcher.py` 单文件 1834 行，职责过多 | `watcher.py` | 🔴 P0 | 📋 待拆分 |
| 12 | `pages/hub.py` 单文件 1418 行，多 Tab 混在一起 | `pages/hub.py` | 🔴 P0 | 📋 待拆分 |

**拆分方案**（v1.0.1 已部分完成，剩余）：

```
watcher.py (1834行) → watcher/ 包
├── __init__.py        re-export start/stop/retry
├── listener.py        文件系统监听（watchdog）
├── dedup.py          内容去重（content_hash 比较）
├── dispatcher.py      事件分发（触发摄入管道）
└── state.py           监听状态管理

pages/hub.py (1418行) → pages/hub/ 包
├── __init__.py        re-export page_hub + page_doc_detail
├── overview.py        概览标签
├── browse.py         浏览标签
├── review.py         待审核标签
├── dlq.py            死信队列标签
└── detail.py         /doc/{id} 详情页
```

**拆分原则**：每步拆一个模块，拆完立即验证功能不变；`__init__.py` re-export，调用方零改动；单文件 ≤ 400行。

---

## 管理文件体系

| 文件 | 用途 |
|------|------|
| `BLUEPRINT.md` | 项目宪法（愿景/原则/重心/边界/验收） |
| `PROJECT_PLAN.md` | 功能路线图 + 设计决策（本文件） |
| `CHANGELOG.md` | 版本变更日志（含已完成版本详细记录） |
| `FLOWCHART.md` | 流程框图 |
| `README.md` | 项目门面 |
| `docs/schema.md` | 字段设计文档 |
