# A8 审查：组件契约一致性与资源管理

**审查角度**：组件契约一致性 + 状态/资源管理  
**审查日期**：2026-06-24

---

## 审查范围

- `search_engine.py` (782行)
- `report_renderer.py` (447行)

---

## 发现的问题

### P1 级别（已修复）

| 编号 | 位置 | 问题 | 状态 |
|------|------|------|------|
| B1 | `search_engine.py:354` vs `report_renderer.py:20` | **输出目录不一致** — `local_data/reports` vs `data/reports` | ✅ 已修复 |
| B2 | `report_renderer.py:278` | `safe_query` 变量定义后从未使用 | ✅ 已删除 |
| B3 | `report_renderer.py:298` | `all_images` 收集后从未渲染；`all_images_html=""` 始终为 `""` | ✅ 已删除 |
| B4 | `search_engine.py:260` | `search("")` 空查询直接传给 `_embed()` | ✅ 已修复 |

### P2 级别（v1.1.0 修复）

| 编号 | 位置 | 问题 |
|------|------|------|
| B5 | `search_engine.py:663 vs 665` | `answer()` 返回 chunks 格式不一致（错误时 deduped，成功时 expanded） |
| B6 | `search_engine.py:78` | `facet_filter` 无效键静默忽略，用户输错 key 无提示 |
| B7 | `report_renderer.py:89` | `formula_to_html_spans()` 每次调用重新编译正则 |

---

## 验证结果

```
语法检查：✅ PASS（两个文件）
模块导入：✅ PASS
OUTPUT_DIR 一致性：✅ PASS
空查询保护：✅ PASS
```

---

## 搜索阶段模块状态

| 文件 | 行数 | 职责 |
|------|------|------|
| `search_engine.py` | ~786 | 搜索 + LLM 问答 |
| `report_renderer.py` | ~447 | HTML/PDF 报告渲染 |
| `utils/llm_helpers.py` | ~50 | LLM 辅助函数 |

---

---

# A9 审查：可测试性与运行时行为

**审查角度**：验证模块独立性、导入链完整性、运行时行为正确性  
**审查日期**：2026-06-24

## 发现的问题

### P1 级别（已修复）

| 编号 | 位置 | 问题 | 状态 |
|------|------|------|------|
| D1 | `search_engine.py` | **重构遗留死导入** — 移动函数后未清理 12 个 import（subprocess/io/base64/math/tempfile/html/hashlib/Optional/datetime/FPDF/PILImage等） | ✅ 已清理 |
| D2 | `report_renderer.py` | `Optional` 导入未使用 | ✅ 已删除 |
| D3 | `search_engine.py` | `report_renderer` 导入中 6/7 个函数未使用（只有 `render_report_html` 实际用到） | ✅ 精简为只导入 `render_report_html` |

### P2 级别（v1.1.0 修复）

| 编号 | 位置 | 问题 |
|------|------|------|
| E4 | `search_engine.py:164` | `score_threshold` 为 0.0 时（falsy）跳过过滤，已安全但不精确 |
| E5 | `report_renderer.py:83-84` | `formula_to_html_spans()` 每次调用重新编译正则 |
| E6 | `report_renderer.py:293` | 若 LLM 在 LaTeX 公式内放置 [引用N]，会被错误转为 HTML link |

## 模块状态（最终版）

| 文件 | 行数 | 导入数 | 职责 |
|------|------|--------|------|
| `search_engine.py` | ~740 | 10 | 搜索 + LLM 问答 |
| `report_renderer.py` | ~443 | 9 | HTML/PDF 报告渲染 |
| `utils/llm_helpers.py` | ~50 | 2 | LLM 辅助函数 |

---

## 累计审查角度

1. ✅ A1: 代码质量
2. ✅ A2: 链接跟踪
3. ✅ A3: 交叉验证
4. ✅ A4: 纵深防御
5. ✅ A5: 架构边界
6. ✅ A6: 数据流完整性
7. ✅ A7: 搜索质量与极端场景
8. ✅ A8: 组件契约一致性与资源管理
9. ✅ A9: 可测试性与运行时行为（死导入清理）
