from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base


_engine_cache = {}


def get_engine(database_url: str):
    if database_url not in _engine_cache:
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
