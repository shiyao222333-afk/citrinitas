# 贡献指南

感谢你考虑为 KB Query Engine 做出贡献！

---

## 🌟 如何贡献

### 报告 Bug

如果你发现了 Bug，请：

1. **搜索现有 Issue**：确认没有重复报告
2. **创建新 Issue**：使用 [Bug 报告模板](https://github.com/shiyao222333-afk/kb-query-engine/issues/new?template=bug_report.yml)
3. **提供详细信息**：版本号、操作系统、复现步骤、错误信息

### 建议新功能

如果你有新功能建议，请：

1. **搜索现有 Issue**：确认没有重复建议
2. **创建新 Issue**：使用 [功能请求模板](https://github.com/shiyao222333-afk/kb-query-engine/issues/new?template=feature_request.yml)
3. **描述使用场景**：说明这个功能想解决什么问题

### 提交代码

#### 开发流程

1. **Fork 本仓库**
2. **创建分支**：
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **编写代码**：遵循代码规范
4. **测试**：确保功能正常
5. **提交改动**：
   ```bash
   git add .
   git commit -m "feat: 添加新功能"
   ```
6. **推送分支**：
   ```bash
   git push origin feature/your-feature-name
   ```
7. **创建 Pull Request**

#### Commit 信息规范

推荐使用 [Conventional Commits](https://www.conventionalcommits.org/zh-Hans/)：

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `refactor` | 代码重构 |
| `test` | 添加测试 |
| `chore` | 构建/工具链变更 |

示例：
```
feat: 添加 PDF 导出功能
fix: 修复引用重编号逻辑错误
docs: 更新 README 安装指南
```

#### 代码规范

- **Python**：遵循 PEP 8
- **注释**：关键逻辑添加中文注释
- **命名**：变量/函数名使用小写+下划线（snake_case）
- **测试**：新功能包含测试用例

---

## 🚧 开发环境搭建

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/你的用户名/kb-query-engine.git
cd kb-query-engine

# 2. 安装依赖
pip install requests fpdf2 pillow
pip install paddlepaddle paddleocr

# 3. 安装 KaTeX
npm install -g katex

# 4. 启动 Qdrant + Ollama
.\start.bat

# 5. 运行测试
python kb_query.py "测试查询" --answer
```

---

## 📋 Pull Request 规范

### PR 标题格式

```
feat: 添加 PDF 导出功能
fix: 修复引用重编号逻辑错误
docs: 更新 README
```

### PR 描述模板

见 [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)

---

## 📧 提问

如果你有使用问题，请：

- **查看文档**：先阅读 README 和 FAQ
- **搜索 Issue**：确认没有重复问题
- **创建 Discussion**：使用 [GitHub Discussions](https://github.com/shiyao222333-afk/kb-query-engine/discussions)

---

## � 🙏 致谢

感谢所有贡献者！

---

**再次感谢你的贡献！** 🎉
