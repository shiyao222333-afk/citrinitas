# Citrinitas — 项目主计划

> 本文档管理功能路线图和设计决策。版本变更记录见 `CHANGELOG.md`，Bug 跟踪改用 GitHub Issues。

最后更新: 2026-06-21 (v0.6.1 代码质量重构 I)

---

## 当前状态

- 当前版本：**v0.6.1 ✅**（代码质量重构 I — main.py 页面拆分）
- 下一个版本：**v0.7.0 🔮**（摄入执行重构 + kb_query.py 拆分）
- 活跃 Bug：**0**
- Git 状态：main 分支，已推送 GitHub

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
| v0.4.3 | ✅ | 框架 | 摄入管线修复 | 5 项 PATCH |
| v0.4.4 | ✅ | 框架 | 文档管理 + XSS 修复 | 文档管理页面 `/manage` + XSS 漏洞修复 |
| v0.4.5 | ✅ | 框架 | P1 问题修复 | 17 项 P1 修复 |
| v0.4.9 | ✅ | 框架 | P1 剩余问题修复 | D1+U7/S1/F4 修复 |
| v0.5.0 | ✅ | 框架 | L2 管道 | auto_classify 增强 + normalize_facet_values |
| v0.5.1 | ✅ | 框架 | 内存优化 | get_facet_stats 修复 |
| v0.6.0 | ✅ | 框架 | 卡片式结果面板 | 三层管道 + 配置驱动 UI + 来源徽章 |
| v0.6.1 | ✅ | 框架 | 代码质量重构 I | main.py 页面拆分（1213行→348行） |
| v0.7.0 | 🔮 | 框架 | 摄入执行重构 | 阶段三 + kb_query.py 拆分 + 统一返回值格式 |
| v0.8.0 | 🔮 | 墙体 | 搜索重构 + 知识关系网 | 搜索流程重构 + NetworkX + Plotly |
| v0.9.0 | 🔮 | 装修 | 知识库管理重构 + 审核队列 | 阶段四 + hub/manage 优化 |
| v1.0.0 | 🔮 | 交付 | 生产就绪 | 阶段五 + 代码重构收尾 + YAML 配置化 |
| v1.1.0 | 🔮 | 交付 | 检索增强 | QA 自动生成 + 图谱联动 |
| v1.2.0 | 🔮 | 交付 | 移动端 | 微信 Bot + 移动端适配 |

---

## 二、当前版本：v0.6.0 ✅ 已完成（2026-06-21 验收通过）

### 目标

重构元数据标注管道：从单步 LLM 分类升级为三层并行管道（文件元数据 + 规则引擎并行 → LLM 兜底缺口 → 程序计算置信度），实现可复现的标签生成。同步完成结果面板 UI 重构（卡片式 + 来源徽章 + 高级选项折叠）。

### 摄入管道五阶段路线图

> 摄入管道按五个阶段递进开发，每个阶段独立验收。

| 阶段 | 名称 | 状态 | 版本 | 核心交付 |
|:----:|------|:----:|:----:|---------|
| 一 | 内容准备 | ✅ 完成 | v0.4.0–v0.5.1 | 文件上传 / OCR / 手动输入 + 基础 auto_classify + 入库检索 |
| 二 | 元数据标注 | ✅ 已完成 | v0.6.0 | 三层并行管道 + 规则引擎 + 来源徽章 + 置信度路由 |
| 三 | 摄入执行重构 | 📋 待开始 | v0.7.0 | ingest() 管道化（步骤可配置/可跳过）+ 批量摄入 |
| 四 | 审核队列 | 📋 待开始 | v0.9.0 | 置信度路由落地（待审/死信队列 UI）+ 知识中枢审核入口 |
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

## 三、设计决策

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

- 批量文件摄入（v0.8.0 守望文件夹）
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
| 1 | 知识关系网 | RAGFlow | NetworkX 内存图，实体+关系提取+图遍历 | 从已有关系字段建图（零 LLM），分面分类天然着色 | v0.6.0 |
| 2 | QA 自动生成 | FastGPT | 文档→LLM 拆成问答对→向量化 | 嵌入摄入管线，作为可选开关 | v0.7.0 |
| 3 | 管线配置化 | Dify | 摄入步骤 YAML 声明 | 步骤可配置/可跳过/可调参 | v0.8.0 |

### 学习优先级

| 优先级 | 内容 | 难度 | 落地 |
|:--:|------|:--:|:--:|
| 1 | 知识关系网：Schema 定稿 + NetworkX + 可视化 | 🟡 中 | v0.6.0 |
| 2 | API 熔断机制 | 🟢 低 | v0.6.0 |
| 3 | QA 自动生成摄入模式 | 🟢 低 | v0.7.0 |
| 4 | LLM 关系发现（按需触发） | 🟡 中 | v0.7.0 |
| 5 | 管线 YAML 配置化 | 🟢 低 | v0.8.0 |
| 6 | 双队列异步摄入 | 🟡 中 | v0.8.0 |
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

## 八、代码质量重构路线（2026-06-21 规划）

> **本节的重构任务已纳入版本路线图（见第一节）**，此处仅记录详细分工与验收标准。
> 重构原则：**验收通过后再动，渐进式拆分，不一次性大改**。

### 重构任务与版本对应关系

| 版本 | 重构内容 | 对应文件 |
|------|---------|---------|
| v0.6.1 | main.py 页面层拆分 | main.py → pages/*.py |
| v0.7.0 | kb_query.py 拆分 + 统一返回值格式 | kb_query.py → 5 个独立模块 |
| v0.8.0 | 搜索流程重构（search_engine.py 独立）| search_engine.py + 知识关系网 |
| v0.9.0 | 知识库管理重构（hub/manage 优化）| doc_manager.py + hub/manage 页面 |
| v1.0.0 | 代码重构收尾 + YAML 配置化 | 规范统一 + config/settings.py |

### 问题定位

| # | 问题 | 位置 | 严重程度 |
|---|---|---|---|
| 1 | `kb_query.py` 五层职责混在一起 | `kb_query.py` | 🔴 P0 |
| 2 | `page_ingest()` 366 行，UI+逻辑不分 | `main.py:294` | 🔴 P0 |
| 3 | `ingest()` 302 行，做了分块+嵌入+存储三件事 | `kb_query.py` | 🟡 P1 |
| 4 | `classify_document()` 159 行，三层管道挤在一起 | `kb_query.py` | 🟡 P1 |
| 5 | 返回值格式不统一 | 全局 | 🟡 P1 |
| 6 | `panel_funcs.py` 编辑对话框 99 行，可拆分 | `panel_funcs.py` | 🟢 P2 |
| 7 | `config/classifications.py` 720 行，主要是数据 | `config/` | 🟢 P2 |

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

#### 第二步：`kb_query.py` 渐进式拆分（v0.7.0，中风险）

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

#### 第四步：搜索流程重构（v0.8.0，中风险）

搜索相关函数从 `kb_query.py` 拆出为独立模块，与知识关系网同步开发：

```
kb_query.py (搜索相关函数) → search_engine.py 独立模块
├── search()             向量检索 + 分面过滤
├── answer()             LLM 合成 + 引用编号
├── _render_report_html() HTML 报告渲染
├── get_facet_stats()    分面统计
└── 知识关系网           NetworkX + Plotly 可视化（同版本交付）
```

**验收标准**：搜索+问答功能不变，分面统计接口不变。

#### 第五步：知识库管理重构（v0.9.0，低风险）

`hub()` + `manage()` 页面逻辑优化，与 `doc_manager.py`（第二步已拆）协同：

- hub 页面：分面统计仪表盘改用 `search_engine.py` 接口
- manage 页面：文档列表/查看/删除改用 `doc_manager.py` 接口
- 审核队列 UI：置信度路由落地（待审/死信队列入口）

**验收标准**：文档管理功能不变，审核队列可操作。

### 不做的事

- ❌ 一次性大拆 `kb_query.py`（风险太高，容易引入新 bug）
- ❌ 重写测试框架（当前阶段先手动验收，后续补单元测试）
- ❌ 引入类型检查（mypy/pyright）——有成本，收益低

### 当前版本（v0.6.0）验收通过后再启动第一步
