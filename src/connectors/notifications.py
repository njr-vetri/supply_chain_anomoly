"""SMTP and webhook notifications. Credentials and endpoints come from environment variables."""
from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
import os
import smtplib
from typing import Callable
from urllib.request import Request, urlopen

from src.connectors.base import ConnectorHealth


class SMTPNotificationAdapter:
    def __init__(self, *, timeout_seconds: int = 10, enabled_env: str = "CONNECTORS_ENABLED",
                 smtp_factory=smtplib.SMTP):
        self.timeout = timeout_seconds
        self.enabled_env = enabled_env
        self.simulated = smtp_factory is not smtplib.SMTP
        self.smtp_factory = smtp_factory

    def _config(self):
        values = {key: os.getenv(key) for key in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO")}
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise RuntimeError("SMTP environment configuration is incomplete")
        values["SMTP_PORT"] = os.getenv("SMTP_PORT", "587")
        values["SMTP_STARTTLS"] = os.getenv("SMTP_STARTTLS", "true").lower() == "true"
        return values

    def health_check(self) -> ConnectorHealth:
        if os.getenv(self.enabled_env, "false").lower() != "true":
            return ConnectorHealth("smtp_email", "DRY_RUN", datetime.now(timezone.utc).isoformat(),
                                   "notifications are disabled; no SMTP connection attempted")
        try:
            config = self._config()
            if self.simulated:
                return ConnectorHealth("smtp_email", "SIMULATED", datetime.now(timezone.utc).isoformat(),
                                       "injected SMTP transport; no email server was contacted")
            with self.smtp_factory(config["SMTP_HOST"], int(config["SMTP_PORT"]), timeout=self.timeout) as client:
                client.ehlo()
                if config["SMTP_STARTTLS"]:
                    client.starttls()
                    client.ehlo()
                client.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            status, detail = "HEALTHY", "SMTP connectivity and authentication succeeded"
        except Exception as exc:
            status, detail = "UNAVAILABLE", f"SMTP health check failed ({type(exc).__name__})"
        return ConnectorHealth("smtp_email", status, datetime.now(timezone.utc).isoformat(), detail)

    def send(self, *, subject: str, message: str) -> dict:
        if os.getenv(self.enabled_env, "false").lower() != "true":
            return {"status": "DRY_RUN", "label": "DRY_RUN", "connector": "smtp_email"}
        config = self._config()
        email = EmailMessage()
        email["Subject"], email["From"], email["To"] = subject, config["SMTP_FROM"], config["SMTP_TO"]
        email.set_content(message)
        with self.smtp_factory(config["SMTP_HOST"], int(config["SMTP_PORT"]), timeout=self.timeout) as client:
            client.ehlo()
            if config["SMTP_STARTTLS"]:
                client.starttls()
                client.ehlo()
            client.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
            client.send_message(email)
        return {"status": "SIMULATED" if self.simulated else "SENT",
                "label": "SIMULATED" if self.simulated else "REAL", "connector": "smtp_email"}


class WebhookNotificationAdapter:
    def __init__(self, *, url_env: str = "WEBHOOK_URL", token_env: str | None = "WEBHOOK_TOKEN",
                 timeout_seconds: int = 10, enabled_env: str = "CONNECTORS_ENABLED",
                 request_transport: Callable | None = None):
        self.url_env, self.token_env, self.timeout = url_env, token_env, timeout_seconds
        self.enabled_env = enabled_env
        self.simulated = request_transport is not None
        self.request_transport = request_transport or urlopen

    def _request(self, method: str, data: bytes | None = None) -> Request:
        endpoint = os.getenv(self.url_env)
        if not endpoint:
            raise RuntimeError("Webhook endpoint environment variable is not configured")
        headers = {"Content-Type": "application/json"}
        token = os.getenv(self.token_env) if self.token_env else None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return Request(endpoint, data=data, headers=headers, method=method)

    def health_check(self) -> ConnectorHealth:
        if os.getenv(self.enabled_env, "false").lower() != "true":
            return ConnectorHealth("webhook", "DRY_RUN", datetime.now(timezone.utc).isoformat(),
                                   "notifications are disabled; no webhook request attempted")
        try:
            if self.simulated:
                return ConnectorHealth("webhook", "SIMULATED", datetime.now(timezone.utc).isoformat(),
                                       "injected HTTP transport; no webhook was contacted")
            request = self._request("HEAD")
            with self.request_transport(request, timeout=self.timeout) as response:
                status = "HEALTHY" if 200 <= response.status < 400 else "UNAVAILABLE"
                detail = "webhook endpoint responded" if status == "HEALTHY" else "webhook endpoint returned an error status"
        except Exception as exc:
            status, detail = "UNAVAILABLE", f"webhook health check failed ({type(exc).__name__})"
        return ConnectorHealth("webhook", status, datetime.now(timezone.utc).isoformat(), detail)

    def send(self, *, subject: str, message: str) -> dict:
        if os.getenv(self.enabled_env, "false").lower() != "true":
            return {"status": "DRY_RUN", "label": "DRY_RUN", "connector": "webhook"}
        import json
        request = self._request("POST", json.dumps({"subject": subject, "message": message}).encode("utf-8"))
        with self.request_transport(request, timeout=self.timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Webhook returned HTTP {response.status}")
        return {"status": "SIMULATED" if self.simulated else "SENT",
                "label": "SIMULATED" if self.simulated else "REAL", "connector": "webhook"}
