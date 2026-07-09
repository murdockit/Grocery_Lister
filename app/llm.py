from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.deals import CandidateDeal, SelectedDeal
from app.pricing import fallback_select, passes_discount_threshold
from app.watchlist import Watchlist


class LlmDecision(BaseModel):
    upc: str
    matched_watchlist_item: str
    is_good_deal: bool
    reason: str


class LlmResponse(BaseModel):
    deals: list[LlmDecision]


class DealSelector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def select(self, candidates: list[CandidateDeal], watchlist: Watchlist) -> list[SelectedDeal]:
        if not self.settings.gemini_api_key:
            return fallback_select(candidates, watchlist)
        try:
            decisions = self._ask_gemini(candidates, watchlist)
        except Exception:
            return fallback_select(candidates, watchlist)

        by_upc = {candidate.upc: candidate for candidate in candidates}
        selected: list[SelectedDeal] = []
        for decision in decisions.deals:
            candidate = by_upc.get(decision.upc)
            if candidate is None or not decision.is_good_deal:
                continue
            if not passes_discount_threshold(candidate, watchlist.min_discount_pct):
                continue
            selected.append(
                SelectedDeal(
                    candidate=candidate,
                    matched_watchlist_item=decision.matched_watchlist_item,
                    reason=decision.reason,
                )
            )
        selected.sort(key=lambda deal: deal.candidate.discount_pct, reverse=True)
        return selected[: watchlist.max_list_size]

    def _ask_gemini(self, candidates: list[CandidateDeal], watchlist: Watchlist) -> LlmResponse:
        client = genai.Client(api_key=self.settings.gemini_api_key)
        payload = {
            "watchlist": watchlist.model_dump(mode="json"),
            "candidates": [_candidate_payload(candidate) for candidate in candidates],
            "instruction": (
                "Return which candidate sale items are genuinely relevant to the watchlist. "
                "Do not apply max_list_size or min_discount_pct; code will apply those filters."
            ),
        }
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=json.dumps(payload),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LlmResponse.model_json_schema(),
            ),
        )
        raw = response.text or "{}"
        try:
            return LlmResponse.model_validate_json(raw)
        except ValidationError:
            parsed: Any = json.loads(raw)
            return LlmResponse.model_validate(parsed)


def _candidate_payload(candidate: CandidateDeal) -> dict[str, Any]:
    return {
        "upc": candidate.upc,
        "description": candidate.description,
        "category": candidate.category,
        "regular_price": str(candidate.regular_price) if candidate.regular_price is not None else None,
        "promo_price": str(candidate.promo_price),
        "discount_pct": candidate.discount_pct,
        "matched_search_term": candidate.term,
        "size": candidate.size,
    }
