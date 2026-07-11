# 熔知 Citrinitas — #18–#41 架构审查报告

> 审查类型：🔍 纯分析（只读代码，未改动任何文件）
> 审查范围：#18–#35 存储加固、#28 受控词表（#36–#41）
> 审查视角：模块职责 / 依赖方向 / 集成风险 / 可维护性

## 一、总体结论

架构方向是**对的**，几处关键决策都踩在了正确位置：

- ✅ **单一摄入汇合点** `build_payloads()`（守望夹 + UI 上传两条路线唯一汇合处）—— 词表校验挂这里，一处覆盖两条路线，设计正确。
- ✅ **存储加固方向正确**：`update_document` 用 `set_payload` 做 key-level merge（不重写向量）；`delete_orphan_points` 有 `keep_ids` 空值守卫（绝不误删整篇）；词汇保存用 `tmp + os.replace` 原子写。这些都与 #31「存储原子性」原则一致。
- ✅ **受控词表分层清晰**：`vocabulary.py`（加载+校验）与 `config/normalize.py`（分面枚举守卫）职责不混。

但发现 **1 个 🔴 阻断级 bug（会让程序启动即崩）** + **2 个 🟡 可优化架构点**。阻断 bug 必须由你确认后修复，否则本地放 epub 验收时程序根本起不来。

---

## 🔴 阻断：ingest_pipeline 的导入错误（启动即崩溃）

**现象（已用项目 venv 实测复现）：**

```
from config.classifications import normalize_lifecycle
ImportError: cannot import name 'normalize_lifecycle' from 'config.classifications'
```

**根因：**
- `normalize_lifecycle` 只定义在 `config/normalize.py:432`。
- `config/classifications.py:401` 只 re-export 了 `normalize_facet_values` + `FUZZY_FACET_MAPPING`，**没有** re-export `normalize_lifecycle`。
- 但 `ingest_pipeline.py:17` 写的是 `from config.classifications import normalize_facet_values, normalize_lifecycle`。

**影响范围（已确认）：**
- `main.py:35` → `from pages.ingest import page_ingest` → `ingest_pipeline` 在**启动期**就会 ImportError。
- 结论：当前这批未提交改动下，**App 根本无法启动**；即便绕过启动，所有录入（UI 上传 + 守望夹）也会失败。
- 为什么之前没暴露：单测只跑了 `test_vocabulary.py`（它不 import ingest_pipeline），编译检查（`py_compile`）只查语法不查导入。**没有任何集成导入测试**是这次漏网的真正根因。

**修复（一行）：** `ingest_pipeline.py:17` 改为

```python
from config.normalize import normalize_facet_values, normalize_lifecycle
```

两个函数都真实存在于 `config/normalize.py`，且 `config.normalize` 内部对 `config.classifications` 的导入都是**函数体内惰性导入**，顶层 `import config.normalize` 不会触发循环依赖，安全。

---

## 🟡 根因治理：归一化层跨两模块、靠 re-export 串联（脆弱）

`config/normalize.py` 是真正实现（映射表 + `normalize_facet_values` + `normalize_lifecycle`），`config/classifications.py` 是 schema 定义 + 旧路径 re-export。

**问题：** re-export 永远比实现「慢一步」。这次漏了 `normalize_lifecycle` 就是典型。下次新增归一函数，极易再漏一个。

**建议（二选一，推荐 A）：**
- **A（最小改动）：** 所有调用方统一从 `config.normalize` 导入归一函数，`classifications` 只负责 schema（枚举常量）。即上面那一行修复顺带达成。
- **B：** 把全部归一函数 + 映射表搬进 `classifications`，`normalize.py` 退化为纯内部模块。改动更大，收益相似。

---

## 🟡 needs_review 决策分散在三层（当前无 bug，但易腐）

`needs_review=True` 目前由三处独立设置：
1. `pages/ingest.py`（置信度路由）
2. `watcher/processor.py`（置信度路由）
3. `ingest_pipeline.normalize_free_text_fields`（词表受控校验）

**当前兼容性：** 词表代码只置 `True`、绝不置 `False`，与置信度路由的 `True` 靠 OR 语义正好并存，无逻辑冲突。✅

**但：** 「这份文档该不该进待审核队列」的策略散落三处，将来调规则要改三个地方。建议抽一个集中决策函数：

```python
def decide_needs_review(confidence_flag: bool, vocab_uncontrolled: bool) -> bool:
    return bool(confidence_flag or vocab_uncontrolled)
```

---

## 💭 次要 / 隐患（当前可接受，仅记录）

1. **vocabulary.py 全局可变单例缓存**（`_VOCAB_CACHE` 等模块级变量）：单进程 NiceGUI 没问题；若将来「CLI 医生脚本」与「服务进程」同时跑，缓存会读到旧词表。当前规模可接受。
2. **vocab_doctor.py 直接 `requests` 调 Qdrant**，scroll/payload 逻辑与 `doc_manager.py` 的 `_query_doc_points` / `list_documents` 重复。可复用后者，减少一份联网逻辑。
3. **udc_code 未受控即清空**，原值只进日志、库里不可恢复。受控词表系统下这是合理取舍（错码比空更糟），且文档进待审核队列人工可补——但需知道原值仅存日志。

---

## 优化建议清单（按优先级）

| # | 优先级 | 建议 | 工作量 |
|---|--------|------|--------|
| 1 | 🔴 必做 | 修复 ingest_pipeline.py:17 导入（否则无法启动/录入） | 1 行 |
| 2 | 🟡 建议 | 归一化导入统一归口 `config.normalize`，消除 re-export 滞后类 bug | 1 行（顺带） |
| 3 | 🟡 建议 | 抽 `decide_needs_review` 单一决策函数，集中审核策略 | 小 |
| 4 | 💭 防复发 | **加「导入冒烟测试」**：测试里 `import main` / 每个 `pages.*` / `ingest_pipeline` / `watcher`，让此类集成导入错误在 L2/CI 就暴露 | 小 |
| 5 | 💭 整洁 | vocab_doctor 复用 doc_manager 的查询函数，去掉重复联网代码 | 小 |

---

## ADR 提议：归一化函数归口单一模块

- **Status:** 提议（待你确认后实施）
- **Context:** #41 新增 `normalize_lifecycle` 落在 `config/normalize.py`，但 `ingest_pipeline` 从 `config.classifications` 导入它，而 classifications 只 re-export 了另外两个归一函数，导致启动期 ImportError。根因是「实现在 normalize、旧路径 re-export 在 classifications」的脆弱双轨。
- **Decision:** 调用方统一从 `config.normalize` 导入所有归一函数；`config.classifications` 仅保留 schema 常量（CONTENT_TYPES 等）。如未来新增归一函数，只在一处定义、一处导入。
- **Consequences:** 少一条 re-export 链路 → 减少「漏一个」类 bug；代价是 classifications 的「对外兼容导入点」语义变窄（目前只有极少数老调用依赖，影响可控）。
