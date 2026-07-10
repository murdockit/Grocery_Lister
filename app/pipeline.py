from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import init_db, session_scope
from app.deals import CandidateDeal, SelectedDeal
from app.distill import DistillationResult, run_distillation, should_run_distillation
from app.habits import build_habit_summary, build_price_history
from app.harvest import harvest
from app.kroger import KrogerClient
from app.llm import DealSelector, PreferenceDistiller
from app.models import Item, PriceHistory, Published, Run, utc_now
from app.outputs.email import EmailOutput
from app.outputs.todoist import TodoistOutput
from app.preferences import active_learned_terms, sync_seed_preferences
from app.watchlist import Watchlist, load_watchlist

FAILURE_ALERT_THRESHOLD = 2


async def run_pipeline(settings: Settings | None = None) -> list[SelectedDeal]:
    settings = settings or get_settings()
    init_db(settings.database_url)
    watchlist = load_watchlist(settings.watchlist_path)
    run_id = _start_run(settings)

    try:
        await harvest(settings)

        with session_scope(settings.database_url) as session:
            sync_seed_preferences(session, watchlist)
            learned_terms = active_learned_terms(session, watchlist)
            search_terms = list(dict.fromkeys(watchlist.search_terms + learned_terms))

        candidates = await KrogerClient(settings).get_promo_deals(search_terms)

        with session_scope(settings.database_url) as session:
            upcs = [candidate.upc for candidate in candidates]
            habits = build_habit_summary(session, upcs)
            history = build_price_history(session, upcs)

        selected = DealSelector(settings).select(candidates, watchlist, habits, history)

        with session_scope(settings.database_url) as session:
            _record_prices(session, candidates)

        task_ids = await _publish(settings, selected) or {}

        with session_scope(settings.database_url) as session:
            _record_published(session, selected, settings.output_modes, task_ids)

        await _maybe_distill(settings, watchlist)

        with session_scope(settings.database_url) as session:
            run = session.get(Run, run_id)
            if run is None:
                raise RuntimeError(f"Run {run_id} disappeared before completion")
            run.status = "success"
            run.finished_at = utc_now()
        return selected
    except Exception as exc:
        _mark_run_failed(settings, run_id, exc)
        with session_scope(settings.database_url) as session:
            consecutive_failures = _consecutive_failed_runs(session)
        should_alert = consecutive_failures >= FAILURE_ALERT_THRESHOLD
        if should_alert and settings.smtp_host and settings.notify_email:
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


def _consecutive_failed_runs(session: Session) -> int:
    """Trailing run of status='failed', most recent first. Resets to 0 on any
    success, so a single transient blip doesn't trigger an alert email."""
    runs = session.scalars(select(Run).order_by(Run.started_at.desc()))
    count = 0
    for run in runs:
        if run.status != "failed":
            break
        count += 1
    return count


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


def _record_published(
    session: Session,
    selected: list[SelectedDeal],
    output_modes: list[str],
    task_ids: dict[str, str],
) -> None:
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
                    todoist_task_id=task_ids.get(deal.candidate.upc) if mode == "todoist" else None,
                )
            )


async def _publish(settings: Settings, selected: list[SelectedDeal]) -> dict[str, str]:
    task_ids: dict[str, str] = {}
    for mode in settings.output_modes:
        if mode == "todoist":
            task_ids = await TodoistOutput(settings).publish(selected)
        elif mode == "email":
            await EmailOutput(settings).publish(selected)
        elif mode in {"keep_api", "tasks"}:
            raise NotImplementedError(f"Output mode {mode!r} is planned for Phase 3")
        else:
            raise ValueError(f"Unknown OUTPUT_MODE value: {mode}")
    return task_ids


async def _maybe_distill(settings: Settings, watchlist: Watchlist) -> None:
    result: DistillationResult | None = None
    with session_scope(settings.database_url) as session:
        success_count_query = select(func.count()).select_from(Run).where(Run.status == "success")
        successful_runs = session.scalar(success_count_query) or 0
        if should_run_distillation(successful_runs + 1):
            result = run_distillation(session, watchlist)

    if result is None or (not result.promoted and not result.demoted):
        return
    result = PreferenceDistiller(settings).annotate(result)
    await EmailOutput(settings).send_learning_summary(result.promoted, result.demoted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Weekly Deal Watcher pipeline.")
    parser.add_argument(
        "--now", action="store_true", help="Run immediately and print selected deals."
    )
    args = parser.parse_args()
    if not args.now:
        parser.error("Use --now for a one-shot run, or python -m app.main for the scheduler.")
    selected = asyncio.run(run_pipeline())
    for deal in selected:
        print(deal.task_content)


if __name__ == "__main__":
    main()
