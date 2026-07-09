from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import Settings
from app.deals import SelectedDeal
from app.outputs.base import OutputAdapter


class EmailOutput(OutputAdapter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish(self, deals: list[SelectedDeal]) -> None:
        if not self._configured:
            return
        message = EmailMessage()
        message["Subject"] = "Weekly Deals"
        message["From"] = self.settings.effective_email_from
        message["To"] = self.settings.notify_email
        message.set_content(_digest_body(deals))
        self._send(message)

    async def send_failure(self, error: str) -> None:
        if not self._configured:
            return
        message = EmailMessage()
        message["Subject"] = "Weekly Deal Watcher failed"
        message["From"] = self.settings.effective_email_from
        message["To"] = self.settings.notify_email
        message.set_content(f"The weekly deal job failed:\n\n{error}\n")
        self._send(message)

    @property
    def _configured(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.notify_email and self.settings.effective_email_from)

    def _send(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if self.settings.smtp_user:
                smtp.login(self.settings.smtp_user, self.settings.smtp_pass)
            smtp.send_message(message)


def _digest_body(deals: list[SelectedDeal]) -> str:
    if not deals:
        return "No qualifying weekly deals found.\n"
    lines = ["Weekly Deals", ""]
    for deal in deals:
        lines.append(f"- {deal.task_content}")
        lines.append(f"  {deal.reason}")
    return "\n".join(lines) + "\n"
