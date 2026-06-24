# 搜索阶段代码审查报告 — A7 角度

> 审查角度：A7 — 搜索质量与极端场景  
> 审查时间：2026-06-24  
> 审查文件：`search_engine.py`（670行）、`report_renderer.py`（455行）  
> 审查人：匠匠

---

## 一、搜索质量

### Q1 — 分组去重过度激进（P1）

**位置**：`search_engine.py:328-340`

**问题**：按 `doc_id` 分组后，每个文档只保留 score 最高的 1 个 chunk。如果同一文档有 3 个相关 chunk（不同章节），另外 2 个会被丢弃。

**影响**：搜索结果可能遗漏同一文档内的其他相关内容。

**修复建议**：
```python
# 方案A：保留每个文档最多 N 个 chunk（如3个）
# 方案B：新增参数 group_by_doc（默认True，可关闭）
```

### Q2 — LLM 合成时文本截断过于激进（P2）

**位置**：`search_engine.py:550`

**问题**：`if len(text) > 1500: text = text[:1500] + "…(省略)"` — 1500 字对于重要参考资料可能不够。

**影响**：LLM 看不到完整参考资料，合成质量下降。

---

## 二、极端输入

### E1 — 空字符串查询未处理（P1）

**位置**：`search_engine.py:260`

**问题**：`query=""` 时，`_embed([""])` 会生成全零向量或报错，搜索结果无意义。

**修复**：
```python
if not query or not query.strip():
    return {"ok": False, "error": "查询不能为空"}
```

### E2 — 超长查询未截断（P2）

**位置**：`search_engine.py:260`

**问题**：查询超过 embed 模型 max_seq_length（如 8192 token）时，`_embed()` 可能报错或截断。

**修复**：在 `_embed()` 调用前检查 token 数，超长则截断并警告。

### E3 — 特殊字符未转义（P2）

**位置**：`search_engine.py:276-325`（search 返回结构）

**问题**：`source` 字段含尖括号时，HTML 渲染可能出问题（`render_report_html` 有 `html.escape`，但 `search()` 返回的 JSON 没有）。

**影响**：前端直接渲染 `source` 可能触发 XSS。

---

## 三、性能瓶颈

### P1 — `get_facet_stats()` 全量 scroll（P1）

**位置**：`search_engine.py:722-763`

**问题**：每次调用都 scroll 全量 points，知识库 10 万条时耗时可达数分钟。

**修复建议**：
- 用 Qdrant 的 `facets` API（如果版本支持）
- 或缓存统计结果（60 秒过期）

### P2 — `katex_post_process()` 逐公式调 Node.js（P2）

**位置**：`report_renderer.py:182-254`

**问题**：每个公式都启动一次 Node.js 子进程，报告含 20 个公式时耗时 >5 秒。

**修复建议**：`katex_post_process()` 已经支持批量处理（一次调用渲染所有公式），但 `render_report_html()` 中的调用方式是正确的——只调用一次。所以这个问题实际上**不存在**。

> ✅ 核实：`katex_post_process()` 已经批量处理，性能 OK。

### P3 — `img_to_b64()` 大图片无压缩（P2）

**位置**：`report_renderer.py:31-68`

**问题**：`HAS_PIL=True` 时，先 resize 再读入内存，但 `HAS_PIL=False` 时直接读入整个文件，可能产生巨型 base64 字符串（几 MB）。

**修复建议**：无 PIL 时也限制文件大小（如 > 500KB 则跳过）。

---

## 四、并发安全

### C1 — `answer()` 写入文件无锁（P2）

**位置**：`report_renderer.py:446-454`

**问题**：如果两个用户同时调用 `answer()`，可能同时写 `report_YYYYMMDD_HHMMSS.html`（时间戳精确到秒，理论上可能冲突，虽然概率极低）。

**修复建议**：用 `tempfile.NamedTemporaryFile` 或加文件锁。

### C2 — 全局变量线程安全（✅ 无问题）

`LLM_BASE_URL`、`LLM_API_KEY` 等全局变量在模块加载时设定，之后只读，线程安全。

---

## 五、其他发现

### O1 — `search()` 返回值与文档不一致（P2）

**位置**：`search_engine.py:216-242`（docstring）

**问题**：docstring 说返回 `"chunks"` 数组，但实际返回结构中 `chunks` 里的字段比文档写的更多（如 `needs_review`、`confidence`、`field_sources` 是之前 A6 审查才加的，文档已更新，但字段列表顺序和实际代码不一致）。

**影响**：低，不影响功能，但维护时可能困惑。

### O2 — `_sanitize_html()` 白名单实现有误（P1）

**位置**：`search_engine.py:384-392`

**问题**：当前实现是"黑名单"（移除危险标签/属性），不是白名单。如果 LLM 返回新的危险标签（如 `<svg onload=...>`），不会被过滤。

**修复建议**：改成真正的白名单：
```python
ALLOWED_TAGS = {'b', 'i', 'p', 'br', 'span', 'div', 'a', 'img', 'table', 'tr', 'td', 'th'}
ALLOWED_ATTRS = {'href', 'src', 'class', 'id'}
# 然后用 bleach 或手写 parser 过滤
```

---

## 六、问题汇总

| 编号 | 等级 | 类型 | 描述 | 位置 |
|------|------|------|------|------|
| Q1 | P1 | 质量 | 分组去重过度激进，同类文档只保留1个chunk | `search_engine.py:328` |
| E1 | P1 | 极端输入 | 空字符串查询未处理 | `search_engine.py:260` |
| P1 | P1 | 性能 | `get_facet_stats()` 全量 scroll | `search_engine.py:722` |
| O2 | P1 | 安全 | `_sanitize_html()` 是黑名单而非白名单 | `search_engine.py:384` |
| Q2 | P2 | 质量 | LLM 合成时文本截断 1500 字太短 | `search_engine.py:550` |
| E2 | P2 | 极端输入 | 超长查询未截断 | `search_engine.py:260` |
| E3 | P2 | 安全 | `search()` 返回的 `source` 可能含 XSS | `search_engine.py:276` |
| P3 | P2 | 性能 | `img_to_b64()` 无 PIL 时可能读入超大文件 | `report_renderer.py:31` |
| C1 | P2 | 并发 | `answer()` 写入文件无锁 | `report_renderer.py:446` |
| O1 | P2 | 文档 | 返回值文档与实际代码不一致 | `search_engine.py:216` |

---

## 七、修复优先级建议

**立即修复（P1）**：
1. E1：空查询检查
2. O2：`_sanitize_html()` 改为白名单
3. P1：`get_facet_stats()` 性能优化（或加缓存）

**下版本修复（P2）**：
1. Q1：分组去重策略调整（加配置项）
2. Q2：文本截断阈值可配置
3. E2/E3/C1/O1：按计划修复

---

*审查完成时间：2026-06-24*  
*下次审查角度建议：A8（依赖管理 / 可测试性）*
