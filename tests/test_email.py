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

    for header in ("Item", "Regular", "Promo", "Savings %", "Confidence", "Likelihood", "Why"):
        assert header in body
    assert "Chicken thighs" in body
    assert "$2.79" in body
    assert "$1.99" in body
    assert "29%" in body
    assert "82" in body
    assert "Likely" in body
    assert "Great local price." in body


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


def _deal(upc: str, confidence, likelihood, discount_pct: int = 10) -> SelectedDeal:
    regular = Decimal("10.00")
    promo = regular * (Decimal(100 - discount_pct) / Decimal(100))
    return SelectedDeal(
        candidate=CandidateDeal(
            upc=upc,
            description=f"Item {upc}",
            category="Misc",
            regular_price=regular,
            promo_price=promo,
            term="item",
        ),
        matched_watchlist_item="item",
        reason="reason",
        confidence=confidence,
        likelihood=likelihood,
    )


def test_digest_sorts_likely_and_high_confidence_first():
    unlikely = _deal("unlikely", confidence=90, likelihood="unlikely", discount_pct=50)
    blank_low_conf = _deal("blank-low", confidence=20, likelihood=None, discount_pct=40)
    blank_high_conf = _deal("blank-high", confidence=95, likelihood=None, discount_pct=10)
    likely_low_conf = _deal("likely-low", confidence=10, likelihood="likely", discount_pct=5)
    likely_high_conf = _deal("likely-high", confidence=99, likelihood="likely", discount_pct=5)

    deals = [unlikely, blank_low_conf, likely_low_conf, blank_high_conf, likely_high_conf]

    html_body = _digest_html(deals)
    text_body = _digest_body(deals)

    expected_order = ["likely-high", "likely-low", "blank-high", "blank-low", "unlikely"]

    def positions(body: str) -> list[str]:
        return sorted(expected_order, key=lambda upc: body.index(f"Item {upc}"))

    assert positions(html_body) == expected_order
    assert positions(text_body) == expected_order


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
