from decimal import Decimal

import pytest

from app.config import Settings
from app.deals import CandidateDeal
from app.kroger import KrogerClient


def test_kroger_location_ids_normalizes_csv() -> None:
    settings = Settings(kroger_location_id="store-a, store-b, store-a")

    assert settings.kroger_location_ids == ["store-a", "store-b"]


@pytest.mark.asyncio
async def test_get_promo_deals_searches_each_location_and_keeps_best_price() -> None:
    settings = Settings(kroger_location_id="store-a,store-b")
    client = KrogerClient(settings)
    calls: list[tuple[str, str]] = []

    async def fake_get_access_token() -> str:
        return "token"

    async def fake_search_products(_http_client, _token: str, term: str, location_id: str):
        calls.append((term, location_id))
        return [
            CandidateDeal(
                upc="0001111011111",
                description="Coffee",
                category="Pantry",
                regular_price=Decimal("8.99"),
                promo_price=Decimal("5.99") if location_id == "store-a" else Decimal("4.99"),
                term=term,
                location_id=location_id,
            )
        ]

    client._get_access_token = fake_get_access_token
    client._search_products = fake_search_products

    deals = await client.get_promo_deals(["coffee"])

    assert calls == [("coffee", "store-a"), ("coffee", "store-b")]
    assert [(deal.upc, deal.promo_price, deal.location_id) for deal in deals] == [
        ("0001111011111", Decimal("4.99"), "store-b")
    ]