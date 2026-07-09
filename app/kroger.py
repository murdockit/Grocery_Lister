from __future__ import annotations

import base64
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.deals import CandidateDeal
from app.http import with_retries

KROGER_BASE_URL = "https://api.kroger.com/v1"
FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "kroger_products.json"


class KrogerClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_promo_deals(self, terms: list[str]) -> list[CandidateDeal]:
        if self.settings.mock_kroger:
            return self._load_mock_deals(terms)

        token = await self._get_access_token()
        deals: list[CandidateDeal] = []
        location_ids = self.settings.kroger_location_ids
        if not location_ids:
            raise RuntimeError("KROGER_LOCATION_ID is required")

        async with httpx.AsyncClient(base_url=KROGER_BASE_URL, timeout=self.settings.http_timeout_seconds) as client:
            for term in terms:
                for location_id in location_ids:
                    deals.extend(await self._search_products(client, token, term, location_id))
        return _best_deals_by_upc(deals)

    async def find_locations(self, zip_code: str, limit: int = 10) -> list[dict[str, Any]]:
        token = await self._get_access_token()
        async with httpx.AsyncClient(base_url=KROGER_BASE_URL, timeout=self.settings.http_timeout_seconds) as client:
            response = await with_retries(
                lambda: client.get(
                    "/locations",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"filter.zipCode.near": zip_code, "filter.limit": str(limit)},
                )
            )
            response.raise_for_status()
            return response.json().get("data", [])

    async def _get_access_token(self) -> str:
        if not self.settings.kroger_client_id or not self.settings.kroger_client_secret:
            raise RuntimeError("KROGER_CLIENT_ID and KROGER_CLIENT_SECRET are required")

        credentials = f"{self.settings.kroger_client_id}:{self.settings.kroger_client_secret}".encode()
        auth = base64.b64encode(credentials).decode()
        async with httpx.AsyncClient(base_url=KROGER_BASE_URL, timeout=self.settings.http_timeout_seconds) as client:
            response = await with_retries(
                lambda: client.post(
                    "/connect/oauth2/token",
                    headers={
                        "Authorization": f"Basic {auth}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={"grant_type": "client_credentials", "scope": "product.compact"},
                )
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def _search_products(
        self, client: httpx.AsyncClient, token: str, term: str, location_id: str
    ) -> list[CandidateDeal]:
        response = await with_retries(
            lambda: client.get(
                "/products",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "filter.term": term,
                    "filter.locationId": location_id,
                    "filter.limit": "50",
                },
            )
        )
        response.raise_for_status()
        return self._parse_products(response.json().get("data", []), term, location_id)

    def _load_mock_deals(self, terms: list[str]) -> list[CandidateDeal]:
        with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
            products = json.load(handle).get("data", [])
        parsed: list[CandidateDeal] = []
        for term in terms:
            parsed.extend(self._parse_products(products, term))
        return _best_deals_by_upc(parsed)

    def _parse_products(
        self, products: list[dict[str, Any]], term: str, location_id: str | None = None
    ) -> list[CandidateDeal]:
        deals: list[CandidateDeal] = []
        for product in products:
            item = (product.get("items") or [{}])[0]
            price = item.get("price") or {}
            promo = _to_decimal(price.get("promo"))
            regular = _to_decimal(price.get("regular"))
            if promo is None:
                continue
            deals.append(
                CandidateDeal(
                    upc=str(product.get("upc", "")),
                    description=str(product.get("description", "Unknown item")),
                    category=_category(product),
                    regular_price=regular,
                    promo_price=promo,
                    term=term,
                    size=item.get("size"),
                    location_id=location_id,
                )
            )
        return deals


def _best_deals_by_upc(deals: list[CandidateDeal]) -> list[CandidateDeal]:
    best: dict[str, CandidateDeal] = {}
    for deal in deals:
        current = best.get(deal.upc)
        if current is None or deal.promo_price < current.promo_price:
            best[deal.upc] = deal
    return list(best.values())


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _category(product: dict[str, Any]) -> str | None:
    categories = product.get("categories") or []
    if categories:
        return str(categories[0])
    return None
