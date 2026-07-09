from decimal import Decimal

from app.deals import CandidateDeal
from app.pricing import fallback_select
from app.watchlist import WatchItem, Watchlist


def test_fallback_select_uses_good_price_and_discount_threshold():
    watchlist = Watchlist(
        items=[WatchItem(name="chicken thighs", good_price=Decimal("2.00")), WatchItem(name="coffee")],
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
