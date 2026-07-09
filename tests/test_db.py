import sqlite3
from decimal import Decimal

from sqlalchemy import select

from app.db import init_db, session_scope
from app.models import Published


def test_init_db_creates_missing_sqlite_parent(tmp_path):
    database_path = tmp_path / "nested" / "app.db"

    init_db(f"sqlite:///{database_path}")

    assert database_path.exists()


def test_init_db_adds_missing_columns_to_existing_tables(tmp_path):
    """Simulates a database created before todoist_task_id/outcome existed."""
    database_path = tmp_path / "app.db"
    database_url = f"sqlite:///{database_path}"

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE published (
            id INTEGER PRIMARY KEY,
            run_date DATETIME,
            item_id INTEGER,
            price NUMERIC(10, 2),
            output_mode VARCHAR(64)
        )
        """
    )
    connection.execute(
        "INSERT INTO published (run_date, item_id, price, output_mode) VALUES "
        "('2026-01-01 00:00:00', 1, 1.99, 'todoist')"
    )
    connection.commit()
    connection.close()

    init_db(database_url)

    with session_scope(database_url) as session:
        rows = list(session.scalars(select(Published)))

    assert len(rows) == 1
    assert rows[0].price == Decimal("1.99")
    assert rows[0].todoist_task_id is None
    assert rows[0].outcome is None