from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db import init_db, session_scope
from app.distill import (
    DEMOTE_IGNORE_STREAK,
    PROMOTE_PURCHASE_THRESHOLD,
    run_distillation,
    should_run_distillation,
)
from app.models import Decision, Item, Preference
from app.preferences import LEARNED_PREFERENCE_CAP
from app.watchlist import Watchlist


def _week(n: int) -> datetime:
    return datetime(2026, 1, 7, 0, 30, tzinfo=UTC) + timedelta(weeks=n)


def _decision(session, item, signal, week, price=None):
    session.add(Decision(item_id=item.id, signal=signal, price=price, run_date=_week(week)))


def _preference(name: str, keyword: str, source: str) -> Preference:
    return Preference(name=name, keyword=keyword, source=source, active=True)


def test_should_run_distillation_every_fourth_run():
    assert not should_run_distillation(0)
    assert not should_run_distillation(1)
    assert not should_run_distillation(3)
    assert should_run_distillation(4)
    assert should_run_distillation(8)


def test_four_week_purchase_history_promotes_a_learned_preference(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Kroger Chicken Thighs Family Pack", category="Meat")
        session.add(item)
        session.flush()
        for week, price in enumerate([Decimal("1.99"), Decimal("2.19"), Decimal("2.29")]):
            _decision(session, item, "purchased", week, price)

    with session_scope(database_url) as session:
        result = run_distillation(session, Watchlist(items=[]))

    assert len(result.promoted) == 1
    promoted = result.promoted[0]
    assert promoted.times_purchased == PROMOTE_PURCHASE_THRESHOLD
    assert promoted.good_price == Decimal("2.29")

    with session_scope(database_url) as session:
        pref = session.scalar(select(Preference).where(Preference.source == "learned"))
        assert pref is not None
        assert pref.name == "Kroger Chicken Thighs Family Pack"
        assert pref.active is True


def test_consecutive_ignores_demote_a_learned_preference(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Store Brand Yogurt", category="Dairy")
        other_item = Item(upc="upc-2", description="Other Item", category="Dairy")
        session.add_all([item, other_item])
        session.flush()
        session.add(_preference("Store Brand Yogurt", "store brand yogurt", "learned"))
        for week in range(DEMOTE_IGNORE_STREAK):
            _decision(session, item, "ignored", week)
            # Someone bought something else those weeks, so these aren't "weak" no-shopping weeks.
            _decision(session, other_item, "purchased", week, Decimal("1.00"))

    with session_scope(database_url) as session:
        result = run_distillation(session, Watchlist(items=[]))

    demoted = [d for d in result.demoted if d.name == "Store Brand Yogurt"]
    assert len(demoted) == 1
    assert demoted[0].ignored_streak == DEMOTE_IGNORE_STREAK

    with session_scope(database_url) as session:
        pref = session.scalar(select(Preference).where(Preference.keyword == "store brand yogurt"))
        assert pref.active is False


def test_all_ignored_week_does_not_count_toward_demotion(tmp_path):
    """A week where every published item was ignored is a weak signal (the user
    probably skipped shopping) and should not count toward any single item's streak."""
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Store Brand Yogurt", category="Dairy")
        other_item = Item(upc="upc-2", description="Other Item", category="Dairy")
        session.add_all([item, other_item])
        session.flush()
        session.add(_preference("Store Brand Yogurt", "store brand yogurt", "learned"))
        # 5 weeks of genuine ignores (someone bought other_item those weeks, so
        # they're not "weak" no-shopping weeks) - not enough to demote on their own.
        for week in range(5):
            _decision(session, item, "ignored", week)
            _decision(session, other_item, "purchased", week, Decimal("1.00"))
        # A 6th week where *everything* published was ignored - weak signal, should be
        # discounted, so it must not be the straw that pushes this item over the threshold.
        _decision(session, item, "ignored", 5)
        _decision(session, other_item, "ignored", 5)

    with session_scope(database_url) as session:
        result = run_distillation(session, Watchlist(items=[]))

    assert result.demoted == []


def test_seed_preferences_are_never_modified(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="chicken thighs", category="Meat")
        other_item = Item(upc="upc-2", description="Other Item", category="Meat")
        session.add_all([item, other_item])
        session.flush()
        session.add(_preference("chicken thighs", "chicken thighs", "seed"))
        for week in range(DEMOTE_IGNORE_STREAK):
            _decision(session, item, "ignored", week)
            _decision(session, other_item, "purchased", week, Decimal("1.00"))

    with session_scope(database_url) as session:
        result = run_distillation(session, Watchlist(items=[]))

    assert result.demoted == []
    with session_scope(database_url) as session:
        pref = session.scalar(select(Preference).where(Preference.source == "seed"))
        assert pref.active is True


def test_blocklisted_items_are_never_promoted(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Beef Liver", category="Meat")
        session.add(item)
        session.flush()
        for week, price in enumerate([Decimal("1.99"), Decimal("2.19"), Decimal("2.29")]):
            _decision(session, item, "purchased", week, price)

    watchlist = Watchlist(items=[], blocklist=["liver"])
    with session_scope(database_url) as session:
        result = run_distillation(session, watchlist)

    assert result.promoted == []


def test_learned_preference_cap_blocks_new_promotions(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        for n in range(LEARNED_PREFERENCE_CAP):
            session.add(_preference(f"pref-{n}", f"pref-{n}", "learned"))
        item = Item(upc="upc-1", description="New Item", category="Meat")
        session.add(item)
        session.flush()
        for week, price in enumerate([Decimal("1.99"), Decimal("2.19"), Decimal("2.29")]):
            _decision(session, item, "purchased", week, price)

    with session_scope(database_url) as session:
        result = run_distillation(session, Watchlist(items=[]))

    assert result.promoted == []
