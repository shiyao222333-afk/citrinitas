# BUG 修复追踪 — v1.0.0 守望文件夹

> 创建时间：2026-06-24  
> 来源：多轮代码审查（A4 防御纵深 + A2 链路追踪 + A3 交叉校验 + A5 架构边界）

## P0 — 必须修复（功能不正确）

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| **F1** | 6 处 `except Empty` 应为 `except Full`，队列满时文件静默丢失 | `watcher_v2.py:1082,1122,1251,1287,1328,1751` | ✅ 已修复（commit 待推送） |
| **F2** | `_queued_files.add(filepath)` 应为 `fp`，重复入队检查失效 | `watcher_v2.py:1249` | ✅ 已修复（commit 待推送） |
| **F3** | `metadata` 缺少 `needs_review` 字段，UI 待审核标签页永远为空 | `watcher_v2.py:1004-1006` | ✅ 已修复（commit 待推送） |

## P1 — 应该修复（影响稳定性/体验）

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| **F4** | `WatchHandlerV2` 缺少 `on_moved()`，剪切粘贴文件不触发处理 | `watcher_v2.py:1098` | ✅ 已修复（commit 待推送） |
| **F5** | `WATCH_V2_INFRA_RETRY_INTERVAL` 重复定义，`pipe_cfg.yaml` 配置项无效 | `config/settings.py:275-298` | ✅ 已修复（commit 待推送） |

## P2 — 可延后

| # | 问题 | 位置 | 状态 |
|---|------|------|------|
| **F6** | 无优雅关闭，Ctrl+C 时状态可能不一致 | `watcher_v2.py` 全局 | ✅ 已修复（commit 待推送） |
| **F7** | 无配置热重载，改 `pipe_cfg.yaml` 必须重启 | `watcher_v2.py` / `config/settings.py` | ⬜ 延后到 v1.1.0 |

## 修复顺序

1. ✅ F1 — 修复 6 处 `except Empty` → `except Full`
2. ✅ F2 — 修复 `_queued_files.add(filepath)` → `fp`
3. ✅ F3 — 添加 `needs_review` 到 `metadata`
4. ✅ F4 — 添加 `on_moved()` 方法
5. ✅ F5 — 修复 `WATCH_V2_INFRA_RETRY_INTERVAL` 重复定义

## 验证方法

修复完成后：
1. 语法检查：`python -m py_compile watcher_v2.py config/settings.py`
2. 功能验证：丢文件到 `data/inbox/`，确认处理正常
3. UI 验证：确认"待审核"标签页能看到守望文件夹产生的低置信度文件
