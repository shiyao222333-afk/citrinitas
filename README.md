<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+">
  <img src="https://img.shields.io/badge/LLM-DeepSeek-orange?style=flat-square&logo=deepseek&logoColor=white" alt="DeepSeek">
  <img src="https://img.shields.io/badge/Vector Store-Qdrant-red?style=flat-square&logo=qdrant&logoColor=white" alt="Qdrant">
  <img src="https://img.shields.io/badge/Formula-KaTeX-brightgreen?style=flat-square&logo=latex&logoColor=white" alt="KaTeX">
  <img src="https://img.shields.io/github/license/shiyao222333-afk/kb-query-engine?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/github/stars/shiyao222333-afk/kb-query-engine?style=social" alt="Stars">
</p>

<h1 align="center">📚 KB Query Engine</h1>

<p align="center">
  <b>中文技术文档知识库问答系统</b><br>
  基于 Qdrant + Ollama + LLM API · 支持引用追溯 · 公式渲染 · HTML报告
</p>

<p align="center">
  <a href="#-快速开始"><b>快速开始</b></a> ·
  <a href="#-功能特性"><b>功能特性</b></a> ·
  <a href="#-输出示例"><b>输出示例</b></a> ·
  <a href="#-常见问题"><b>常见问题</b></a> ·
  <a href="https://github.com/shiyao222333-afk/kb-query-engine/issues"><b>提Issue</b></a>
</p>

---

## 🎯 这个工具能帮你做什么？

> **场景**：你手上有大量技术文档（PDF、手册、教科书、笔记），想快速找到某个知识点的答案。

| 传统方式 ❌ | KB Query Engine ✅ |
|-----------|---------------------|
| 翻几十页手册找公式 | 直接问："齿轮的转动惯量公式是什么？" |
| 复制粘贴内容给ChatGPT | 本地运行，数据不出门 |
| 不知道答案在哪份文档 | 自动标注来源 `[引用1]` 并跳转 |
| 公式显示为乱码 | KaTeX 渲染，打开即用 |
| 想打印/分享结果 | 一键生成HTML报告（支持打印/PDF） |

**核心价值**：
- 📖 **引用可追溯**：每个答案标注来源，点击跳转原文
- 🔒 **本地优先**：支持纯本地运行（Ollama + Qdrant），数据不出门
- 📐 **公式完美渲染**：KaTeX 服务端渲染，无JS闪烁
- 📊 **表格智能拆分**：大表格按行拆分引用，避免引用范围过大
- 📝 **补充内容标注**：LLM使用非知识库内容时标注 `[补充]`

---

## ✨ 功能特性

- **OCR 摄入**：PaddleOCR / PPStructureV3（公式+表格+图表结构化识别）
- **向量搜索**：Qdrant + qwen3-embedding:4b（2560维）
- **LLM 合成**：DeepSeek API（OpenAI兼容接口），支持引用标注 + `[补充]` 标记
- **引用粒度控制**：大表格按行拆分为独立引用，避免引用范围过大
- **引用重编号**：回答中实际使用的引用自动重编号为连续1~N
- **公式渲染**：KaTeX 服务端批量渲染，HTML打开即用（无JS实时计算）
- **HTML 报告**：双层结构（AI回答 + 原始素材），支持打印/PDF
- **去重过滤**：入库前SHA256去重；搜索结果同源去重 + OCR质量过滤

---

## 🏗️ 架构

```
摄入: 图片/文本 → PaddleOCR/PPStructureV3 → 分块嵌入 → Qdrant
查询: 自然语言 → 向量搜索 → LLM API 合成 → 程序渲染 HTML/PDF
```

---

## 📦 安装依赖

```bash
# Python 环境
pip install requests fpdf2 pillow

# PaddleOCR（中文 OCR）
pip install paddlepaddle paddleocr

# PPStructureV3（结构化识别，可选）
pip install "paddlex[ocr]==3.7.0"

# Ollama（嵌入模型运行环境）
# 从 https://ollama.com 安装，然后：
ollama pull qwen3-embedding:4b

# KaTeX（公式渲染，需要 Node.js）
npm install -g katex
```

---

## 🚀 快速开始

### 1. 启动服务

```bash
# 启动 Qdrant + Ollama（Windows）
.\start.bat
```

### 2. 摄入文档

```bash
# 摄入文本文件
python kb_query.py --ingest "D:/Documents/KnowledgeBase/齿轮设计基础.txt"

# OCR 图片（自动识别公式/表格）
python kb_query.py --ocr "photo.jpg" --source "手册-P3"

# OCR 后先审核再入库
python kb_query.py --ocr "photo.jpg" --check-only
```

### 3. 问答

```bash
# 端到端问答（搜索 → LLM 合成 → HTML报告）
python kb_query.py "齿轮的失效形式有哪些" --answer --llm-api-key sk-xxx

# 纯搜索（不调用 LLM）
python kb_query.py "齿轮参数表" --top 10
```

---

## ⚙️ 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `KB_LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `KB_LLM_API_KEY` | LLM API Key | （必须自行设置） |
| `KB_LLM_MODEL` | LLM 模型名 | `deepseek-chat` |

### 命令行参数

#### `--table-split-threshold N`
表格行数 > N 时按行拆分为独立引用（默认 4）。

```bash
python kb_query.py "转动惯量公式" --answer --table-split-threshold 3
```

#### `--threshold F`
搜索相关度阈值（默认 0.3）。

---

## 📊 输出格式

### HTML 报告结构

```
┌─────────────────────────────────────┐
│  📝 综合回答（AI 合成）           │
│  - 引用编号高亮 + 跳转锚点      │
│  - 公式 KaTeX 渲染             │
│  - [补充] 标记                  │
├─────────────────────────────────────┤
│  📚 原始素材（逐条展示）       │
│  - 被引用的行显示 [引用N] 标签 │
│  - 未引用的行正常展示（无标签）│
│  - 图片 base64 嵌入            │
└─────────────────────────────────────┘
```

---

## 🔍 引用系统

### 引用粒度

- **默认**：每个搜索结果块作为一条引用 `[引用1]` ~ `[引用N]`
- **大表格**：行数 > 4 时自动按行拆分，每行生成独立引用

### 引用重编号

LLM 回答中实际使用的引用编号会被重编号为连续 1~N，避免编号跳跃。

示例：
```
LLM 输出: "根据[引用5]和[引用2]，结果是[引用3]"
重编号后: "根据[引用1]和[引用2]，结果是[引用3]"
```

### `[补充]` 标记

LLM 在回答中使用非知识库内容时，需在句末标注 `[补充]`。

---

## 📐 公式支持

- **行内公式**：`$...$`（如 `$J=\frac{\pi\rho D^4}{32}$`）
- **独行公式**：`$$...$$`
- **渲染方式**：KaTeX 服务端批量渲染（HTML 打开即用，无闪烁）

---

## 📋 文件结构

```
kb_query.py        主程序（OCR/搜索/合成/报告）
render_math.js      Node.js 脚本（KaTeX 渲染）
start.bat          Windows 启动脚本（Qdrant + Ollama）
.gitignore          排除本地数据/日志
```

---

## 🔧 依赖版本

| 依赖 | 版本 |
|---|---|
| Python | 3.13+ |
| requests | 2.31+ |
| fpdf2 | 2.8+ |
| PaddleOCR | 3.7+ |
| Ollama | 0.7+ |
| qwen3-embedding | 4b（2560维）|
| Node.js | 22+ |
| KaTeX | 0.16+ |

---

## 📝 版本管理

### 当前版本

`v0.1.0` - 初始版本

### 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| `v0.1.0` | 2026-06-14 | 初始版本，核心功能完成 |

### 版本更新日志

见 [CHANGELOG.md](CHANGELOG.md)（待创建）

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 提交 Issue

- 🐛 **Bug报告**：描述复现步骤、期望行为、实际行为
- 💡 **功能请求**：描述使用场景、期望功能

### 提交 Pull Request

1. Fork 本仓库
2. 创建分支 (`git checkout -b feature/xxx`)
3. 提交改动 (`git commit -m "feat: xxx"`)
4. 推送分支 (`git push origin feature/xxx`)
5. 提交 Pull Request

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- [Qdrant](https://github.com/qdrant/qdrant) - 向量数据库
- [Ollama](https://github.com/ollama/ollama) - 本地LLM运行环境
- [KaTeX](https://github.com/KaTeX/KaTeX) - 公式渲染
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - 中文OCR

---

## 📧 联系我

- GitHub Issues: [提交Issue](https://github.com/shiyao222333-afk/kb-query-engine/issues)
- Email: （待补充）

---

<p align="center">
  ⭐ 如果这个项目对你有帮助，请给一个 Star！
</p>
