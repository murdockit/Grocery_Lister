from app.db import init_db


def test_init_db_creates_missing_sqlite_parent(tmp_path):
    database_path = tmp_path / "nested" / "app.db"

    init_db(f"sqlite:///{database_path}")

    assert database_path.exists()