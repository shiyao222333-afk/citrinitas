"""
统一日志配置 — Citrinitas v1.1.0

日志输出位置：
  - 控制台（开发时可见）
  - local_data/logs/citrinitas_YYYYMMDD.log（按天轮转，保留30天）

日志格式：
  [2026-07-06 12:00:00] [ERROR] [E001] [ingest_service] 文件读取失败: path=..., reason=...

用法：
  from utils.logging_config import setup_logging
  setup_logging()  # 在 main.py 启动时调用一次
"""
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from utils.error_codes import format_error, ErrorCode


# ── 日志目录 ────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "local_data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE_PREFIX = "citrinitas"
LOG_LEVEL = os.environ.get("KB_LOG_LEVEL", "INFO").upper()


def _build_formatter() -> logging.Formatter:
    """
    日志格式：
      [2026-07-06 12:00:00.123] [LEVEL] [E001] [module] message
    """
    fmt = (
        "[%(asctime)s.%(msecs)03d] "
        "[%(levelname)-8s] "
        "[%(name)s] "
        "%(message)s"
    )
    return logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")


def setup_logging(level: str = None) -> None:
    """
    初始化全局日志配置。在 main.py 启动时调用一次。

    参数：
        level: 日志级别（DEBUG / INFO / WARNING / ERROR / CRITICAL）
              默认读 KB_LOG_LEVEL 环境变量，否则 INFO
    """
    log_level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)
    formatter = _build_formatter()

    # ── 根 logger 配置 ─────────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(log_level)

    # 清除已有 handler（避免重复添加）
    root.handlers.clear()

    # ── 控制台 handler ─────────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # ── 文件 handler（按天轮转，保留30天）───────────────────────────────────
    log_file = os.path.join(LOG_DIR, f"{LOG_FILE_PREFIX}.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"  # 轮转文件名：citrinitas.log.2026-07-06
    root.addHandler(file_handler)

    # ── 屏蔽第三方库多余日志 ─────────────────────────────────────────────────
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("ollama").setLevel(logging.WARNING)
    logging.getLogger("qdrant_client").setLevel(logging.WARNING)
    logging.getLogger("nicegui").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)

    root.info("Logging initialized: level=%s, file=%s", log_level, log_file)


def get_logger(name: str) -> logging.Logger:
    """
    获取带名字的 logger。各模块统一用这个，不用自己调 logging.getLogger。
    """
    return logging.getLogger(name)


# ── 便捷函数：带错误码的日志 ──────────────────────────────────────────────────
def log_error(logger: logging.Logger, code: ErrorCode, **kwargs):
    """记录 ERROR 级别日志，带错误码。"""
    logger.error(format_error(code, **kwargs))


def log_warning(logger: logging.Logger, code: ErrorCode, **kwargs):
    """记录 WARNING 级别日志，带错误码。"""
    logger.warning(format_error(code, **kwargs))


def log_info(logger: logging.Logger, code: ErrorCode, **kwargs):
    """记录 INFO 级别日志，带错误码。"""
    logger.info(format_error(code, **kwargs))


def log_debug(logger: logging.Logger, code: ErrorCode, **kwargs):
    """记录 DEBUG 级别日志，带错误码。"""
    logger.debug(format_error(code, **kwargs))


def log_critical(logger: logging.Logger, code: ErrorCode, **kwargs):
    """记录 CRITICAL 级别日志，带错误码。触发 Server酱 推送。"""
    msg = format_error(code, **kwargs)
    logger.critical(msg)
    # 触发外部告警（异步，不阻塞主流程）
    try:
        from utils.alerts import send_alert
        send_alert(code.code, msg)
    except Exception:
        logger.warning("Alert send failed (non-critical)")
