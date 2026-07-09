from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.deals import CandidateDeal, SelectedDeal
from app.distill import DistillationResult
from app.habits import HabitSummary
from app.pricing import fallback_select, is_historically_good_price, passes_discount_threshold
from app.watchlist import Watchlist


class LlmDecision(BaseModel):
    upc: str
    matched_watchlist_item: str
    is_good_deal: bool
    confidence: float | None = None
    reason: str


class LlmResponse(BaseModel):
    deals: list[LlmDecision]


class DealSelector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def select(
        self,
        candidates: list[CandidateDeal],
        watchlist: Watchlist,
        habits: dict[str, HabitSummary] | None = None,
        history: dict[str, list[Decimal]] | None = None,
    ) -> list[SelectedDeal]:
        habits = habits or {}
        history = history or {}
        candidates = [
            candidate
            for candidate in candidates
            if not watchlist.is_blocked(candidate.description)
            and not watchlist.is_blocked(candidate.category or "")
        ]

        if not self.settings.gemini_api_key:
            return fallback_select(candidates, watchlist, history)
        try:
            decisions = self._ask_gemini(candidates, watchlist, habits, history)
        except Exception:
            return fallback_select(candidates, watchlist, history)

        by_upc = {candidate.upc: candidate for candidate in candidates}
        selected: list[SelectedDeal] = []
        for decision in decisions.deals:
            candidate = by_upc.get(decision.upc)
            if candidate is None or not decision.is_good_deal:
                continue
            item_history = history.get(candidate.upc, [])
            historically_good = is_historically_good_price(candidate.promo_price, item_history)
            passes_discount = passes_discount_threshold(candidate, watchlist.min_discount_pct)
            if not passes_discount and not historically_good:
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

    def _ask_gemini(
        self,
        candidates: list[CandidateDeal],
        watchlist: Watchlist,
        habits: dict[str, HabitSummary],
        history: dict[str, list[Decimal]],
    ) -> LlmResponse:
        client = genai.Client(api_key=self.settings.gemini_api_key)
        candidate_payloads = [
            _candidate_payload(candidate, habits, history) for candidate in candidates
        ]
        payload = {
            "watchlist": watchlist.model_dump(mode="json"),
            "candidates": candidate_payloads,
            "instruction": (
                "Return which candidate sale items are genuinely relevant to the watchlist. "
                "Prioritize items due for replenishment (long since last purchase relative "
                "to how often they're bought). Downweight items the user has repeatedly "
                "ignored. Flag prices at or below the user's demonstrated buy price "
                "(max_price_purchased_at) or historically good (historically_good_price) as "
                "strong deals even if the discount_pct looks modest. Do not apply "
                "max_list_size or min_discount_pct; code will apply those filters."
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


class DistillationReasons(BaseModel):
    promoted_reasons: dict[str, str] = {}
    demoted_reasons: dict[str, str] = {}


class PreferenceDistiller:
    """Optional Gemini commentary layer for the monthly distillation pass.

    The promote/demote/cap decisions themselves are made deterministically in
    app/distill.py; this only asks Gemini for friendlier reason text for the
    email digest, and falls back to the rule-based reasons on any failure.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def annotate(self, result: DistillationResult) -> DistillationResult:
        if not self.settings.gemini_api_key or (not result.promoted and not result.demoted):
            return result
        try:
            reasons = self._ask_gemini(result)
        except Exception:
            return result

        for promoted in result.promoted:
            reason = reasons.promoted_reasons.get(promoted.name)
            if reason:
                promoted.reason = reason
        for demoted in result.demoted:
            reason = reasons.demoted_reasons.get(demoted.name)
            if reason:
                demoted.reason = reason
        return result

    def _ask_gemini(self, result: DistillationResult) -> DistillationReasons:
        client = genai.Client(api_key=self.settings.gemini_api_key)
        promoted_payloads = [
            {
                "name": p.name,
                "good_price": str(p.good_price) if p.good_price is not None else None,
                "times_purchased": p.times_purchased,
            }
            for p in result.promoted
        ]
        demoted_payloads = [
            {"name": d.name, "ignored_streak": d.ignored_streak} for d in result.demoted
        ]
        payload = {
            "promoted": promoted_payloads,
            "demoted": demoted_payloads,
            "instruction": (
                "Write a one-sentence, friendly reason for each preference change, for a "
                "weekly grocery deal email. Keys of the returned maps must be the item name "
                "exactly as given."
            ),
        }
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=json.dumps(payload),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DistillationReasons.model_json_schema(),
            ),
        )
        raw = response.text or "{}"
        try:
            return DistillationReasons.model_validate_json(raw)
        except ValidationError:
            parsed: Any = json.loads(raw)
            return DistillationReasons.model_validate(parsed)


def _candidate_payload(
    candidate: CandidateDeal, habits: dict[str, HabitSummary], history: dict[str, list[Decimal]]
) -> dict[str, Any]:
    habit = habits.get(candidate.upc)
    item_history = history.get(candidate.upc, [])
    regular_price = str(candidate.regular_price) if candidate.regular_price is not None else None
    return {
        "upc": candidate.upc,
        "description": candidate.description,
        "category": candidate.category,
        "regular_price": regular_price,
        "promo_price": str(candidate.promo_price),
        "discount_pct": candidate.discount_pct,
        "matched_search_term": candidate.term,
        "size": candidate.size,
        "historically_good_price": is_historically_good_price(candidate.promo_price, item_history),
        "habit": habit.model_dump(mode="json") if habit else None,
    }
