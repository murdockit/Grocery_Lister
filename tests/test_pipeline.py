import pytest

from app.config import Settings
from app.db import session_scope
from app.models import AppState
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
