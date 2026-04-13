"""
邮件推送（SMTP）。
优先发送 HTML 格式（支持可视化排版），回退到纯文本。
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from app.config import ChannelConfig
from app.models import Digest

from .base import _render_for_plain_text


class EmailSender:
    channel_type = "email"

    def send(
        self,
        digest: Digest,
        channel: ChannelConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        if channel.type != "email":
            raise ValueError("EmailSender only supports channel.type='email'")
        smtp_host = channel.smtp_host
        smtp_port: int = channel.smtp_port or 587
        smtp_user = channel.smtp_user
        smtp_password = channel.smtp_password
        to_addr = channel.to
        use_tls = channel.use_tls

        if not smtp_host or not to_addr:
            raise ValueError("email channel missing smtp_host or to")

        from_addr = smtp_user or to_addr
        subject = digest.title or "Daily Digest"

        html_body = digest.rendered.html
        text_body = _render_for_plain_text(digest)

        if html_body:
            # 发送 multipart/alternative：邮件客户端优先显示 HTML
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_addr
            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(text_body, _subtype="plain", _charset="utf-8")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = to_addr

        use_ssl = channel.use_ssl
        if use_ssl:
            # 465 端口：直接 SSL 连接
            with smtplib.SMTP_SSL(smtp_host, smtp_port or 465, timeout=30) as smtp:
                smtp.ehlo()
                if smtp_user and smtp_password:
                    smtp.login(smtp_user, smtp_password)
                smtp.sendmail(from_addr, [to_addr], msg.as_string())
        else:
            # 587 端口：STARTTLS 升级
            with smtplib.SMTP(smtp_host, smtp_port or 587, timeout=30) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                if smtp_user and smtp_password:
                    smtp.login(smtp_user, smtp_password)
                smtp.sendmail(from_addr, [to_addr], msg.as_string())
