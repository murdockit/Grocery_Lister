from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class WatchItem(BaseModel):
    name: str
    good_price: Decimal | None = None
    unit: str | None = None


class Watchlist(BaseModel):
    items: list[WatchItem] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    max_list_size: int = Field(default=15, ge=1)
    min_discount_pct: int = Field(default=15, ge=0, le=100)

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, categories: list[str]) -> list[str]:
        return [category.strip() for category in categories if category.strip()]

    @property
    def search_terms(self) -> list[str]:
        terms = [item.name for item in self.items] + self.categories
        return list(dict.fromkeys(term.strip() for term in terms if term.strip()))


def load_watchlist(path: Path) -> Watchlist:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return Watchlist.model_validate(raw)
