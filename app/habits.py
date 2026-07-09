from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision, Item, PriceHistory


class HabitSummary(BaseModel):
    times_purchased: int = 0
    times_ignored: int = 0
    last_purchase_date: datetime | None = None
    max_price_purchased_at: Decimal | None = None
    min_promo_price_seen: Decimal | None = None
    avg_promo_price_seen: Decimal | None = None


def build_habit_summary(session: Session, upcs: list[str]) -> dict[str, HabitSummary]:
    """Per-item replenishment/purchase habits, keyed by UPC, for the weekly LLM prompt."""
    if not upcs:
        return {}

    summary: dict[str, HabitSummary] = {}
    items = session.scalars(select(Item).where(Item.upc.in_(upcs))).all()
    for item in items:
        decisions = list(session.scalars(select(Decision).where(Decision.item_id == item.id)))
        purchased = [d for d in decisions if d.signal == "purchased"]
        ignored = [d for d in decisions if d.signal == "ignored"]

        promos = [
            ph.promo_price
            for ph in session.scalars(select(PriceHistory).where(PriceHistory.item_id == item.id))
            if ph.promo_price is not None
        ]

        purchased_prices = [d.price for d in purchased if d.price is not None]
        summary[item.upc] = HabitSummary(
            times_purchased=len(purchased),
            times_ignored=len(ignored),
            last_purchase_date=max((d.run_date for d in purchased), default=None),
            max_price_purchased_at=max(purchased_prices, default=None),
            min_promo_price_seen=min(promos, default=None),
            avg_promo_price_seen=(sum(promos) / len(promos)) if promos else None,
        )
    return summary


def build_price_history(session: Session, upcs: list[str]) -> dict[str, list[Decimal]]:
    """Prior promo prices per UPC, for percentile-based 'good deal' scoring."""
    if not upcs:
        return {}

    history: dict[str, list[Decimal]] = {}
    items = session.scalars(select(Item).where(Item.upc.in_(upcs))).all()
    for item in items:
        promos = [
            ph.promo_price
            for ph in session.scalars(select(PriceHistory).where(PriceHistory.item_id == item.id))
            if ph.promo_price is not None
        ]
        if promos:
            history[item.upc] = promos
    return history
