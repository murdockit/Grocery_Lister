from decimal import Decimal

from app.deals import CandidateDeal, SelectedDeal
from app.watchlist import Watchlist


def passes_discount_threshold(candidate: CandidateDeal, min_discount_pct: int) -> bool:
    if candidate.regular_price is None:
        return False
    return candidate.discount_pct >= min_discount_pct


def fallback_select(candidates: list[CandidateDeal], watchlist: Watchlist) -> list[SelectedDeal]:
    selected: list[SelectedDeal] = []
    watch_terms = [item.name.lower() for item in watchlist.items]
    category_terms = [category.lower() for category in watchlist.categories]

    for candidate in candidates:
        haystack = f"{candidate.description} {candidate.category or ''}".lower()
        matched = next((term for term in watch_terms if term in haystack), None)
        if matched is None:
            matched = next((term for term in category_terms if term in haystack), None)
        if matched is None:
            continue

        watch_item = next((item for item in watchlist.items if item.name.lower() == matched), None)
        if watch_item and watch_item.good_price is not None:
            if candidate.promo_price > Decimal(watch_item.good_price):
                continue
        elif not passes_discount_threshold(candidate, watchlist.min_discount_pct):
            continue

        selected.append(
            SelectedDeal(
                candidate=candidate,
                matched_watchlist_item=matched,
                reason="Matched by local fallback rules.",
            )
        )

    selected.sort(key=lambda deal: (deal.candidate.discount_pct, -deal.candidate.promo_price), reverse=True)
    return selected[: watchlist.max_list_size]
