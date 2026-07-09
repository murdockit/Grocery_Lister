import math
from decimal import Decimal

from app.deals import CandidateDeal, SelectedDeal
from app.watchlist import Watchlist

GOOD_PRICE_PERCENTILE = 25


def passes_discount_threshold(candidate: CandidateDeal, min_discount_pct: int) -> bool:
    if candidate.regular_price is None:
        return False
    return candidate.discount_pct >= min_discount_pct


def promo_percentile(promos: list[Decimal], percentile: float) -> Decimal | None:
    if not promos:
        return None
    ordered = sorted(promos)
    rank = max(1, math.ceil(percentile / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def is_historically_good_price(
    promo_price: Decimal,
    historical_promos: list[Decimal],
    percentile: float = GOOD_PRICE_PERCENTILE,
) -> bool:
    threshold = promo_percentile(historical_promos, percentile)
    if threshold is None:
        return False
    return promo_price <= threshold


def fallback_select(
    candidates: list[CandidateDeal],
    watchlist: Watchlist,
    history: dict[str, list[Decimal]] | None = None,
) -> list[SelectedDeal]:
    history = history or {}
    selected: list[SelectedDeal] = []
    watch_terms = [item.name.lower() for item in watchlist.items]
    category_terms = [category.lower() for category in watchlist.categories]

    for candidate in candidates:
        category = candidate.category or ""
        if watchlist.is_blocked(candidate.description) or watchlist.is_blocked(category):
            continue

        haystack = f"{candidate.description} {category}".lower()
        matched = next((term for term in watch_terms if term in haystack), None)
        if matched is None:
            matched = next((term for term in category_terms if term in haystack), None)
        if matched is None:
            continue

        item_history = history.get(candidate.upc, [])
        historically_good = is_historically_good_price(candidate.promo_price, item_history)

        watch_item = next((item for item in watchlist.items if item.name.lower() == matched), None)
        passes_discount = passes_discount_threshold(candidate, watchlist.min_discount_pct)
        if watch_item and watch_item.good_price is not None:
            if candidate.promo_price > Decimal(watch_item.good_price) and not historically_good:
                continue
        elif not passes_discount and not historically_good:
            continue

        reason = "Matched by local fallback rules."
        if historically_good:
            reason += f" At/below the {GOOD_PRICE_PERCENTILE}th percentile of its promo history."

        selected.append(
            SelectedDeal(candidate=candidate, matched_watchlist_item=matched, reason=reason)
        )

    def sort_key(deal: SelectedDeal) -> tuple[int, Decimal]:
        return (deal.candidate.discount_pct, -deal.candidate.promo_price)

    selected.sort(key=sort_key, reverse=True)
    return selected[: watchlist.max_list_size]
