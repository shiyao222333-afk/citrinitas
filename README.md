<p align="center">
  <a href="https://github.com/shiyao222333-afk/knowledge-forge"><img src="https://img.shields.io/badge/Python-3.13+-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.13+"></a>
  <img src="https://img.shields.io/badge/Status-Active-green?style=flat-square" alt="Active">
  <img src="https://img.shields.io/badge/Stage-MVP-orange?style=flat-square" alt="MVP">
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/blob/main/LICENSE"><img src="https://img.shields.io/github/license/shiyao222333-afk/knowledge-forge?style=flat-square" alt="MIT License"></a>
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/stargazers"><img src="https://img.shields.io/github/stars/shiyao222333-afk/knowledge-forge?style=social" alt="Stars"></a>
</p>

<p align="center">
  <img src="https://api.star-history.com/svg?repos=shiyao222333-afk/knowledge-forge&type=Date&width=600&height=200" alt="Star History Chart">
</p>

<h1 align="center">🔥 KnowledgeForge / 知炬</h1>

<p align="center">
  <b>个人知识库管理系统</b><br>
  把截图、手册、笔记丢进去，问一个问题，直接得到<strong>带来源引用的答案</strong>。<br>
  数据全在本地，不联网也能用。
</p>

<p align="center">
  <a href="#-5秒快速体验"><b>⚡ 5秒体验</b></a> ·
  <a href="#-适合谁用"><b>👤 适合谁用</b></a> ·
  <a href="#-核心特性"><b>✨ 核心特性</b></a> ·
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/blob/main/flow_diagram.md"><b>📊 流程图</b></a> ·
  <a href="https://github.com/shiyao222333-afk/knowledge-forge/issues"><b>🐛 提 Issue</b></a> ·
  <a href="#-路线图"><b>🗺️ 路线图</b></a>
</p>

---

## ⚡ 5秒快速体验

```bash
# 1. 克隆项目
git clone https://github.com/shiyao222333-afk/knowledge-forge.git
cd knowledge-forge

# 2. 安装依赖（首次）
pip install requests fpdf2 pillow paddlepaddle paddleocr

# 3. 启动服务
.\start.bat   # Windows：启动 Qdrant + Ollama

# 4. 摄入一份资料试试
python kb_query.py --ingest "README.md"

# 5. 提问！
python kb_query.py "KnowledgeForge 是什么" --answer
# → 打开生成的 query_result.html 查看结果
```

> 💡 需要有 LLM API Key（DeepSeek / Qwen 等均可），在命令行加上 `--llm-api-key sk-xxx` 即可。

---

## 📸 效果预览

> **待补充**：运行一次 `--answer` 后，对 `query_result.html` 截图，放到 `docs/screenshot.png`，然后把下面这行取消注释。

<!-- 取消注释后生效：
<p align="center">
  <img src="docs/screenshot.png" alt="HTML报告截图" width="800">
</p>
-->

目前可以本地运行体验，效果见 [flow_diagram.md](flow_diagram.md) 中的序列图。

---

## 👤 适合谁用？

| ✅ 非常适合 | ❌ 不太适合 |
|--------------|--------------|
| 有中文技术文档/手册积累的人 | 只需要英文资料搜索的人（用英文工具更合适） |
| 截图/照片里有大量文字想搜 | 数据量极小（<10 个文件）且不需要搜索 |
| 关心数据隐私，不想上传云端 | 想要现成的 Web UI（我们还在做 v0.2） |
| 需要溯源：答案从哪来的 | 不想碰命令行的人（CLI 操作，GUI 规划中） |
| 公式/表格很多的技术文档 | |

---

## ✨ 核心特性

| 特性 | 传统知识库 ❌ | KnowledgeForge ✅ |
|------|----------|-------------------|
| **语义理解** | 关键词匹配，搜不到同义词 | AI 理解意图，语义搜索 |
| **图片识别** | 不支持，或只支持 PDF | PaddleOCR 识别截图/照片文字 |
| **表格引用** | 整张表算一个结果 | 大表格按行拆分，精确到行 |
| **引用溯源** | 只给文件名，不知道在哪 | 每个回答标注 `[引用N]`，可点击跳转 |
| **公式支持** | 无法识别公式 | PPStructureV3 识别 → KaTeX 渲染 |
| **数据隐私** | 必须上传云端 | 全本地运行，数据不出门 |
| **引用编号** | 跳跃、不连续 | 后处理重编号，永远 1、2、3... |

---

## 📊 操作流程图

完整的 Mermaid 流程图（10 张图：架构、摄入、查询、引用优化、序列图）👉  
**🔗 [点此查看 flow_diagram.md](flow_diagram.md)**

GitHub 原生渲染 Mermaid，点击上方链接即可看到全部流程图。

---

## 🚀 安装与快速开始

### 1. 安装依赖

```bash
# Python 包
pip install requests fpdf2 pillow

# PaddleOCR（中文 OCR，必需）
pip install paddlepaddle paddleocr

# PPStructureV3（结构化识别，可选但推荐）
pip install "paddlex[ocr]==3.7.0"

# Ollama（本地嵌入模型运行环境）
# 从 https://ollama.com 安装，然后拉取模型：
ollama pull qwen3-embedding:4b

# KaTeX（公式渲染，可选）
npm install -g katex
```

### 2. 启动服务

```bash
.\start.bat   # Windows：启动 Qdrant + Ollama
.\stop.bat    # 停止服务
```

### 3. 摄入你的资料

```bash
# 文本文件直接入库
python kb_query.py --ingest "D:/Documents/KnowledgeBase/齿轮设计基础.txt"

# 图片 OCR 后入库（自动识别公式/表格）
python kb_query.py --ocr "photo.jpg" --source "齿轮手册-P23"

# OCR 后先预览再决定是否入库
python kb_query.py --ocr "photo.jpg" --check-only
```

### 4. 提问！

```bash
# 端到端问答（搜索 → LLM 合成 → HTML 报告）
python kb_query.py "模数 2.5 的齿轮外径是多少" --answer --llm-api-key sk-xxx

# 纯搜索（不调用 LLM，只查看相关素材）
python kb_query.py "齿轮参数表" --top 10
```

### 5. 从 IMA 知识库同步（可选）

```bash
# 从已导出的 IMA 文件目录同步
python sync_ima.py --import-dir D:\ima_exports\
```

---

## ⚙️ 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `KB_LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `KB_LLM_API_KEY` | LLM API Key | **（必须自行设置）** |
| `KB_LLM_MODEL` | LLM 模型名 | `deepseek-chat` |

### 常用参数

```bash
# 表格行数 > 4 时按行拆分引用（可调整）
python kb_query.py "转动惯量公式" --answer --table-split-threshold 3

# 搜索相关度阈值（默认 0.3，越高越严格）
python kb_query.py "查询词" --threshold 0.5

# 限制送入 LLM 的 chunk 数量（避免超 context）
python kb_query.py "查询词" --answer --max-chunks 8
```

---

## 🧭 项目愿景

我们把知识库管理系统的发展分为三个阶段：

```
阶段一（当前 v0.1）：个人知识库工具
  → 摄入、搜索、问答、引用标注、OCR、公式渲染

阶段二（规划中 v0.2~v0.3）：知识图谱 + 多模态
  → 自动建立知识点关联、图表理解、手写笔记 OCR

阶段三（更远未来 v0.4~v0.5）：完全本地智能
  → 本地 LLM、CAD 插件联动、团队协作知识库
```

**最终目标**：一个完全属于你自己的、会成长的、本地运行的知识大脑。

---

## 🗺️ 路线图

### v0.2 — 知识库管理面板
- [ ] Web UI：上传/删除/预览知识库中的文档
- [ ] 知识库统计：文档数量、覆盖主题、存储占用
- [ ] 批量摄入：拖拽上传整个文件夹

### v0.3 — 知识图谱雏形
- [ ] 自动提取文档中的实体（公式、参数、概念）
- [ ] 建立知识点之间的关联关系
- [ ] 问答时展示相关知识网络

### v0.4 — 多模态理解
- [ ] 图表理解：识别图中的曲线、趋势、标注
- [ ] 手写笔记 OCR 优化
- [ ] 视频帧提取 + 关键帧入库

### v0.5 — 知识库自进化
- [ ] 用户纠错反馈 → 自动优化入库质量
- [ ] 定期重新嵌入（模型升级时）
- [ ] 知识库版本管理（快照/回滚）

---

## 🏗️ 架构概览

```
KnowledgeForge（分层架构）

┌─────────────────────────────────────────────┐
│  用户层：CLI / Web UI（规划中）           │
├─────────────────────────────────────────────┤
│  服务层：问答合成 · 引用管理 · 报告生成 │
├─────────────────────────────────────────────┤
│  核心层：向量检索 · OCR · 嵌入           │
├─────────────────────────────────────────────┤
│  存储层：Qdrant（向量）· 文件系统       │
└─────────────────────────────────────────────┘
```

**技术栈**：
- 向量数据库：[Qdrant](https://github.com/qdrant/qdrant)
- 嵌入模型：[Ollama](https://github.com/ollama/ollama) + `qwen3-embedding:4b`
- OCR 引擎：[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) / PPStructureV3
- LLM 合成：OpenAI 兼容 API（默认 DeepSeek）
- 公式渲染：[KaTeX](https://github.com/KaTeX/KaTeX)

---

## 🤝 贡献指南

欢迎参与！这个项目处于早期阶段，每一份贡献都能显著影响方向。

### 你可以怎么参与

- 🐛 **报告 Bug**：[提交 Issue](https://github.com/shiyao222333-afk/knowledge-forge/issues/new?template=bug_report.yml)
- 💡 **提议新功能**：[功能请求](https://github.com/shiyao222333-afk/knowledge-forge/issues/new?template=feature_request.yml)
- 💻 **提交代码**：Fork → 分支 → PR
- 📖 **完善文档**：路线图、使用案例、最佳实践

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## ❓ FAQ

**Q：支持英文文档吗？**
A：支持。Ollama 的 `qwen3-embedding:4b` 对中英文都有效果，但中文优化更好。英文场景建议换用 `nomic-embed-text` 嵌入模型。

**Q：能处理多少 GB 的数据？**
A：理论上无上限，但受限于硬件。Qdrant 支持磁盘存储，可以存大量向量。建议先从小批量（几十个文件）开始测试。

**Q：和 Obsidian / Notion 有什么区别？**
A：Obsidian 是笔记管理，Notion 是在线协作。KnowledgeForge 专注**非结构化资料**（截图、扫描件、PDF）的**语义搜索和问答**，尤其是中文技术文档场景。

**Q：需要联网吗？**
A：摄入和搜索不需要联网。只有调用 LLM 合成回答时需要联网（可以切换为本地 LLM 来完全离线）。

**Q：表格拆分功能会拆分所有表格吗？**
A：不会。只有表格行数超过阈值（默认 4 行）时才会拆分。小表格保持原样。

**Q：OCR 识别不准怎么办？**
A：可以用 `--check-only` 参数先预览识别结果，不满意可以不入库。也可以手动编辑 `local_data/` 下的识别结果文件。

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- [Qdrant](https://github.com/qdrant/qdrant) - 向量数据库
- [Ollama](https://github.com/ollama/ollama) - 本地 LLM 运行环境
- [KaTeX](https://github.com/KaTeX/KaTeX) - 公式渲染
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - 中文 OCR

---

<p align="center">
  ⭐ 如果这个方向对你有启发，请给一个 Star！<br>
  🗂️ 让每个人的知识积累，都变成真正的资产。
</p>
