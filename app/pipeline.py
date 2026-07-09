from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import init_db, session_scope
from app.deals import CandidateDeal, SelectedDeal
from app.kroger import KrogerClient
from app.llm import DealSelector
from app.models import Item, PriceHistory, Published, Run, utc_now
from app.outputs.email import EmailOutput
from app.outputs.todoist import TodoistOutput
from app.watchlist import Watchlist, load_watchlist


async def run_pipeline(settings: Settings | None = None) -> list[SelectedDeal]:
    settings = settings or get_settings()
    init_db(settings.database_url)
    watchlist = load_watchlist(settings.watchlist_path)
    run_id = _start_run(settings)

    try:
        candidates = await KrogerClient(settings).get_promo_deals(watchlist.search_terms)
        selected = DealSelector(settings).select(candidates, watchlist)

        with session_scope(settings.database_url) as session:
            _record_prices(session, candidates)

        await _publish(settings, selected)

        with session_scope(settings.database_url) as session:
            _record_published(session, selected, settings.output_modes)
            run = session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"Run {run_id} disappeared before completion")
            run.status = "success"
            run.finished_at = utc_now()
        return selected
    except Exception as exc:
        _mark_run_failed(settings, run_id, exc)
        if settings.smtp_host and settings.notify_email:
            await EmailOutput(settings).send_failure(str(exc))
        raise


def _start_run(settings: Settings) -> int:
    with session_scope(settings.database_url) as session:
        run = Run()
        session.add(run)
        session.flush()
        return run.id


def _mark_run_failed(settings: Settings, run_id: int, exc: Exception) -> None:
    with session_scope(settings.database_url) as session:
        run = session.get(Run, run_id)
        if run is not None:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utc_now()


def _record_prices(session: Session, candidates: list[CandidateDeal]) -> None:
    for candidate in candidates:
        item = session.scalar(select(Item).where(Item.upc == candidate.upc))
        if item is None:
            item = Item(
                upc=candidate.upc,
                description=candidate.description,
                category=candidate.category,
            )
            session.add(item)
            session.flush()
        else:
            item.description = candidate.description
            item.category = candidate.category
        session.add(
            PriceHistory(
                item_id=item.id,
                regular_price=candidate.regular_price,
                promo_price=candidate.promo_price,
            )
        )


def _record_published(session: Session, selected: list[SelectedDeal], output_modes: list[str]) -> None:
    for deal in selected:
        item = session.scalar(select(Item).where(Item.upc == deal.candidate.upc))
        if item is None:
            continue
        for mode in output_modes:
            session.add(
                Published(
                    item_id=item.id,
                    price=Decimal(deal.candidate.promo_price),
                    output_mode=mode,
                )
            )


async def _publish(settings: Settings, selected: list[SelectedDeal]) -> None:
    for mode in settings.output_modes:
        if mode == "todoist":
            await TodoistOutput(settings).publish(selected)
        elif mode == "email":
            await EmailOutput(settings).publish(selected)
        elif mode in {"keep_api", "tasks"}:
            raise NotImplementedError(f"Output mode {mode!r} is planned for Phase 3")
        else:
            raise ValueError(f"Unknown OUTPUT_MODE value: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Weekly Deal Watcher pipeline.")
    parser.add_argument("--now", action="store_true", help="Run immediately and print selected deals.")
    args = parser.parse_args()
    if not args.now:
        parser.error("Use --now for a one-shot run, or python -m app.main for the scheduler.")
    selected = asyncio.run(run_pipeline())
    for deal in selected:
        print(deal.task_content)


if __name__ == "__main__":
    main()
