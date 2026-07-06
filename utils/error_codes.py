"""
错误码体系 — Citrinitas v1.1.0

分段规则：
  E001-E099  摄入管线（ingest）
  E100-E199  搜索与问答（search）
  E200-E299  守望文件夹（watcher）
  E300-E399  LLM 调用（llm）
  E400-E499  OCR 处理（ocr）
  E500-E599  分类管道（classify）
  E600-E699  文档管理（document）
  E900-E999  基础设施（infra）

每个错误码 = (code, level, message_template)
level: DEBUG / INFO / WARNING / ERROR / CRITICAL
"""
from enum import Enum, auto

class ErrorCode(Enum):
    """
    错误码枚举。用法：

    from utils.error_codes import ErrorCode, format_error

    try:
        ...
    except Exception as e:
        logger.error(format_error(ErrorCode.INGEST_FILE_READ, path=path, reason=str(e)))
    """
    # ── 摄入管线 E001-E099 ──────────────────────────
    INGEST_FILE_READ       = ("E001", "ERROR",   "文件读取失败: path={path}, reason={reason}")
    INGEST_FILE_TYPE      = ("E002", "WARNING", "不支持的文件类型: path={path}, type={file_type}")
    INGEST_OCR_FAIL       = ("E003", "WARNING", "OCR 处理失败: path={path}, reason={reason}")
    INGEST_EMBED_FAIL    = ("E004", "ERROR",   "向量化失败: path={path}, reason={reason}")
    INGEST_QDRANT_WRITE  = ("E005", "ERROR",   "写入 Qdrant 失败: path={path}, reason={reason}")
    INGEST_CLASSIFY_FAIL = ("E006", "WARNING", "分类失败: path={path}, reason={reason}")
    INGEST_BATCH_PARTIAL = ("E007", "WARNING", "批量摄入部分失败: success={success}, failed={failed}")
    INGEST_TIMEOUT        = ("E008", "ERROR",   "摄入超时: path={path}, timeout={timeout}s")

    # ── 搜索与问答 E100-E199 ────────────────────────
    SEARCH_QDRANT_FAIL   = ("E100", "ERROR",   "Qdrant 查询失败: query={query}, reason={reason}")
    SEARCH_NO_RESULTS    = ("E101", "INFO",    "搜索无结果: query={query}")
    SEARCH_LLM_FAIL      = ("E102", "ERROR",   "LLM 问答失败: query={query}, reason={reason}")
    SEARCH_LLM_TIMEOUT   = ("E103", "ERROR",   "LLM 问答超时: query={query}, timeout={timeout}s")
    SEARCH_FACET_FAIL   = ("E104", "WARNING", "分面统计失败: reason={reason}")

    # ── 守望文件夹 E200-E299 ─────────────────────────
    WATCHER_SCAN_FAIL    = ("E200", "WARNING", "守望扫描失败: directory={directory}, reason={reason}")
    WATCHER_PROCESS_FAIL = ("E201", "ERROR",   "守望处理失败: path={path}, reason={reason}")
    WATCHER_DLQ_FULL     = ("E202", "WARNING", "死信队列已满: size={size}, max={max}")
    WATCHER_RETRY_EXHAUST = ("E203", "ERROR", "重试耗尽: path={path}, attempts={attempts}")

    # ── LLM 调用 E300-E399 ───────────────────────────
    LLM_API_ERROR        = ("E300", "ERROR",   "LLM API 调用失败: model={model}, reason={reason}")
    LLM_API_TIMEOUT     = ("E301", "ERROR",   "LLM API 超时: model={model}, timeout={timeout}s")
    LLM_JSON_PARSE_FAIL = ("E302", "WARNING", "LLM 返回 JSON 解析失败: raw={raw[:100]}")
    LLM_RATE_LIMIT      = ("E303", "WARNING", "LLM API 限流: model={model}, wait={wait}s")

    # ── OCR 处理 E400-E499 ───────────────────────────
    OCR_ENGINE_MISSING = ("E400", "ERROR",   "OCR 引擎缺失: engine={engine}")
    OCR_IMAGE_READ_FAIL = ("E401", "WARNING", "OCR 图片读取失败: path={path}")
    OCR_NO_RESULT       = ("E402", "INFO",    "OCR 无结果: path={path}")

    # ── 分类管道 E500-E599 ────────────────────────────
    CLASSIFY_LLM_FAIL   = ("E500", "WARNING", "分类 LLM 失败: path={path}, reason={reason}")
    CLASSIFY_JSON_FAIL  = ("E501", "WARNING", "分类结果 JSON 解析失败: path={path}")
    CLASSIFY_CONFIDENCE_LOW = ("E502", "INFO", "分类置信度低: path={path}, confidence={confidence}")

    # ── 文档管理 E600-E699 ────────────────────────────
    DOC_NOT_FOUND       = ("E600", "WARNING", "文档不存在: doc_id={doc_id}")
    DOC_DELETE_FAIL    = ("E601", "ERROR",   "文档删除失败: doc_id={doc_id}, reason={reason}")
    DOC_MOVE_FAIL      = ("E602", "ERROR",   "文档移动失败: doc_id={doc_id}, reason={reason}")

    # ── 基础设施 E900-E999 ────────────────────────────
    INFRA_QDRANT_OFFLINE = ("E900", "CRITICAL", "Qdrant 离线: url={url}")
    INFRA_OLLAMA_OFFLINE = ("E901", "CRITICAL", "Ollama 离线: url={url}")
    INFRA_DISK_FULL       = ("E902", "CRITICAL", "磁盘空间不足: path={path}, free={free}MB")
    INFRA_CONFIG_MISSING  = ("E903", "ERROR",   "配置文件缺失: path={path}")
    INFRA_STARTUP_FAIL    = ("E904", "CRITICAL", "启动失败: component={component}, reason={reason}")

    @property
    def code(self):
        return self.value[0]

    @property
    def level(self):
        return self.value[1]

    @property
    def template(self):
        return self.value[2]


def format_error(code: ErrorCode, **kwargs) -> str:
    """
    格式化错误消息。用法：

        logger.error(format_error(ErrorCode.INGEST_FILE_READ, path=path, reason=str(e)))

    输出格式：
        [E001] ERROR 文件读取失败: path=..., reason=...
    """
    msg = code.template.format(**kwargs)
    return f"[{code.code}] {code.level} {msg}"


def format_error_with_traceback(code: ErrorCode, exc: Exception, **kwargs) -> str:
    """
    格式化错误消息 + traceback。用于需要记录完整堆栈的场景。
    """
    import traceback
    tb = traceback.format_exc()
    msg = format_error(code, **kwargs)
    return f"{msg}\n{tb}"
