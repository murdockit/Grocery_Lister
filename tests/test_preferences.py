from decimal import Decimal

from sqlalchemy import select

from app.db import init_db, session_scope
from app.models import Preference
from app.preferences import active_learned_terms, sync_seed_preferences
from app.watchlist import WatchItem, Watchlist


def test_sync_seed_preferences_upserts_and_deactivates_stale(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    watchlist = Watchlist(items=[WatchItem(name="chicken thighs", good_price=Decimal("2.00"))])
    with session_scope(database_url) as session:
        sync_seed_preferences(session, watchlist)

    with session_scope(database_url) as session:
        prefs = list(session.scalars(select(Preference)))
        assert len(prefs) == 1
        assert prefs[0].source == "seed"
        assert prefs[0].active is True
        assert prefs[0].good_price == Decimal("2.00")

    watchlist_without_item = Watchlist(items=[])
    with session_scope(database_url) as session:
        sync_seed_preferences(session, watchlist_without_item)

    with session_scope(database_url) as session:
        prefs = list(session.scalars(select(Preference)))
        assert len(prefs) == 1
        assert prefs[0].active is False


def test_sync_seed_preferences_deactivates_blocklisted_learned_rows(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        session.add(Preference(name="liver", keyword="liver", source="learned", active=True))

    watchlist = Watchlist(items=[], blocklist=["liver"])
    with session_scope(database_url) as session:
        sync_seed_preferences(session, watchlist)

    with session_scope(database_url) as session:
        pref = session.scalar(select(Preference).where(Preference.keyword == "liver"))
        assert pref.active is False


def test_active_learned_terms_excludes_inactive_and_blocklisted(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    init_db(database_url)

    with session_scope(database_url) as session:
        session.add(Preference(name="bacon", keyword="bacon", source="learned", active=True))
        session.add(Preference(name="liver", keyword="liver", source="learned", active=True))
        session.add(
            Preference(name="old thing", keyword="old thing", source="learned", active=False)
        )

    watchlist = Watchlist(items=[], blocklist=["liver"])
    with session_scope(database_url) as session:
        terms = active_learned_terms(session, watchlist)

    assert terms == ["bacon"]
