from __future__ import annotations

import smtplib
from decimal import Decimal
from email.message import EmailMessage

from app.config import Settings
from app.deals import SelectedDeal
from app.distill import DemotedPreference, PromotedPreference
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

    async def send_learning_summary(
        self, promoted: list[PromotedPreference], demoted: list[DemotedPreference]
    ) -> None:
        if not self._configured or (not promoted and not demoted):
            return
        message = EmailMessage()
        message["Subject"] = "Weekly Deal Watcher - what I learned"
        message["From"] = self.settings.effective_email_from
        message["To"] = self.settings.notify_email
        message.set_content(_learning_summary_body(promoted, demoted))
        self._send(message)

    @property
    def _configured(self) -> bool:
        settings = self.settings
        return bool(settings.smtp_host and settings.notify_email and settings.effective_email_from)

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

    savings = sum(
        (
            deal.candidate.regular_price - deal.candidate.promo_price
            for deal in deals
            if deal.candidate.regular_price
        ),
        Decimal("0"),
    )
    if savings > 0:
        lines.append("")
        lines.append(f"Estimated savings if you buy everything on this list: ${savings:.2f}")
    return "\n".join(lines) + "\n"


def _learning_summary_body(
    promoted: list[PromotedPreference], demoted: list[DemotedPreference]
) -> str:
    lines = ["What I learned this month", ""]
    if promoted:
        lines.append("New preferences learned:")
        for pref in promoted:
            lines.append(f"- {pref.name}: {pref.reason}")
        lines.append("")
    if demoted:
        lines.append("Preferences deactivated:")
        for pref in demoted:
            lines.append(f"- {pref.name}: {pref.reason}")
        lines.append("")
    lines.append(
        "Disagree with any of these? Add the item name to 'blocklist' in watchlist.yaml to veto it."
    )
    return "\n".join(lines) + "\n"
