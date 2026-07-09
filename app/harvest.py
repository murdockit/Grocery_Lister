from __future__ import annotations

from sqlalchemy import select

from app.config import Settings
from app.db import session_scope
from app.models import Decision, Published, utc_now
from app.outputs.todoist import TodoistOutput


def _pending_published(session) -> list[Published]:
    query = select(Published).where(
        Published.todoist_task_id.isnot(None),
        Published.outcome.is_(None),
    )
    return list(session.scalars(query))


async def harvest(settings: Settings) -> None:
    """Turn last run's un-checked-off Todoist tasks into purchase/ignore signals.

    Must run before this week's publish() call, which clears the project and
    would otherwise destroy the evidence of what got checked off.
    """
    if not settings.todoist_api_token:
        return

    with session_scope(settings.database_url) as session:
        pending = _pending_published(session)
        task_ids = [pub.todoist_task_id for pub in pending if pub.todoist_task_id]

    if not task_ids:
        return

    outcomes = await TodoistOutput(settings).harvest_outcomes(task_ids)
    if not outcomes:
        return

    with session_scope(settings.database_url) as session:
        for pub in _pending_published(session):
            signal = outcomes.get(pub.todoist_task_id)
            if signal is None:
                continue
            pub.outcome = signal
            session.add(
                Decision(item_id=pub.item_id, signal=signal, price=pub.price, run_date=utc_now())
            )
