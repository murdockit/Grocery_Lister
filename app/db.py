from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

_engine_cache = {}


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database = url.database
    if not database or database == ":memory:" or url.query.get("uri") == "true":
        return

    parent = Path(database).expanduser().parent
    if parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)


def get_engine(database_url: str):
    if database_url not in _engine_cache:
        _ensure_sqlite_parent_dir(database_url)
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        _engine_cache[database_url] = create_engine(database_url, connect_args=connect_args)
    return _engine_cache[database_url]


def init_db(database_url: str) -> None:
    Base.metadata.create_all(get_engine(database_url))


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    factory = sessionmaker(bind=get_engine(database_url), expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
