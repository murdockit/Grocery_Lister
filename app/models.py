from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    upc: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    prices: Mapped[list[PriceHistory]] = relationship(back_populates="item")


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    regular_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    promo_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    item: Mapped[Item] = relationship(back_populates="prices")


class Published(Base):
    __tablename__ = "published"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    output_mode: Mapped[str] = mapped_column(String(64))

    item: Mapped[Item] = relationship()


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppState(Base):
    __tablename__ = "app_state"
    __table_args__ = (UniqueConstraint("key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[str] = mapped_column(Text)
