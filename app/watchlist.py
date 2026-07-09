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
    blocklist: list[str] = Field(default_factory=list)
    max_list_size: int = Field(default=15, ge=1)
    min_discount_pct: int = Field(default=15, ge=0, le=100)

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, categories: list[str]) -> list[str]:
        return [category.strip() for category in categories if category.strip()]

    @field_validator("blocklist")
    @classmethod
    def normalize_blocklist(cls, blocklist: list[str]) -> list[str]:
        return [entry.strip() for entry in blocklist if entry.strip()]

    @property
    def blocked_set(self) -> set[str]:
        return {entry.lower() for entry in self.blocklist}

    def is_blocked(self, name: str) -> bool:
        haystack = name.lower()
        return any(blocked in haystack for blocked in self.blocked_set)

    @property
    def search_terms(self) -> list[str]:
        terms = [item.name for item in self.items] + self.categories
        deduped = dict.fromkeys(term.strip() for term in terms if term.strip())
        return [term for term in deduped if not self.is_blocked(term)]


def load_watchlist(path: Path) -> Watchlist:
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return Watchlist.model_validate(raw)
