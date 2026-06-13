# KnowledgeForge 操作逻辑流程图

> 本文档包含项目的完整操作逻辑流程图，使用 Mermaid 格式，GitHub 原生支持渲染。

---

## 一、总体架构图

```mermaid
graph TB
    subgraph 用户层
        U[用户]
    end

    subgraph 摄入层
        T[文本文件摄入]
        O[图片OCR摄入]
        IMA[IMA知识库同步]
    end

    subgraph 处理层
        OCR[PaddleOCR / PPStructureV3]
        CHUNK[语义分块]
        EMBED[Ollama 向量化]
        DEDUP[SHA256去重]
    end

    subgraph 存储层
        QD[Qdrant 向量库]
        FS[本地文件 local_data/]
    end

    subgraph 查询层
        Q[用户提问]
        VEC[向量搜索]
        LLM[LLM 合成回答]
        RENUM[引用重编号]
        HTML[HTML报告生成]
    end

    U --> T
    U --> O
    U --> Q
    IMA --> T

    T --> CHUNK
    O --> OCR
    OCR --> CHUNK
    CHUNK --> DEDUP
    DEDUP --> EMBED
    EMBED --> QD
    OCR --> FS
    T --> FS

    Q --> VEC
    VEC --> QD
    VEC --> LLM
    LLM --> RENUM
    RENUM --> HTML
    HTML --> U
```

---

## 二、文档摄入流程

```mermaid
flowchart TD
    START([开始摄入]) --> INPUT{输入类型?}
    INPUT -->|文本文件| TEXT[读取文本文件]
    INPUT -->|图片文件| IMG[图片OCR]
    INPUT -->|IMA知识库| IMA[从IMA拉取内容]

    IMG --> PADDLE{PaddleOCR}
    PADDLE --> STRUCT[PPStructureV3<br>表格/公式识别]
    STRUCT --> LATEX[公式 → LaTeX]
    STRUCT --> TABLE[表格 → HTML]

    TEXT --> CHUNK[语义分块]
    LATEX --> CHUNK
    TABLE --> CHUNK
    IMA --> CHUNK

    CHUNK --> DEDUP{SHA256去重}
    DEDUP -->|已存在| SKIP[跳过]
    DEDUP -->|新内容| EMBED[Ollama 向量化]

    EMBED --> QD[(存入 Qdrant)]
    CHUNK --> SAVE[保存原文到 local_data/]

    SKIP --> END([结束])
    QD --> END
    SAVE --> END
```

---

## 三、查询与回答生成流程

```mermaid
flowchart TD
    Q([用户提问]) --> EMBED_Q[问题向量化<br>Ollama Embedding]

    EMBED_Q --> SEARCH[Qdrant 向量搜索]

    SEARCH --> FILTER[同源去重 +<br>OCR质量过滤]

    FILTER --> EXPAND{表格行数 ><br>拆分阈值?}

    EXPAND -->|是| SPLIT[按行拆分表格<br>生成虚拟chunk]
    EXPAND -->|否| KEEP[保持原chunk]

    SPLIT --> TOPK[取 top-K 个chunk]
    KEEP --> TOPK

    TOPK --> PROMPT[构建 Synthesis Prompt<br>注入 chunk 原文]

    PROMPT --> LLM([LLM API 调用])

    LLM --> PARSE[解析回答<br>提取引用编号]

    PARSE --> RENUM[引用重编号<br>映射为连续 1~M]

    RENUM --> HTML[生成 HTML 报告]

    HTML --> DETAILS[&lt;details&gt; 展示原始素材]
    HTML --> ANSWER[展示 AI 回答]

    ANSWER --> END([返回用户])
    DETAILS --> END
```

---

## 四、引用粒度优化流程（表格行拆分）

```mermaid
flowchart LR
    subgraph 拆分前
        C1[Chunk 1: 普通文本]
        C2[Chunk 2: 表格 20行]
        C3[Chunk 3: 普通文本]
    end

    subgraph 拆分后
        C1A[Chunk 1: 普通文本]
        R1[Chunk 2-1: 表格第1行]
        R2[Chunk 2-2: 表格第2行]
        R3[Chunk 2-3: 表格第3行]
        RN[...]
        C3A[Chunk 3: 普通文本]
    end

    C2 -->|行数>阈值| R1
    C2 --> R2
    C2 --> R3
    C2 --> RN
```

---

## 五、引用重编号逻辑

```mermaid
flowchart TD
    LLM_OUT[LLM原始输出<br>参考答案2、4、5] --> EXTRACT[正则提取<br>所有引用编号]

    EXTRACT --> NUMS[得到: 2, 4, 5]

    NUMS --> MAP[建立映射表<br>2→1, 4→2, 5→3]

    MAP --> REPLACE[替换回答中的<br>引用编号]

    REPLACE --> FINAL[最终输出<br>参考答案1、2、3]
```

---

## 六、IMA 知识库同步流程

```mermaid
flowchart TD
    START([sync_ima.py 启动]) --> AUTH[IMA MCP 鉴权]

    AUTH --> LIST[获取知识库列表<br>get_knowledge_base_list]

    LIST --> LOOP[遍历知识库]

    LOOP --> SEARCH[搜索知识条目<br>search_knowledge]

    SEARCH --> FETCH[获取条目内容<br>fetch_media_content]

    FETCH --> TYPE{内容类型?}

    TYPE -->|WORD/PDF/TXT| TEXT[提取纯文本]
    TYPE -->|WEB/Markdown| MD[提取 Markdown]
    TYPE -->|IMG| OCR[OCR识别图片]

    TEXT --> CONVERT[转换为 kb_query 格式]
    MD --> CONVERT
    OCR --> CONVERT

    CONVERT --> INGEST[调用 kb_query.py<br>--ingest 摄入]

    INGEST --> NEXT{还有更多?}
    NEXT -->|是| LOOP
    NEXT -->|否| DONE([同步完成])
```

---

## 七、HTML 报告结构

```mermaid
graph TD
    REPORT[query_result.html]

    REPORT --> HEADER[页面头部<br>标题 + 查询时间]

    HEADER --> ANSWER[AI 回答区域]
    ANSWER --> CITE[引用标注<br>可点击跳转]

    HEADER --> DETAILS[&lt;details&gt; 原始素材]

    DETAILS --> CHUNK1[引用1: 来源A]
    DETAILS --> CHUNK2[引用2: 来源B]
    DETAILS --> CHUNKN[引用N: ...]

    CHUNK1 --> MATH[公式: KaTeX 渲染]
    CHUNK1 --> TABLE[表格: HTML Table]
    CHUNK1 --> TEXT[纯文本]
```

---

## 八、错误处理与重试逻辑

```mermaid
flowchart TD
    OP[执行操作] --> CHECK{成功?}
    CHECK -->|是| OK[继续]
    CHECK -->|否| ERR{错误类型?}

    ERR -->|网络超时| RETRY[等待后重试<br>最多3次]
    ERR -->|API KEY无效| ABORT[终止并报错]
    ERR -->|OCR失败| SKIP[跳过该文件<br>记录日志]
    ERR -->|Qdrant未启动| WAIT[等待服务启动<br>或提示用户]

    RETRY --> OP
    WAIT --> OP
    SKIP --> NEXT[处理下一个]
```

---

## 九、项目文件结构

```mermaid
graph TD
    ROOT[knowledge-forge/]

    ROOT --> KB[kb_query.py<br>主程序]

    ROOT --> START[start.bat / stop.bat<br>启动/停止脚本]

    ROOT --> DATA[local_data/<br>OCR结果存档]
    ROOT --> QR[qdrant_data/<br>Qdrant数据库]

    ROOT --> DOCS[文档]
    DOCS --> README[README.md]
    DOCS --> HISTORY[DEVELOPMENT_HISTORY.md]
    DOCS --> CONTRIB[CONTRIBUTING.md]

    ROOT --> SYNC[sync_ima.py<br>IMA同步脚本]
    ROOT --> FLOW[FLOW_DIAGRAM.md<br>本文件]
```

---

## 十、序列图：一次完整问答

```mermaid
sequenceDiagram
    participant U as 用户
    participant CLI as kb_query.py
    participant EMB as Ollama Embedding
    participant QD as Qdrant
    participant LLM as LLM API
    participant HTML as HTML报告

    U->>CLI: python kb_query.py "问题" --answer
    CLI->>EMB: 向量化问题
    EMB-->>CLI: 问题向量
    CLI->>QD: 向量相似度搜索 top-K
    QD-->>CLI: K个相关chunk
    CLI->>CLI: 表格行拆分（如需要）
    CLI->>LLM: 发送 chunk + 问题
    LLM-->>CLI: 带引用标注的回答
    CLI->>CLI: 引用重编号
    CLI->>HTML: 生成 HTML 报告
    HTML-->>U: 打开 query_result.html
```
