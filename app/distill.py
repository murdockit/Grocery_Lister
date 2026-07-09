from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Decision, Item, Preference, utc_now
from app.preferences import LEARNED_PREFERENCE_CAP, active_learned_count
from app.watchlist import Watchlist

logger = logging.getLogger(__name__)

PROMOTE_PURCHASE_THRESHOLD = 3
DEMOTE_IGNORE_STREAK = 6


@dataclass
class PromotedPreference:
    name: str
    good_price: Decimal | None
    times_purchased: int
    reason: str = ""


@dataclass
class DemotedPreference:
    name: str
    ignored_streak: int
    reason: str = ""


@dataclass
class DistillationResult:
    promoted: list[PromotedPreference] = field(default_factory=list)
    demoted: list[DemotedPreference] = field(default_factory=list)


def should_run_distillation(successful_run_count: int, every: int = 4) -> bool:
    return successful_run_count > 0 and successful_run_count % every == 0


def run_distillation(session: Session, watchlist: Watchlist) -> DistillationResult:
    """Deterministic promote/demote pass over decision history, with hard guardrails:

    seed preferences are never modified, learned rows are capped, and blocklisted
    items are never promoted. This is the code-side authority the plan calls for;
    any LLM commentary layered on top only annotates these decisions, it doesn't
    make them.
    """
    result = DistillationResult()
    all_decisions = list(session.scalars(select(Decision)))
    if not all_decisions:
        return result

    decisions_by_day: dict[date, list[Decision]] = {}
    decisions_by_item: dict[int, list[Decision]] = {}
    for decision in all_decisions:
        decisions_by_day.setdefault(decision.run_date.date(), []).append(decision)
        decisions_by_item.setdefault(decision.item_id, []).append(decision)

    active_names = {
        pref.keyword
        for pref in session.scalars(select(Preference).where(Preference.active.is_(True)))
    }

    for item_id, item_decisions in decisions_by_item.items():
        item = session.get(Item, item_id)
        if item is None:
            continue
        keyword = item.description.strip().lower()
        if watchlist.is_blocked(item.description):
            continue

        purchased = [d for d in item_decisions if d.signal == "purchased" and d.price is not None]
        if len(purchased) >= PROMOTE_PURCHASE_THRESHOLD and keyword not in active_names:
            if active_learned_count(session) >= LEARNED_PREFERENCE_CAP:
                logger.info(
                    "Learned preference cap (%s) reached; skipping promotion of %s",
                    LEARNED_PREFERENCE_CAP,
                    item.description,
                )
                continue
            good_price = max(d.price for d in purchased)
            evidence = {
                "times_purchased": len(purchased),
                "purchase_prices": [str(d.price) for d in purchased],
            }
            pref = Preference(
                name=item.description,
                keyword=keyword,
                good_price=good_price,
                weight=1.0,
                source="learned",
                active=True,
                last_updated=utc_now(),
                evidence=json.dumps(evidence),
            )
            session.add(pref)
            active_names.add(keyword)
            promoted = PromotedPreference(
                name=item.description,
                good_price=good_price,
                times_purchased=len(purchased),
                reason=(
                    f"Purchased {len(purchased)} times; learned a good price of ${good_price:.2f}."
                ),
            )
            logger.info("Promoted learned preference: %s", promoted)
            result.promoted.append(promoted)
            continue

        streak = _consecutive_ignored(item_decisions, decisions_by_day)
        if streak >= DEMOTE_IGNORE_STREAK:
            learned_pref = session.scalar(
                select(Preference).where(
                    Preference.source == "learned",
                    Preference.active.is_(True),
                    Preference.keyword == keyword,
                )
            )
            if learned_pref is not None:
                learned_pref.active = False
                learned_pref.last_updated = utc_now()
                demoted = DemotedPreference(
                    name=learned_pref.name,
                    ignored_streak=streak,
                    reason=(
                        f"Ignored {streak} consecutive appearances; deactivating this preference."
                    ),
                )
                logger.info("Demoted learned preference: %s", demoted)
                result.demoted.append(demoted)

    return result


def _is_weak_week(decisions_that_day: list[Decision]) -> bool:
    """A week where every published item was ignored is a weak signal (the user
    probably skipped shopping), not evidence against any specific item."""
    return bool(decisions_that_day) and all(d.signal == "ignored" for d in decisions_that_day)


def _consecutive_ignored(
    item_decisions: list[Decision], decisions_by_day: dict[date, list[Decision]]
) -> int:
    ordered = sorted(item_decisions, key=lambda d: d.run_date, reverse=True)
    streak = 0
    for decision in ordered:
        if _is_weak_week(decisions_by_day.get(decision.run_date.date(), [])):
            continue
        if decision.signal == "ignored":
            streak += 1
        else:
            break
    return streak
