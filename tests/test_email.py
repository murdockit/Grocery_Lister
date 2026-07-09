from decimal import Decimal

from app.deals import CandidateDeal, SelectedDeal
from app.outputs.email import _digest_body


def test_digest_body_formats_deals():
    deal = SelectedDeal(
        candidate=CandidateDeal(
            upc="1",
            description="Chicken thighs",
            category="Meat",
            regular_price=Decimal("2.79"),
            promo_price=Decimal("1.99"),
            term="chicken thighs",
        ),
        matched_watchlist_item="chicken thighs",
        reason="Great local price.",
    )

    body = _digest_body([deal])

    assert "Chicken thighs - $1.99 (reg $2.79, 29% off)" in body
    assert "Great local price." in body
