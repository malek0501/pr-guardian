"""
Client Email — PR-Guardian Orchestrator.

Supporte deux providers :
- SMTP (Gmail, M365, etc.)
- SendGrid API

Envoie les notifications au Scrum Master ou au Développeur
selon le verdict de la revue.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from pr_guardian.config import get_settings
from pr_guardian.models import EmailPayload

logger = logging.getLogger("pr_guardian.email")


class EmailClient:
    """Client d'envoi d'emails multi-provider."""

    def __init__(self):
        self._settings = get_settings()
        if not self._settings.email_configured:
            logger.warning("Email non configuré — les notifications seront ignorées.")

    # ── Interface publique ──────────────────

    def send(self, payload: EmailPayload) -> bool:
        """Envoie un email selon le provider configuré."""
        if not self._settings.email_configured:
            logger.warning("Email non configuré, envoi ignoré.")
            return False

        try:
            if self._settings.email_provider == "sendgrid":
                return self._send_sendgrid(payload)
            else:
                return self._send_smtp(payload)
        except Exception as exc:
            logger.error(f"Échec envoi email : {exc}")
            return False

    # ── SMTP ────────────────────────────────

    def _send_smtp(self, payload: EmailPayload) -> bool:
        """Envoi via SMTP."""
        s = self._settings
        msg = MIMEMultipart("alternative")
        msg["Subject"] = payload.subject
        msg["From"] = s.email_from
        msg["To"] = ", ".join(payload.to)

        if payload.body_text:
            msg.attach(MIMEText(payload.body_text, "plain", "utf-8"))
        msg.attach(MIMEText(payload.body_html, "html", "utf-8"))

        with smtplib.SMTP(s.smtp_host, s.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(s.smtp_user, s.smtp_password)
            server.sendmail(s.email_from, payload.to, msg.as_string())

        logger.info(f"Email SMTP envoyé à {payload.to}")
        return True

    # ── SendGrid ────────────────────────────

    def _send_sendgrid(self, payload: EmailPayload) -> bool:
        """Envoi via SendGrid API."""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Content, To
        except ImportError:
            logger.error("sendgrid n'est pas installé.")
            return False

        s = self._settings
        message = Mail(
            from_email=s.email_from,
            to_emails=[To(addr) for addr in payload.to],
            subject=payload.subject,
            html_content=Content("text/html", payload.body_html),
        )

        sg = SendGridAPIClient(api_key=s.sendgrid_api_key)
        response = sg.send(message)
        logger.info(f"Email SendGrid envoyé (status={response.status_code})")
        return 200 <= response.status_code < 300
