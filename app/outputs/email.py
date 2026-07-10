from __future__ import annotations

import html
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
        message.add_alternative(_digest_html(deals), subtype="html")
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


_LIKELIHOOD_RANK = {"likely": 0, None: 1, "unlikely": 2}


def _digest_sort_key(deal: SelectedDeal) -> tuple[int, float, int]:
    likelihood_rank = _LIKELIHOOD_RANK.get(deal.likelihood, 1)
    confidence = deal.confidence if deal.confidence is not None else -1.0
    return (likelihood_rank, -confidence, -deal.candidate.discount_pct)


def _sort_for_digest(deals: list[SelectedDeal]) -> list[SelectedDeal]:
    """Surface likely purchases and high-confidence deals first in the email
    (this is presentation-only; it doesn't affect Todoist task order)."""
    return sorted(deals, key=_digest_sort_key)


def _total_savings(deals: list[SelectedDeal]) -> Decimal:
    return sum(
        (
            deal.candidate.regular_price - deal.candidate.promo_price
            for deal in deals
            if deal.candidate.regular_price
        ),
        Decimal("0"),
    )


def _digest_body(deals: list[SelectedDeal]) -> str:
    if not deals:
        return "No qualifying weekly deals found.\n"
    lines = ["Weekly Deals", ""]
    for deal in _sort_for_digest(deals):
        lines.append(f"- {deal.task_content}")
        details = deal.reason
        if deal.confidence is not None:
            details += f" (confidence: {deal.confidence:.0f})"
        if deal.likelihood:
            details += f" ({deal.likelihood})"
        lines.append(f"  {details}")

    savings = _total_savings(deals)
    if savings > 0:
        lines.append("")
        lines.append(f"Estimated savings if you buy everything on this list: ${savings:.2f}")
    return "\n".join(lines) + "\n"


_TABLE_STYLE = "border-collapse:collapse;font-family:sans-serif;font-size:14px;"
_HEADER_CELL_STYLE = "text-align:{align};padding:6px 10px;border-bottom:2px solid #333;"
_BODY_CELL_STYLE = "padding:6px 10px;border-bottom:1px solid #ddd;text-align:{align};"

_COLUMNS = ("Item", "Regular", "Promo", "Savings %", "Confidence", "Likelihood", "Why")
_ALIGNMENTS = ("left", "right", "right", "right", "right", "center", "left")


def _digest_html(deals: list[SelectedDeal]) -> str:
    if not deals:
        return "<p>No qualifying weekly deals found.</p>"

    header_cells = "".join(
        f"<th style='{_HEADER_CELL_STYLE.format(align=align)}'>{name}</th>"
        for name, align in zip(_COLUMNS, _ALIGNMENTS, strict=True)
    )
    rows = "".join(_digest_html_row(deal) for deal in _sort_for_digest(deals))

    savings = _total_savings(deals)
    savings_html = ""
    if savings > 0:
        savings_html = (
            f"<p>Estimated savings if you buy everything on this list: <b>${savings:.2f}</b></p>"
        )

    return (
        "<h2>Weekly Deals</h2>"
        f"<table style='{_TABLE_STYLE}'>"
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        f"{savings_html}"
    )


def _digest_html_row(deal: SelectedDeal) -> str:
    candidate = deal.candidate
    regular = f"${candidate.regular_price:.2f}" if candidate.regular_price is not None else "n/a"
    confidence = f"{deal.confidence:.0f}" if deal.confidence is not None else "n/a"
    likelihood = deal.likelihood.capitalize() if deal.likelihood else "-"
    values = (
        html.escape(candidate.description),
        regular,
        f"${candidate.promo_price:.2f}",
        f"{candidate.discount_pct}%",
        confidence,
        html.escape(likelihood),
        html.escape(deal.reason),
    )
    cells = "".join(
        f"<td style='{_BODY_CELL_STYLE.format(align=align)}'>{value}</td>"
        for value, align in zip(values, _ALIGNMENTS, strict=True)
    )
    return f"<tr>{cells}</tr>"


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
