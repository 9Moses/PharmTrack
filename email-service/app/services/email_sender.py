"""
app/services/email_sender.py — Email Service
Async SMTP sender backed by aiosmtplib.
Supports plain text and HTML emails.
"""
import logging
import ssl
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import settings

logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> bool:
    """
    Send an email asynchronously.
    Returns True on success, False on failure (logs the error).
    """
    message = MIMEMultipart("alternative")
    message["From"] = f"{settings.default_from_name} <{settings.default_from_email}>"
    message["To"] = to
    message["Subject"] = subject

    message.attach(MIMEText(text_body, "plain"))
    if html_body:
        message.attach(MIMEText(html_body, "html"))

    try:
        if settings.smtp_use_ssl:
            ssl_context = ssl.create_default_context()
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                use_tls=True,
                tls_context=ssl_context,
            )
        else:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
        logger.info("[Email Service] Sent '%s' to %s", subject, to)
        return True
    except Exception as exc:
        logger.error("[Email Service] Failed to send '%s' to %s: %s", subject, to, exc)
        return False
