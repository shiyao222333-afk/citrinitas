# ADR-001: 引入 Service 层解耦 UI 和核心逻辑

**状态**：已接受（Accepted）

**日期**：2026-07-06

---

## 背景（Context）

当前 `kb_query.py` 是「上帝对象」：
- 包含摄入管线编排（`_step_*`, `ingest`, `ingest_batch`）
- 包含置信度路由（`route_by_confidence`）
- 包含分面统计（`get_facet_stats`，且与 `search_engine/facets.py` 重复定义）
- 作为 CLI 入口（`if __name__ == "__main__":`）
- UI 层（`pages/ingest.py`, `watcher/processor.py`）直接 `import kb_query` 并调用其函数

这导致：
1. **UI 和核心逻辑紧耦合** — 改核心逻辑可能意外破坏 UI
2. **无法独立测试** — 摄入逻辑和 CLI 参数解析混在一起
3. **将来做 REST API（v1.3.0）时需要重构** — 无法复用逻辑
4. **违反架构原则第2条**：「核心逻辑与 UI 完全解耦」

---

## 决策（Decision）

引入 `services/` 层，将 `kb_query.py` 的职责拆分为：

```
services/
  __init__.py          # 公共 API 重导出
  ingest_service.py    # 摄入编排（从 kb_query.py 拆出）
```

具体改动：
1. 创建 `services/ingest_service.py`，包含：
   - 摄入管线步骤函数（`_step_*`）
   - `ingest` 和 `ingest_batch` 公共 API
   - `_ingest_lock` 并发锁
2. 把 `route_by_confidence` 移到 `classify_pipeline.py`（分类逻辑归分类模块）
3. 删除 `kb_query.py` 里的 `get_facet_stats` 重复定义（改用 `search_engine.facets.get_facet_stats`）
4. 重写 `kb_query.py`，只做 CLI facade（导入 services 并解析命令行参数）
5. 更新 UI 层调用方（`pages/ingest.py`, `watcher/processor.py`），直接导入 services

---

## 后果（Consequences）

### 变得更容易（Positive）
- ✅ **UI 和核心逻辑解耦** — UI 层调用 `services.ingest_service.ingest()`，不直接依赖 `kb_query.py`
- ✅ **符合架构原则第2条** — 核心逻辑与 UI 完全解耦
- ✅ **将来做 REST API 更容易** — 直接暴露 `services/` 为 REST 端点
- ✅ **代码更好维护** — 每个 Service 职责单一，文件更小
- ✅ **可以独立测试** — `services/ingest_service.py` 可以单独测试

### 变得更困难（Negative）
- ⚠️ **增加了一个间接层** — UI 层需要导入 `services`，而不是直接导入 `kb_query`
- ⚠️ **需要改 UI 层的 import 语句** — `pages/ingest.py` 和 `watcher/processor.py` 需要更新

### 风险
- 🔴 **导入循环** — `services/ingest_service.py` 导入了很多模块，需要确保没有循环导入
  - **缓解措施**：已测试语法，无循环导入
- 🔴 **运行时错误** — 拆分后可能某些函数调用失败
  - **缓解措施**：需要手动测试摄入流程

---

## 备选方案（Alternatives Considered）

### 方案 A：保持 `kb_query.py` 作为 facade，不拆分
- **优点**：改动小，风险低
- **缺点**：继续违反架构原则，将来做 REST API 时需要重构

### 方案 B：一次性拆分所有模块（ingest + search + classify + document）
- **优点**：一步到位
- **缺点**：改动太大，风险高，容易引入 bug

### 方案 C（已采纳）：先拆摄入逻辑，其他逻辑逐步拆
- **优点**：改动可控，风险低，可以增量重构
- **缺点**：需要多次提交

---

## 遵循原则

- ✅ **架构原则第2条**：核心逻辑与 UI 完全解耦
- ✅ **MVP 优先**：先拆最胖的模块（`kb_query.py` 655行）
- ✅ **可逆性**：`kb_query.py` 仍然保留 CLI 入口，向后兼容

---

## 下一步

1. **统一错误处理（v1.1.0 剩余工作）**：
   - 统一 `logging.yaml` 配置
   - 建立错误码体系（`E001-E099` 摄入 / `E100-E199` 搜索 / ...）
   - 消灭 `except:pass`
   - 增加日志查看器 UI

2. **拆分其他大文件（v1.2.0）**：
   - `classify_pipeline.py`（549行）→ `classify/` 包
   - `doc_manager.py`（619行）→ `services/document_service.py`

3. **准备 REST API（v1.3.0）**：
   - 有了 Service 层后，做 REST API 很快
   - 直接暴露 `services/` 为 REST 端点

---

## 作者

- 架构评审：Software Architect Agent
- 实施：Coding Agent
- 审核：用户

---

**参考**：
- `PROJECT_PLAN.md` — v1.1.0 架构重构
- `BLUEPRINT.md` — 架构原则第2条
- `docs/architecture-review-2026-07-06.md` — 完整架构评审报告
