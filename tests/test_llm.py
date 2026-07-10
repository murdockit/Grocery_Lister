from decimal import Decimal

from app.config import Settings
from app.deals import CandidateDeal
from app.habits import HabitSummary
from app.llm import DealSelector, LlmDecision, LlmResponse
from app.watchlist import WatchItem, Watchlist


def test_select_propagates_confidence_and_likelihood_from_llm(monkeypatch):
    settings = Settings(gemini_api_key="fake-key")
    selector = DealSelector(settings)
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

    response = LlmResponse(
        deals=[
            LlmDecision(
                upc="1",
                matched_watchlist_item="coffee",
                is_good_deal=True,
                confidence=82,
                reason="Matches watchlist and is on sale.",
            )
        ]
    )
    monkeypatch.setattr(selector, "_ask_gemini", lambda *args, **kwargs: response)

    selected = selector.select([candidate], watchlist, habits, {})

    assert len(selected) == 1
    assert selected[0].confidence == 82
    assert selected[0].likelihood == "likely"


def test_select_falls_back_when_gemini_raises(monkeypatch):
    settings = Settings(gemini_api_key="fake-key")
    selector = DealSelector(settings)
    watchlist = Watchlist(items=[WatchItem(name="coffee")], min_discount_pct=15, max_list_size=10)
    candidate = CandidateDeal(
        upc="1",
        description="Private Selection Coffee",
        category="Beverages",
        regular_price=Decimal("10.99"),
        promo_price=Decimal("7.99"),
        term="coffee",
    )

    def boom(*args, **kwargs):
        raise RuntimeError("gemini is down")

    monkeypatch.setattr(selector, "_ask_gemini", boom)

    selected = selector.select([candidate], watchlist)

    assert len(selected) == 1
    assert selected[0].confidence is None
