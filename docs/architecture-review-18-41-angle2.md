# 架构复审（第二视角）— #18–#41

> 上一轮（architecture-review-18-41.md）从「结构 / 导入链路」角度查，发现导入 bug。
> 本轮换三个实战视角重查：**数据正确性（幂等）、审核队列出口、健壮性**。
> 结论：方向没问题，但发现 3 个比导入 bug 更隐蔽的系统性问题（含 1 个已实锤的静默瘫痪）。

---

## 仍待修（上一轮遗留，未动）

### 🔴 BLOCKER — `ingest_pipeline.py:17` 导入错误（应用启动即崩）
```python
from config.classifications import normalize_facet_values, normalize_lifecycle
```
`config/classifications.py` 只转发了 `normalize_facet_values`，**没有转发 `normalize_lifecycle`**（它只定义在 `config/normalize.py`）。
→ 加载链 `main → pages.ingest → ingest_pipeline` 在**启动时刻**就 `ImportError`，程序起不来。
→ 修复（一行）：`from config.normalize import normalize_facet_values, normalize_lifecycle`
→ 上一轮已用项目 venv 实锤，本轮不再赘述。

---

## 视角一：数据正确性与幂等性 ✅ 基本健康

| 检查项 | 结论 |
|---|---|
| `normalize_free_text_fields` 重复调用是否幂等 | ✅ 是。已归一的标准词再次归一仍是自身；udc 清空后二次调用跳过；tags/keywords 保留原文的也稳定 |
| `normalize_lifecycle` 重复调用是否幂等 | ✅ 是。标准 key 原样返回，不会二次翻转 |
| `build_payloads` 是否在同一遍里重复归一 | ✅ 否。`_prepare_metadata` 每次都从 `base_meta` 重建新 dict，归一只挂一次 |
| 重摄入（同文件更新）是否会越归越偏 | ✅ 不会，因每次从原始 `base_meta` 重跑 |

💭 **小建议（非阻塞）**：`normalize_facet_values` 的「子串兜底」在重摄入时可能产生"惊喜式"归一。
例：`content_type="笔记"` 子串命中 `personal_note`；`domain="开发"` 子串命中 `in_progress`（lifecycle 侧）。
当前不致命（已是标准枚举），但建议在审核页/详情页**展示归一后的最终值**，让用户能核对 AI 的归类是否被算法改写了。

---

## 视角二：审核队列的「出口」⚠️ 发现两个真问题

> 背景：`needs_review=True` 的文档进「待审核」标签页（`pages/hub/review.py`），用户可「通过并入库」（写 `needs_review=False`）或「丢弃」。
> 手动审核出口是通的（`update_metadata` 会更新该文档**所有分块**，doc_manager.py:113-119，已确认）。

### 🔴 BLOCKER — `vocab_doctor --fix` 修复后却把文档永久卡在队列

预期闭环：**用户往词表加词 → 跑 `vocab_doctor --fix` 把存量标签归一 → 文档自动离开待审核队列**。

实际断裂：
- `vocab_doctor.normalize_doc_payload()` 注释明写「**不动 needs_review**」（第 65 行）。
- 修复后 `tags`/`keywords` 已归并为受控词，但 payload 里的 `needs_review` 仍是 `True`。
- 审核页按 `needs_review=True` 过滤 → **文档永远留在队列里**，即使它的"病因"已消除。

后果：医生脚本本应自动化消化存量，现在只能归一标签、清不掉标记，最终仍要人工去 UI 点"通过"——脚本的意义被腰斩。

**修复方向**：`fix_normalize` 在 `classify_payload(归一后payload)` 为空（即已无受控问题）时，顺手 `set_payload({"needs_review": False})`。注意要与下方"单一布尔"问题联动处理（见下）。

### 🟡 设计异味 — `needs_review` 是单一布尔，被 3+ 个生产者写入、只有审核页会整体清空

生产者：
1. 上传页置信度路由（`pages/ingest.py:256`）
2. 守望夹置信度路由（`watcher/processor.py:291`）
3. 词表校验（`vocabulary.py:194`）

清空者：仅审核页「通过」按钮（整体设 `False`）；医生脚本（本应，但没做）。

这导致两种相反的故障：
- **过度释放**：文档因"低置信度"进队列；你加了个词表词 + 跑医生，医生若清 `needs_review`，会连"低置信度"的标记一起清掉 → 低质量文档被提前放行。
- **卡死**：就是上面那条——医生归一了词表问题却清不掉标记。

**根因修复（推荐）**：把 `needs_review: bool` 替换为 `review_reasons: list[str]`（如 `["vocab_uncontrolled"]` / `["low_confidence"]`）。
- 每个生产者只 `add` 自己的原因；每个修复者只 `remove` 自己能解决的原因。
- "是否需要审核" = `len(review_reasons) > 0`。
- 向后兼容：现有 `needs_review=True` 的文档迁移为 `["legacy"]` 即可。
- 这是可演进、低风险（加字段 + 双写过渡），一次性解决"过度释放 + 卡死"两端的耦合。

---

## 视角三：健壮性 🔴 发现一个静默瘫痪级问题

### 🔴 BLOCKER — 词表文件形状错误 → 静默清空整个词表 → 全库被打进待审核（已实锤）

`load_vocabulary()` 的 `try/except` 设计意图是"文件缺失/损坏不阻断摄入"，但它把**任何异常**都吞掉并回退空词表。

实测（项目 venv，临时构造错误形状）：
```
[vocab] 词表加载失败（回退空词表，不阻断摄入）: 'list' object has no attribute 'items'
themes 实际: {}     ← 整个词表被静默清空
lookup 大小: 0
normalize_theme('机械设计') = None   ← 正常词也被判"未受控"
```

触发场景：用户手滑把 `controlled_vocabulary.json` 的 `themes` 写成列表（而非 `{标准词:[同义词]}`）。
连锁反应：
1. 加载失败 → 回退**空词表** + 仅一行 warning（程序照常启动）。
2. 此后所有新摄入：tags/keywords 在空词表下**全部判未受控** → `needs_review=True`。
3. 全部新文档无声无息地涌进待审核队列，用户直到审核页爆掉才察觉。

这正是上一轮说的"最严档 + 空词表兜底"组合的反噬：**兜底为了不崩，却制造了一个更隐蔽的全局退化**。

**修复方向（防静默瘫痪）**：
- 加载时**校验形状**（themes/keywords 必须是 dict，udc_subdivisions 必须是 dict）。
- 形状错误时**不要静默回退空表**，而要：保留上一次成功加载的缓存（若有）+ 明确报错（日志 ERROR 级别 + 启动告警），让用户立刻知道词表坏了。
- 即「缺失文件 = 不约束（向后兼容）」，但「文件存在却形状错 = 必须吵」。

### 🟡 线程安全 — 模块级全局词表缓存无锁

`vocabulary.py` 的 `_VOCAB_CACHE / _THEME_LOOKUP / _KEYWORD_LOOKUP / _UDC_CODES` 是模块全局，`_build_lookup` 同时改写其中三个。
- 调用点：摄入在守望夹**后台线程**跑 `normalize_free_text_fields` → `load_vocabulary`；UI 保存 `/vocab` 在**主线程**跑 `save_vocabulary`。
- 两者都调 `_build_lookup`，存在竞态：一个线程读到"新旧混搭"的半构建查找表。
- 概率低，但是真实数据竞态。修复：把四个全局收进一个 `namespace` 对象一次性 swap，或用 `threading.Lock` 包住 load/reload/save。

### 🟡 保存健壮性 — `save_vocabulary` 静默丢行 + 丢未知键

- 工作副本某行缺 `std`/`code` 时，dict 推导式的 `if ...strip()` 直接**跳过该行**（数据静默丢失，无报错）。建议保存前校验形状并回具体错误。
- 只保留 `version`/`description` 头，丢失其它顶层键与 JSON 注释。对配置文件可接受，但值得知道。

---

## 优先级总表

| # | 严重度 | 问题 | 视角 | 修复成本 |
|---|---|---|---|---|
| 1 | 🔴 | 导入 bug（启动即崩） | 遗留 | 1 行 |
| 2 | 🔴 | 词表形状错误 → 静默清空 → 全库进队列 | 健壮性 | 中（加形状校验+保留旧缓存） |
| 3 | 🔴 | 医生 --fix 不动 needs_review → 文档卡队列 | 审核出口 | 小（加条件清标记） |
| 4 | 🟡 | needs_review 单一布尔被多生产者耦合 | 审核出口 | 中（改 review_reasons） |
| 5 | 🟡 | 词表缓存多线程竞态 | 健壮性 | 小（收 namespace/加锁） |
| 6 | 🟡 | save 静默丢行/丢键 | 健壮性 | 小（保存前校验） |
| 7 | 💭 | 子串模糊归一建议展示给用户核对 | 正确性 | 小（UI） |

---

## ADR 提议

### ADR-002：受控词表加载失败不应静默回退空表
- **Context**：当前 `load_vocabulary` 吞掉所有异常回退空表，导致词表形状错误时全库标签被判未受控、无声涌入待审核。
- **Decision**：区分「文件缺失」（向后兼容：不约束）与「文件存在但形状错误」（必须显式报错 + 保留上次成功缓存 + 启动告警）。加载前做形状校验。
- **Consequences**：多一处校验逻辑；换来"词表坏了立刻可知"而非"全局静默退化"。

### ADR-003：`needs_review` 布尔升级为 `review_reasons` 列表
- **Context**：单一布尔被置信度路由与词表校验多个独立生产者写入，清空时无法区分原因，导致过度释放或卡死。
- **Decision**：改为 `review_reasons: list[str]`，各生产者 add 自身原因、各修复者 remove 自身原因；需审核 = 列表非空。
- **Consequences**：需审核判定更精确；需做一次字段迁移；审核页/医生脚本按原因精确消费。

> 注：本轮仅做分析，未改任何代码。所有 #18–#41 改动仍未提交。
