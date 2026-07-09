from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db import init_db, session_scope
from app.harvest import harvest
from app.models import Decision, Item, Published
from app.outputs.todoist import TodoistOutput


@pytest.mark.asyncio
async def test_harvest_records_decisions_and_outcomes(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    settings = Settings(database_url=database_url, todoist_api_token="token")
    init_db(database_url)

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Chicken thighs", category="Meat")
        session.add(item)
        session.flush()
        session.add(
            Published(
                item_id=item.id,
                price=Decimal("1.99"),
                output_mode="todoist",
                todoist_task_id="task-1",
            )
        )
        session.add(
            Published(
                item_id=item.id,
                price=Decimal("2.49"),
                output_mode="todoist",
                todoist_task_id="task-2",
            )
        )

    async def fake_harvest_outcomes(task_ids):
        assert set(task_ids) == {"task-1", "task-2"}
        return {"task-1": "purchased", "task-2": "ignored"}

    def fake_harvest_outcomes_method(self, task_ids):
        return fake_harvest_outcomes(task_ids)

    monkeypatch.setattr(TodoistOutput, "harvest_outcomes", fake_harvest_outcomes_method)

    await harvest(settings)

    with session_scope(database_url) as session:
        published = list(session.scalars(select(Published)))
        outcomes = {p.todoist_task_id: p.outcome for p in published}
        decisions = list(session.scalars(select(Decision)))

    assert outcomes == {"task-1": "purchased", "task-2": "ignored"}
    assert sorted(d.signal for d in decisions) == ["ignored", "purchased"]


@pytest.mark.asyncio
async def test_harvest_skips_already_harvested_and_missing_token(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)
    settings = Settings(database_url=database_url, todoist_api_token="")

    with session_scope(database_url) as session:
        item = Item(upc="upc-1", description="Chicken thighs", category="Meat")
        session.add(item)
        session.flush()
        session.add(
            Published(
                item_id=item.id,
                price=Decimal("1.99"),
                output_mode="todoist",
                todoist_task_id="task-1",
                outcome="purchased",
            )
        )

    await harvest(settings)

    with session_scope(database_url) as session:
        decisions = list(session.scalars(select(Decision)))

    assert decisions == []
