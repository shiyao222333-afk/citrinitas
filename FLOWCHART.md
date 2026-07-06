# 流程框图 — Athanor

> 每个 Phase 1 拆解出的任务必须映射到下面某个节点。
> Mermaid 图展示主干的逻辑分支，节点表定义输入/输出/任务。
> 按功能域拆分四张子图，便于移动端阅读。

---

## 总览

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐
│  摄 入   │───→│ 知识库   │←───│   搜  索     │    │  其 它   │
│ F1→…→N7  │    │ N7(存储) │    │ N9→N10→User  │    │ DL/W1-3  │
│ F_WATCH  │    │ C_DUP    │    │ F6 外部查询  │    │ 系统保障  │
│ (v2收件箱)│    │ N_UPDATE │    │ N_MANUAL修正 │    │          │
│          │    │ N_DEL    │    │              │    │          │
│          │    │ N_GRAPH  │    │              │    │          │
└──────────┘    └──────────┘    └──────────────┘    └──────────┘
```

---

## 一、摄入流程

> 当前重心。覆盖从"内容进来"到"入库存储"的完整管线。
> 对应节点：F1-F5, F_WATCH, N1, C1, N2, C2, N4_*, C3, N5, C_DUP, N_UPDATE, N6, C4, N8, N7, INBOX

```mermaid
flowchart TB
    F_WATCH([📁 守望v2<br/>data/inbox/ + state.jsonl])
    F1[拖入文件]
    F3[手动输入]
    F4[OCR图片]
    F5[外部推送]

    F_WATCH -->|文件放入inbox<br/>写入完成检测<br/>15故障×5策略| N1
    F1 --> N1
    F3 --> N1
    F4 --> N1
    F5 --> N1

    N1([① 摄入入口]) --> C1{&lt;50MB?}
    C1 -->|是| N2
    C1 -->|否| W1[⚠️ 超限警告]

    W1 --> N2
    N2{② 格式识别} -->|可识别| C2
    N2 -->|不可识别| INBOX_FAILED[📥 inbox/ ← 状态:failed<br/>strategy: dlq_delete]

    C2{类型路由} -->|图片| N4_OCR([②b OCR])
    C2 -->|文档| N4_DOC([②a 文档提取])
    C2 -->|无文件| N4_MAN([②c 手动])

    N4_OCR -->|成功| C3
    N4_DOC -->|成功| C3
    N4_MAN -->|成功| C3
    N4_OCR -.->|异常| INBOX_FAILED
    N4_DOC -.->|异常| INBOX_FAILED

    C3{编码?} -->|可解码| N_PRE
    C3 -->|失败| W2[⚠️ chardet推测]

    W2 --> N_PRE
    N_PRE([预处理<br/>纠错·翻译·去广告]) --> N5
    N5{≤5000字?} -->|是| C_DUP
    N5 -->|否| W3[⚠️ 截断]

    W3 --> C_DUP
    C_DUP{去重?} -->|全新| N6
    C_DUP -->|相似| N_UPDATE([更新已有])

    N6([③ AI分类]) --> C4{置信度?}
    C4 -->|高| N7
    C4 -->|中| N8([④ 审核队列])
    C4 -->|低| DL_CONF[☠ 置信度DLQ<br/>JSON格式]
    N8 -->|确认| N7
    N_UPDATE --> N7

    N7([⑤ 存储完成]) -->|部分坏| N_PAGES([⑥ 逐页分析<br/>WLNK决策])
    N_PAGES --> KEEP([📥 保留原文件<br/>inbox/中保留])
    N_PAGES --> DELETE([🗑 删除原文件<br/>纯文本已入库])

    N7 -->|正常| DONE([✅ 完成])
    N7 -->|书籍/大文件(未来)| N_BOOK([📚 书库归档<br/>归一化源+位置指针])
    N7 -.->|大文件续跑(未来)| N_RESUME([⏸ 断点续存])

    style N7 fill:#d4edda,stroke:#28a745
    style INBOX_FAILED fill:#fff3cd,stroke:#f0ad4e
    style DL_CONF fill:#f8d7da,stroke:#dc3545
    style KEEP fill:#d1ecf1,stroke:#0c5460
    style N_PRE fill:#e2e3e5,stroke:#6c757d
    style N_BOOK fill:#d1ecf1,stroke:#0c5460
    style N_RESUME fill:#fff3cd,stroke:#f0ad4e
```

### 摄入节点定义

| 节点 | 名称 | 输入 | 输出 | 逻辑 | 对应任务 |
|:--:|------|------|------|------|:--:|
| F_WATCH | 守望v2 | data/inbox/ 统一收件箱 | 文件→处理管线 | 统一收件箱 + file_state.jsonl 状态追踪；15故障×5策略(WLNK+逐页分析)；内容驱动保留(v1旧目录启动时自动迁移) | Task 1-6 |
| F1 | 拖入文件 | 本地文件 | 原始内容 | 用户拖入/选择 | 1h |
| F3 | 手动输入 | 键盘/剪贴板 | 原始内容 | 用户打字 | 1i |
| F4 | OCR图片 | 图片/扫描文档 | 原始图像 | PaddleOCR | — |
| F5 | 外部推送 | Alembic/第三方 | 原始内容+元数据 | API/SDK | v0.7.0 |
| N1 | ① 摄入入口 | 各来源 | 原始内容+来源标注 | 统一入口，标注 source_path | 1a, 1h, 1i |
| C1 | 大小检查 | 原始内容 | 通过/警告 | >50MB 警告但不阻止 | 1g |
| N2 | ② 格式识别 | 原始内容 | 格式/编码/层级 | 16B魔数→扩展名→放弃 | 1a, 1c |
| C2 | 类型路由 | 识别结果 | 分派到提取器 | 图片→OCR, 文档→提取, 无文件→直传 | 1f |
| N4_DOC | ②a 文档提取 | PDF/DOCX/EPUB/HTML/TXT/SRT | 纯文本 | 按格式调用提取器(pdfplumber多页) | 1b, 1c, 1e |
| N4_OCR | ②b OCR提取 | 图片/扫描PDF | 纯文本 | PaddleOCR(未安装→needs_review) | — |
| N4_MAN | ②c 手动文本 | 用户输入 | 纯文本 | 直接使用 | 1h |
| C3 | 编码检测 | 字节流 | 解码文本 | UTF-8→GBK→latin-1→chardet | 1d |
| N5 | 文本截断 | 解码文本 | ≤5000字 | 超长截断+提示 | — |
| C_DUP | 去重检测 | 截断文本 | 全新/相似 | Qdrant content_hash 去重 | v0.5.0 |
| N_UPDATE | 更新已有 | 新文本+旧ID | 合并后向量+元数据 | 保留旧来源，追加新来源（⚠️ 未实现，当前仅 skip） | v0.5.0 |
| N6 | ③ AI分类 | 纯文本 | 分面标签+置信度 | classify_document() LLM 按分面体系打分 | v0.4.0 |
| C4 | 置信度路由 | 标签+置信度 | 高→入库, 中→审核, 低→DLQ | 三档阈值：≥0.75 直接 / 0.40-0.75 审核 / <0.40 DLQ | v0.4.5 |
| N8 | ④ 审核队列 | 中置信度结果 | 确认后的标签 | 等待人工确认 | v0.4.5 |
| N7 | ⑤ 存储 | 文本+标签+元数据 | 向量索引+文档注册 | metadata_source + source_path 写入<br/>含预存储钩子（Nigredo 接口）| v0.4.0, v0.7.0(B4) |
| N_PAGES | ⑥ 逐页分析 | 多页文档各页内容 | 每页可删性判断 | analyze_page_content() 5信号:非文本元素/密度/OCR可靠性/提取完整度/内容等效性 | Task 3-4 |
| DL_CONF | ☠ 置信度死信 | 低置信度元数据 | JSON 文件 | 置信度<0.40→移入 local_data/dead_letter/ | v0.4.5 |
| INBOX_FAILED | 📥 收件箱失败 | 处理失败的文件 | 留在 inbox/ + state 条目 | file_state.jsonl 记录 state:failed/needs_review/retry; 15故障×5策略(自动重试/等待基础设施/DLQ/审核/跳过) | Task 5 |
| KEEP | 📥 保留原文件 | 含非文本元素的文件 | 保留在 inbox/ | WLNK:任一页不可删→保留整个文件 | Task 4 |
| DELETE | 🗑 删除原文件 | 全部页面纯文本 | 删除原文件 | WLNK:全部页面可删→内容已入库，可删原文件 | Task 4 |
| N_PRE | 预处理 | 解码后全文 | 清洗后文本 | 自动纠错 + 统一语言翻译 + 去除广告/抓取残留（v1.5.0 规划） | 未来 |
| N_BOOK | 📚 书库归档 | 书籍类已存储内容 | 归一化源文件+位置指针+书目录 | 录入前归一化为统一格式，每块记章节/段落指针，搜索按源聚成书/丛书（v1.2.0 规划） | 未来 |
| N_RESUME | ⏸ 断点续存 | 大文件处理中状态 | 最后完成块+续跑 | 源持久化+增量写+记块，关机重启可续（v1.2.x 规划，文字小说优先） | 未来 |

### 摄入连线

| 起→止 | 传递内容 | 触发条件 |
|------|------|------|
| F_WATCH→N1 | inbox 文件+状态追踪 | watchdog 检测到新文件 → 写入完成检测 → 15故障×5策略 |
| F1→N1 | 原始内容 | N1 完成 |
| N1→C1 | 原始内容 | N1 完成 |
| C1→N2 | 原始内容(≤50MB) | 通过 |
| N2→C2 | 识别结果 | 可识别 |
| N2→INBOX_FAILED | 文件+错误日志 | 不可识别(strategy: dlq_delete) |
| C2→N4_DOC | 识别+文档 | 类型=文档 |
| C2→N4_OCR | 识别+图片 | 类型=图片 |
| C2→N4_MAN | 识别+文本 | 类型=无文件 |
| N4_*→C3 | 提取文本 | 提取完成 |
| N4_*→INBOX_FAILED | 文件+状态记录 | 提取异常/失败(15故障类型自动分类) |
| C3→N5 | 解码文本 | 编码通过 |
| C3→INBOX_FAILED | 文件+状态记录 | 编码全败（latin-1 兜底已实际不可达） |
| N5→C_DUP | 截断文本 | 截断完成 |
| C_DUP→N6 | 截断文本 | 去重:全新 |
| C_DUP→N_UPDATE | 新文本+旧ID | 去重:相似（⚠️ 未实现，当前 skip） |
| N_UPDATE→N7 | 合并后数据 | 更新完成 |
| N6→C4 | 标签+置信度 | AI分类完成 |
| C4→N7 | 高置信标签 | 置信通过 (≥0.75) |
| C4→N8 | 中置信标签 | 置信不足 (0.40-0.75) |
| C4→DL_CONF | 低置信元数据 | 置信过低 (<0.40) |
| N8→N7 | 确认标签 | 人工审核完成 |
| N7→N_PAGES | 完成存储的文档 | 摄入来源=watch_v2 |
| N_PAGES→KEEP | 原文件保留 | WLNK:任一页不可删 |
| N_PAGES→DELETE | 删除原文件 | WLNK:全部页面可删 |
| N7→DONE | — | 非守望来源正常完成 |
| C3→N_PRE | 解码后全文 | 编码通过 |
| N_PRE→N5 | 清洗后全文 | 预处理完成 |
| N7→N_BOOK | 书籍类已存储内容 | 书籍来源(未来) |
| N7→N_RESUME | 大文件处理中状态 | 大文件续跑(未来) |

---

## 二、搜索流程

> 覆盖从"用户提问"到"LLM 回答+溯源"的检索管线。
> 也服务外部程序调用（原则4：工序衔接）。
> 对应节点：F6, N9, N10, N_MANUAL

```mermaid
flowchart TB
    User([用户]) -->|提问| N9
    F6[外部程序调用] -->|查询请求| N9

    N9([⑥ 检索<br/>Qdrant语义搜索]) --> N10
    N10([⑦ 回答<br/>LLM合成+溯源]) --> User

    N10 -.->|分类错误?| N_MANUAL([⑧ 手动修正<br/>改标签→重写N7])
    N_MANUAL -.-> N7[(⑤ 存储)]

    style N7 fill:#d4edda,stroke:#28a745
```

### 搜索节点定义

| 节点 | 名称 | 输入 | 输出 | 逻辑 | 对应版本 |
|:--:|------|------|------|------|:--:|
| F6 | 外部程序调用 | 下游查询请求 | 检索结果 | 绕过摄入直达 N9 | v0.7.0 |
| N9 | ⑥ 检索 | 用户查询 或 F6 调用 | 相关片段+出处 | Qdrant 语义搜索 | v0.1.0 |
| N10 | ⑦ 回答 | 检索结果+问题 | LLM合成答案+溯源 | 每个论断标注出处 | v0.1.0 |
| N_MANUAL | ⑧ 手动修正 | 用户反馈的错误分类 | 修正标签→写入 N7 | N10 答案中发现问题时纠正 | v0.4.5 |

### 搜索连线

| 起→止 | 传递内容 | 触发条件 |
|------|------|------|
| User→N9 | 查询文本 | 用户提问 |
| F6→N9 | 查询请求 | 外部程序调用 |
| N9→N10 | 相关片段+出处 | 检索完成 |
| N10→User | LLM 合成答案 | 合成完成 |
| N10→N_MANUAL | 错误分类信息 | 用户指出分类/标签不对 |
| N_MANUAL→N7 | 修正标签 | 修正完成 |

---

## 三、知识库管理

> 覆盖知识库的日常维护：去重、更新、删除、图谱。
> 对应节点：C_DUP, N_UPDATE, N_DEL, N_GRAPH, N_MANUAL

```mermaid
flowchart LR
    C_DUP{去重检测} -->|全新| N6([③ AI分类])
    C_DUP -->|相似| N_UPDATE([更新已有<br/>合并元数据])
    N_UPDATE --> N7[(⑤ 存储<br/>Qdrant)]

    N7 -->|主动清理| N_DEL([⑨ 删除/归档<br/>软删除标记])
    N7 -->|按需构建| N_GRAPH([⑩ 知识图谱<br/>NetworkX])
    N_MANUAL([⑧ 手动修正]) --> N7

    style N7 fill:#d4edda,stroke:#28a745
    style N_DEL fill:#fff3cd,stroke:#f0ad4e
    style N_GRAPH fill:#cce5ff,stroke:#0275d8
```

### 管理节点定义

| 节点 | 名称 | 触发 | 操作 | 说明 | 对应版本 |
|:--:|------|------|------|------|:--:|
| C_DUP | 去重检测 | 每次摄入 N5 后 | 向量相似度>阈值→判重复 | 防止同内容重复入库 | v0.5.0 |
| N_UPDATE | 更新已有 | C_DUP 判重复 | 合并元数据+来源→重写向量 | 保留旧来源，追加新来源 | v0.5.0 |
| N_MANUAL | ⑧ 手动修正 | 用户从 N10 发现错误 | 修改分面标签→重写 N7 | 修复 AI 分类错误 | v0.4.5 |
| N_DEL | ⑨ 删除/归档 | 用户主动清理 | 软删除(archived)→排除检索 | 不物理删除，保留审计 | v0.5.0 |
| N_GRAPH | ⑩ 知识图谱 | N7 存储后按需触发 | relations→NetworkX→Plotly | 惰性同步: dirty标记→打开时重建 | v0.5.0 |

### 管理连线

| 起→止 | 传递内容 | 触发条件 |
|------|------|------|
| C_DUP→N_UPDATE | 新文本+旧条目ID | 相似度>阈值 |
| N_UPDATE→N7 | 合并后数据 | 更新完成 |
| N7→N_DEL | 目标条目ID | 用户清理 |
| N7→N_GRAPH | 关系数据 | 按需构建 |
| N_MANUAL→N7 | 修正标签 | 修正完成 |

---

## 四、系统保障（其它）

> 错误处理、警告提示、失败兜底。不直接参与主流程，但保证系统不静默失败。
> 对应节点：DL, W1, W2, W3

```mermaid
flowchart LR
    N2{格式识别} -->|不可识别| DL[☠ 死信队列<br/>置信度过低→JSON DLQ<br/>处理失败→inbox state:failed]
    C1{大小} -->|>50MB| W1[⚠️ 超限警告]
    C3{编码} -->|失败| W2[⚠️ chardet推测]
    N5{长度} -->|>5000字| W3[⚠️ 截断提示]

    style DL fill:#f8d7da,stroke:#dc3545
    style W1 fill:#fff3cd,stroke:#f0ad4e
    style W2 fill:#fff3cd,stroke:#f0ad4e
    style W3 fill:#fff3cd,stroke:#f0ad4e
```

### 保障节点定义

| 节点 | 名称 | 触发条件 | 处理 | 为什么这样设计 |
|:--:|------|------|------|------|
| DL | 死信队列 | N2 格式/置信度失败 | 置信度低→JSON DLQ(local_data/dead_letter/); 处理失败→inbox state:failed(file_state.jsonl) | 双 DLQ 通道：置信度（需手动修正/重传）vs 处理（在收件箱重试/删除）|
| W1 | 超限警告 | 文件>50MB | 警告但仍可继续 | 不阻止用户，但提示性能风险 |
| W2 | 编码失败 | C3 无法解码 | 标注编码失败+chardet推测 | 不丢弃内容，尽力恢复 |
| W3 | 截断提示 | 文本>5000字 | 截断+提示用户 | LLM 上下文窗口有限，MVP 阶段暂不处理长文本切分 |

### 保障连线

| 起→止 | 传递内容 | 触发条件 |
|------|------|------|
| N2→DL | 原始文件+错误信息 | 格式无法识别/置信度过低 |
| C4→DL | 低置信元数据 | 置信度<0.40 |
| C1→W1 | 原始内容+大小信息 | >50MB |
| C3→W2 | 标注信息+推测编码 | 编码检测失败 |
| N5→W3 | 截断文本+提示 | >5000字 |

---

*版本: v6 | 最后更新: 2026-06-23*

*变更记录:*
- v6: 守望 v2 — F_WATCH 改为统一收件箱(inbox/ + file_state.jsonl)；DL_WATCH/PROC 删除，替换为 INBOX_FAILED(15故障×5策略)+N_PAGES(WLNK逐页分析)+KEEP/DELETE(内容驱动保留)；新增收件箱标签页节点。
- v5: 新增 F_WATCH（守望文件夹）入口节点、DL_WATCH（守望死信）+ DL_CONF（置信度死信）双 DLQ、PROC（已处理）节点及连线。置信度路由三档化（高/中/低）。标记 N_UPDATE 未实现。新增提取异常→DL_WATCH 连线。
- v4: 按功能域拆分为四张独立子图（摄入/搜索/知识库管理/系统保障），每张自含节点定义+连线表。总览图改为文本框图。
- v2: 新增 6 个节点 — F6, C_DUP, N_UPDATE, N_MANUAL, N_DEL, N_GRAPH。
- v1: 初始版本。

*当前重心：一、摄入流程（N1→N2→提取）。*
