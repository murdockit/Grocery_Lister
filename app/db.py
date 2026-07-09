from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
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
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    """create_all() only adds missing tables, not columns on ones that already
    exist. Add any new nullable columns in place so existing databases (with
    real purchase history) upgrade without needing a migration tool."""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'
                conn.execute(text(ddl))


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
