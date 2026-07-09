from decimal import Decimal

from app.deals import CandidateDeal, SelectedDeal
from app.outputs.email import _digest_body, _digest_html


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


def test_digest_body_includes_confidence_and_likelihood():
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
        confidence=82,
        likelihood="likely",
    )

    body = _digest_body([deal])

    assert "confidence: 82" in body
    assert "(likely)" in body


def test_digest_html_renders_table_with_all_columns():
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
        confidence=82,
        likelihood="likely",
    )

    body = _digest_html([deal])

    for header in ("Item", "Regular", "Promo", "Savings %", "Confidence", "Likelihood"):
        assert header in body
    assert "Chicken thighs" in body
    assert "$2.79" in body
    assert "$1.99" in body
    assert "29%" in body
    assert "82" in body
    assert "Likely" in body


def test_digest_html_escapes_item_description():
    deal = SelectedDeal(
        candidate=CandidateDeal(
            upc="1",
            description="<script>alert(1)</script>",
            category="Meat",
            regular_price=Decimal("2.79"),
            promo_price=Decimal("1.99"),
            term="chicken thighs",
        ),
        matched_watchlist_item="chicken thighs",
        reason="Great local price.",
    )

    body = _digest_html([deal])

    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_digest_html_handles_no_deals_and_missing_confidence():
    assert "No qualifying weekly deals found" in _digest_html([])

    deal = SelectedDeal(
        candidate=CandidateDeal(
            upc="1",
            description="Coffee",
            category="Beverages",
            regular_price=None,
            promo_price=Decimal("7.99"),
            term="coffee",
        ),
        matched_watchlist_item="coffee",
        reason="Great local price.",
    )

    body = _digest_html([deal])

    assert "n/a" in body
    assert ">-<" in body
