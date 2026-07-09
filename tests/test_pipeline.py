from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db import session_scope
from app.models import AppState, Preference, Published
from app.outputs.email import EmailOutput
from app.pipeline import run_pipeline


@pytest.mark.asyncio
async def test_pipeline_mock_kroger_selects_deals(tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(
        """
items:
  - name: chicken thighs
    good_price: 2.00
  - name: coffee
max_list_size: 5
min_discount_pct: 15
""",
        encoding="utf-8",
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        watchlist_path=watchlist_path,
        mock_kroger=True,
        output_mode="",
    )

    selected = await run_pipeline(settings)

    assert [deal.candidate.upc for deal in selected] == ["0001111011111", "0001111033333"]

@pytest.mark.asyncio
async def test_pipeline_allows_publish_to_write_state(monkeypatch, tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(
        """
items:
  - name: chicken thighs
    good_price: 2.00
max_list_size: 1
min_discount_pct: 15
""",
        encoding="utf-8",
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        watchlist_path=watchlist_path,
        mock_kroger=True,
        output_mode="todoist",
    )

    async def publish(settings, selected):
        with session_scope(settings.database_url) as session:
            session.add(AppState(key="publish_write", value=str(len(selected))))

    monkeypatch.setattr("app.pipeline._publish", publish)

    selected = await run_pipeline(settings)

    assert len(selected) == 1


@pytest.mark.asyncio
async def test_pipeline_syncs_seed_preferences_and_records_task_ids(monkeypatch, tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text(
        """
items:
  - name: chicken thighs
    good_price: 2.00
max_list_size: 1
min_discount_pct: 15
""",
        encoding="utf-8",
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        watchlist_path=watchlist_path,
        mock_kroger=True,
        output_mode="todoist",
    )

    async def fake_publish(settings, selected):
        return {deal.candidate.upc: f"task-{deal.candidate.upc}" for deal in selected}

    monkeypatch.setattr("app.pipeline._publish", fake_publish)

    selected = await run_pipeline(settings)

    with session_scope(settings.database_url) as session:
        prefs = list(session.scalars(select(Preference).where(Preference.source == "seed")))
        published = list(session.scalars(select(Published)))

    assert [p.keyword for p in prefs] == ["chicken thighs"]
    assert prefs[0].good_price == Decimal("2.00")
    assert len(published) == len(selected) == 1
    assert published[0].todoist_task_id == f"task-{selected[0].candidate.upc}"
    assert published[0].outcome is None


@pytest.mark.asyncio
async def test_pipeline_ingests_active_learned_preference_terms(monkeypatch, tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text("items: []\n", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        watchlist_path=watchlist_path,
        mock_kroger=True,
        output_mode="",
    )

    from app.db import init_db

    init_db(settings.database_url)
    with session_scope(settings.database_url) as session:
        session.add(Preference(name="coffee", keyword="coffee", source="learned", active=True))

    captured_terms = {}

    from app.kroger import KrogerClient

    original_get_promo_deals = KrogerClient.get_promo_deals

    async def spy_get_promo_deals(self, terms):
        captured_terms["terms"] = list(terms)
        return await original_get_promo_deals(self, terms)

    monkeypatch.setattr(KrogerClient, "get_promo_deals", spy_get_promo_deals)

    await run_pipeline(settings)

    assert captured_terms["terms"] == ["coffee"]


@pytest.mark.asyncio
async def test_failure_email_only_sent_after_consecutive_threshold(monkeypatch, tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text("items: []\n", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        watchlist_path=watchlist_path,
        mock_kroger=True,
        output_mode="",
        smtp_host="smtp.example.com",
        notify_email="you@example.com",
    )

    async def boom(settings, selected):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.pipeline._publish", boom)

    sent: list[str] = []

    async def fake_send_failure(self, error):
        sent.append(error)

    monkeypatch.setattr(EmailOutput, "send_failure", fake_send_failure)

    with pytest.raises(RuntimeError):
        await run_pipeline(settings)
    assert sent == []  # first failure: no alert yet

    with pytest.raises(RuntimeError):
        await run_pipeline(settings)
    assert len(sent) == 1  # second consecutive failure: alert fires

    with pytest.raises(RuntimeError):
        await run_pipeline(settings)
    assert len(sent) == 2  # keeps alerting on every failure past the threshold


@pytest.mark.asyncio
async def test_failure_streak_resets_after_a_success(monkeypatch, tmp_path):
    watchlist_path = tmp_path / "watchlist.yaml"
    watchlist_path.write_text("items: []\n", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        watchlist_path=watchlist_path,
        mock_kroger=True,
        output_mode="",
        smtp_host="smtp.example.com",
        notify_email="you@example.com",
    )

    sent: list[str] = []
    should_fail = True

    async def fake_send_failure(self, error):
        sent.append(error)

    async def maybe_boom(settings, selected):
        if should_fail:
            raise RuntimeError("boom")

    monkeypatch.setattr(EmailOutput, "send_failure", fake_send_failure)
    monkeypatch.setattr("app.pipeline._publish", maybe_boom)

    with pytest.raises(RuntimeError):
        await run_pipeline(settings)
    assert sent == []  # first failure: no alert

    should_fail = False
    await run_pipeline(settings)  # succeeds, resets the streak

    should_fail = True
    with pytest.raises(RuntimeError):
        await run_pipeline(settings)
    assert sent == []  # only one failure since the last success
