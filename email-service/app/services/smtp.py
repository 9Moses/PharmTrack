"""
app/services/smtp.py — Email Service
Async SMTP sender using aiosmtplib.
"""
import logging
import asyncio
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib
from core.config import settings

logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str = "",
) -> None:
    """Send an HTML email via SMTP (async)."""
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{settings.app_name} <{settings.smtp_mail}>"
    message["To"] = to

    if text_body:
        message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_mail,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_ssl,
        )
        logger.info("[SMTP] Email sent to %s | Subject: %s", to, subject)
    except Exception as exc:
        logger.error("[SMTP] Failed to send email to %s: %s", to, exc)
        raise


def send_email_sync(to: str, subject: str, html_body: str, text_body: str = "") -> None:
    """Synchronous wrapper — used by the pika consumer thread."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(send_email(to, subject, html_body, text_body))
    finally:
        loop.close()
