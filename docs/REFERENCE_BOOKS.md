# Athanor 参考书目追踪

记录所有在设计与开发过程中发现的参考书籍。待知识库建成后可批量摄入。

格式：书名 | 作者 | 相关章节 | 对 Athanor 的价值 | AI推荐理由 | 摄入状态

---

| # | 书名 | 作者 | 相关章节 | 价值说明 | AI推荐理由 | 状态 |
|---|------|------|---------|---------|----------|:--:|
| 1 | 《Building a Second Brain》(打造第二大脑) | Tiago Forte | CODE 方法 (Capture/Organize/Distill/Express) | 直接对应摄入管线设计哲学——Capture 不是"什么都存"，是有意图的收集。PARA 方法用于组织分类。 | 搜索"知识管理 摄入管道 参考书"时发现，多个来源一致推荐。GitHub上大量 Second Brain 实现参考此书。 | ⏳ |
| 2 | 《How to Take Smart Notes》(卡片笔记写作法) | Sönke Ahrens | 第3-4章：Note-taking as a process；Zettelkasten 方法 | 核心思想"捕获时必须判断是否值得进入系统"，直接指导审核队列的"准入门槛"设计。 | 搜索 PKM 书籍时发现，是 Zettelkasten 方法的权威著作。多个 PKM 工具（Obsidian/Logseq）均受此书影响。 | ⏳ |
| 3 | 《Designing Data-Intensive Applications》(设计数据密集型应用) | Martin Kleppmann | 第11章：Stream Processing；第5章：Replication | 管道架构/消息队列/Dead Letter Queue 的标准参考。Athanor 摄入管线是典型的 stream processing 场景。 | 搜索"async queue pattern"时发现，系统设计领域权威参考。Dead Letter Queue 模式直接取自此书。 | ⏳ |
| 4 | 《Data Engineering with Python》 | Paul Crickard | 第4-5章：Building data pipelines | 实际代码层面的摄入管线设计模式，Python 实现案例。 | 搜索"ingestion pipeline Python book"时发现。 | ⏳ |

---

## 状态说明

- ⏳ 待获取/待摄入
- 📥 已有文件，待摄入 Athanor
- ✅ 已摄入 Athanor 知识库

## 备注

- 此文件在 2026-06-15 创建，作为 Athanor 智能摄入模块设计阶段的研究产出
- 未来发现新参考书时，AI 应自动追加到本文件
