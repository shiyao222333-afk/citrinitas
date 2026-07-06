"""
外部告警推送 — Citrinitas v1.1.0

支持：
  1. Server酱（方糖推送）— https://sct.ftqq.com
  2. 邮件通知（SMTP）— 兜底方案

配置（在 .env 或 pipe_cfg.yaml 里设置）：
  SVR_SEND_KEY  — Server酱 SendKey（免费版）
  SMTP_HOST / SMTP_USER / SMTP_PASS — 邮件配置（可选）

用法：
  from utils.alerts import send_alert

  send_alert("E900", "Qdrant 离线！请检查 Docker。")
  # 非阻塞，失败不抛异常
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Server酱 配置 ────────────────────────────────────────────────────────────────
SVR_SEND_KEY = os.environ.get("SVR_SEND_KEY", "")
SVR_API_URL = f"https://sct.ftqq.com/{SVR_SEND_KEY}.send" if SVR_SEND_KEY else ""

# ── 邮件配置 ────────────────────────────────────────────────────────────────────
SMTP_HOST = os.environ.get("KB_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("KB_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("KB_SMTP_USER", "")
SMTP_PASS = os.environ.get("KB_SMTP_PASS", "")
ALERT_EMAIL_TO = os.environ.get("KB_ALERT_EMAIL", "")


def send_alert(error_code: str, message: str, level: str = "CRITICAL") -> bool:
    """
    发送告警（非阻塞，失败不抛异常）。

    参数：
        error_code: 错误码（如 E900）
        message:    告警内容
        level:      级别（CRITICAL / ERROR / WARNING）

    返回：
        True  = 发送成功（或不需要发送）
        False = 发送失败
    """
    # 只推送 CRITICAL 和 ERROR 级别
    if level not in ("CRITICAL", "ERROR"):
        return True

    subject = f"[Citrinitas] {error_code} - {level}"
    body = (
        f"## Citrinitas 告警\n\n"
        f"- **错误码**: {error_code}\n"
        f"- **级别**: {level}\n"
        f"- **时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- **内容**:\n\n{message}\n"
    )

    success = False

    # 优先用 Server酱
    if SVR_SEND_KEY:
        success = _send_svr(subject, body)

    # Server酱失败或没配置，尝试邮件
    if not success and SMTP_HOST:
        success = _send_email(subject, body)

    if not success:
        logger.warning(f"告警发送失败（所有渠道）：code={error_code}")

    return success


def _send_svr(subject: str, body: str) -> bool:
    """
    通过 Server酱 发送推送（免费版，每天5次限制）。
    """
    try:
        import requests
        resp = requests.post(
            SVR_API_URL,
            data={"title": subject, "desp": body},
            timeout=5,
        )
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 0:
                logger.info(f"Server酱推送成功: {subject}")
                return True
            else:
                logger.warning(f"Server酱推送失败: {result}")
        else:
            logger.warning(f"Server酱推送 HTTP 错误: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Server酱推送异常: {e}")
    return False


def _send_email(subject: str, body: str) -> bool:
    """
    通过 SMTP 发送邮件（兜底方案）。
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL_TO

        msg.attach(MIMEText(body, "markdown" if ALERT_EMAIL_TO.endswith("@qq.com") else "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        logger.info(f"邮件告警发送成功: {subject}")
        return True
    except Exception as e:
        logger.warning(f"邮件告警发送失败: {e}")
    return False


def test_alert() -> str:
    """
    测试告警配置（在 UI 里调用，返回配置状态）。
    """
    status = []
    if SVR_SEND_KEY:
        status.append(f"✅ Server酱已配置（SendKey: {SVR_SEND_KEY[:8]}...）")
        # 发一条测试推送
        ok = send_alert("E999", "这是一条测试告警（Citrinitas v1.1.0）", level="ERROR")
        status.append(f"   测试推送: {'✅ 成功' if ok else '❌ 失败'}")
    else:
        status.append("❌ Server酱未配置（请设置 SVR_SEND_KEY 环境变量）")

    if SMTP_HOST:
        status.append(f"✅ 邮件已配置（SMTP: {SMTP_HOST}）")
    else:
        status.append("⚠️ 邮件未配置（可选）")

    return "\n".join(status)
