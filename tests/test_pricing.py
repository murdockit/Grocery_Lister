from decimal import Decimal

from app.deals import CandidateDeal
from app.habits import HabitSummary
from app.pricing import fallback_select, is_historically_good_price, promo_percentile
from app.watchlist import WatchItem, Watchlist


def test_fallback_select_uses_good_price_and_discount_threshold():
    watchlist = Watchlist(
        items=[
            WatchItem(name="chicken thighs", good_price=Decimal("2.00")),
            WatchItem(name="coffee"),
        ],
        min_discount_pct=15,
        max_list_size=10,
    )
    candidates = [
        CandidateDeal(
            upc="1",
            description="Kroger Chicken Thighs",
            category="Meat",
            regular_price=Decimal("2.79"),
            promo_price=Decimal("1.99"),
            term="chicken thighs",
        ),
        CandidateDeal(
            upc="2",
            description="Private Selection Coffee",
            category="Beverages",
            regular_price=Decimal("10.99"),
            promo_price=Decimal("10.49"),
            term="coffee",
        ),
    ]

    selected = fallback_select(candidates, watchlist)

    assert [deal.candidate.upc for deal in selected] == ["1"]


def test_fallback_select_skips_blocklisted_candidates():
    watchlist = Watchlist(
        items=[WatchItem(name="chicken")],
        blocklist=["liver"],
        min_discount_pct=0,
        max_list_size=10,
    )
    candidates = [
        CandidateDeal(
            upc="1",
            description="Kroger Chicken Liver Pate",
            category="Meat",
            regular_price=Decimal("2.79"),
            promo_price=Decimal("1.99"),
            term="chicken",
        ),
    ]

    selected = fallback_select(candidates, watchlist)

    assert selected == []


def test_fallback_select_accepts_historically_good_price_below_discount_threshold():
    watchlist = Watchlist(
        items=[WatchItem(name="coffee")],
        min_discount_pct=50,
        max_list_size=10,
    )
    candidate = CandidateDeal(
        upc="1",
        description="Private Selection Coffee",
        category="Beverages",
        regular_price=Decimal("10.99"),
        promo_price=Decimal("7.99"),
        term="coffee",
    )
    history = {"1": [Decimal("9.99"), Decimal("8.99"), Decimal("7.99"), Decimal("10.49")]}

    selected = fallback_select([candidate], watchlist, history)

    assert [deal.candidate.upc for deal in selected] == ["1"]
    assert "percentile" in selected[0].reason


def test_fallback_select_attaches_likelihood_from_habits():
    watchlist = Watchlist(items=[WatchItem(name="coffee")], min_discount_pct=0, max_list_size=10)
    candidate = CandidateDeal(
        upc="1",
        description="Private Selection Coffee",
        category="Beverages",
        regular_price=Decimal("10.99"),
        promo_price=Decimal("10.49"),
        term="coffee",
    )
    habits = {"1": HabitSummary(times_purchased=3, times_ignored=0)}

    selected = fallback_select([candidate], watchlist, habits=habits)

    assert selected[0].likelihood == "likely"
    assert selected[0].confidence is None


def test_promo_percentile_uses_nearest_rank():
    promos = [Decimal("1.00"), Decimal("2.00"), Decimal("3.00"), Decimal("4.00")]

    assert promo_percentile(promos, 25) == Decimal("1.00")
    assert promo_percentile(promos, 100) == Decimal("4.00")
    assert promo_percentile([], 25) is None


def test_is_historically_good_price_requires_history():
    assert not is_historically_good_price(Decimal("1.99"), [])
    history = [Decimal("1.00"), Decimal("2.00"), Decimal("3.00")]
    assert is_historically_good_price(Decimal("1.00"), history)
