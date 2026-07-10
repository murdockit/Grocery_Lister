from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class CandidateDeal:
    upc: str
    description: str
    category: str | None
    regular_price: Decimal | None
    promo_price: Decimal
    term: str
    size: str | None = None
    location_id: str | None = None

    @property
    def discount_pct(self) -> int:
        if not self.regular_price or self.regular_price <= 0:
            return 0
        discount = (self.regular_price - self.promo_price) / self.regular_price * Decimal("100")
        return int(discount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class SelectedDeal:
    candidate: CandidateDeal
    matched_watchlist_item: str
    reason: str
    confidence: float | None = None
    likelihood: str | None = None

    @property
    def task_content(self) -> str:
        if self.candidate.regular_price:
            regular = f"reg ${self.candidate.regular_price:.2f}"
        else:
            regular = "reg n/a"
        return (
            f"{self.candidate.description} - ${self.candidate.promo_price:.2f} "
            f"({regular}, {self.candidate.discount_pct}% off)"
        )
