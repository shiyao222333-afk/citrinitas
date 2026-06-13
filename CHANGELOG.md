# Changelog

本文档记录 KB Query Engine 的所有 notable changes。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Added
- 待添加功能

### Fixed
- 待修复问题

### Changed
- 待变更内容

---

## [v0.1.0] - 2026-06-14

### Added
- ✨ OCR 摄入功能（PaddleOCR / PPStructureV3）
- ✨ 向量搜索（Qdrant + qwen3-embedding:4b）
- ✨ LLM 合成（DeepSeek API）+ 引用标注
- ✨ 表格行拆分（引用粒度控制）
- ✨ 引用重编号（连续不跳跃）
- ✨ KaTeX 服务端公式渲染
- ✨ HTML 报告生成（双层结构）
- ✨ `[补充]` 标记（非知识库内容标注）
- ✨ 去重过滤（SHA256 + 同源去重 + OCR质量过滤）

### Fixed
- 无（初始版本）

### Changed
- 无（初始版本）

---

## 版本说明

| 标签 | 含义 |
|------|------|
| `Added` | 新功能 |
| `Fixed` | Bug 修复 |
| `Changed` | 功能变更 |
| `Deprecated` | 即将移除的功能 |
| `Removed` | 已移除的功能 |
| `Security` | 安全问题 |
