from decimal import Decimal

from app.db import init_db, session_scope
from app.habits import HabitSummary, build_habit_summary, build_price_history, compute_likelihood
from app.models import Decision, Item, PriceHistory


def test_build_habit_summary_aggregates_purchases_and_ignores(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Chicken thighs", category="Meat")
        session.add(item)
        session.flush()
        session.add(Decision(item_id=item.id, signal="purchased", price=Decimal("1.99")))
        session.add(Decision(item_id=item.id, signal="purchased", price=Decimal("2.49")))
        session.add(Decision(item_id=item.id, signal="ignored", price=Decimal("2.99")))
        regular, item_id = Decimal("2.79"), item.id
        session.add(
            PriceHistory(item_id=item_id, regular_price=regular, promo_price=Decimal("1.99"))
        )
        session.add(
            PriceHistory(item_id=item_id, regular_price=regular, promo_price=Decimal("2.49"))
        )

    with session_scope(database_url) as session:
        summary = build_habit_summary(session, ["upc-1"])

    stats = summary["upc-1"]
    assert stats.times_purchased == 2
    assert stats.times_ignored == 1
    assert stats.max_price_purchased_at == Decimal("2.49")
    assert stats.min_promo_price_seen == Decimal("1.99")
    assert stats.avg_promo_price_seen == Decimal("2.24")


def test_build_habit_summary_empty_for_unknown_upc(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        summary = build_habit_summary(session, ["missing-upc"])

    assert summary == {}


def test_build_price_history_returns_promo_prices_by_upc(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Coffee", category="Pantry")
        session.add(item)
        session.flush()
        session.add(
            PriceHistory(
                item_id=item.id, regular_price=Decimal("10.99"), promo_price=Decimal("7.99")
            )
        )

    with session_scope(database_url) as session:
        history = build_price_history(session, ["upc-1", "missing-upc"])

    assert history == {"upc-1": [Decimal("7.99")]}


def test_compute_likelihood_thresholds():
    assert compute_likelihood(None) is None
    assert compute_likelihood(HabitSummary(times_purchased=0, times_ignored=0)) is None
    assert compute_likelihood(HabitSummary(times_purchased=2, times_ignored=5)) is None
    assert compute_likelihood(HabitSummary(times_purchased=3, times_ignored=0)) == "likely"
    assert compute_likelihood(HabitSummary(times_purchased=0, times_ignored=6)) == "unlikely"
    # Purchase evidence wins if both thresholds are somehow crossed.
    assert compute_likelihood(HabitSummary(times_purchased=3, times_ignored=6)) == "likely"
