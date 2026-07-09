from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Preference, utc_now
from app.watchlist import Watchlist

LEARNED_PREFERENCE_CAP = 50


def sync_seed_preferences(session: Session, watchlist: Watchlist) -> None:
    """Upsert seed=source preferences from watchlist.yaml; YAML is authoritative.

    Seed rows missing from the current YAML, and learned rows matching the
    blocklist, are deactivated (never deleted) so purchase history stays intact.
    """
    blocked = watchlist.blocked_set
    now = utc_now()

    existing_seed = {
        pref.keyword: pref
        for pref in session.scalars(select(Preference).where(Preference.source == "seed"))
    }

    current_keywords: set[str] = set()
    for item in watchlist.items:
        keyword = item.name.strip().lower()
        current_keywords.add(keyword)
        pref = existing_seed.get(keyword)
        if pref is None:
            pref = Preference(name=item.name, keyword=keyword, source="seed", weight=1.0)
            session.add(pref)
        pref.name = item.name
        pref.good_price = item.good_price
        pref.unit = item.unit
        pref.active = keyword not in blocked
        pref.last_updated = now

    for category in watchlist.categories:
        keyword = category.strip().lower()
        current_keywords.add(keyword)
        pref = existing_seed.get(keyword)
        if pref is None:
            pref = Preference(
                name=category, keyword=keyword, category=category, source="seed", weight=1.0
            )
            session.add(pref)
        pref.name = category
        pref.category = category
        pref.active = keyword not in blocked
        pref.last_updated = now

    for keyword, pref in existing_seed.items():
        if keyword not in current_keywords:
            pref.active = False
            pref.last_updated = now

    for pref in session.scalars(select(Preference).where(Preference.source == "learned")):
        name_blocked = pref.keyword in blocked or pref.name.strip().lower() in blocked
        if name_blocked or watchlist.is_blocked(pref.name):
            pref.active = False
            pref.last_updated = now


def active_learned_terms(session: Session, watchlist: Watchlist) -> list[str]:
    prefs = session.scalars(
        select(Preference).where(Preference.source == "learned", Preference.active.is_(True))
    )
    terms = [pref.name for pref in prefs if not watchlist.is_blocked(pref.name)]
    return list(dict.fromkeys(terms))


def active_learned_count(session: Session) -> int:
    query = select(Preference).where(Preference.source == "learned", Preference.active.is_(True))
    return len(list(session.scalars(query)))
