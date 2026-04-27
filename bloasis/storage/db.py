"""SQLAlchemy engine factory and DDL bootstrap."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event

from bloasis.storage.schema import metadata

DEFAULT_DB_PATH = Path("./bloasis.db")


def _enable_sqlite_pragmas(engine: Engine) -> None:
    """Apply SQLite pragmas suitable for our workload.

    - foreign_keys: enforce FK constraints (off by default in SQLite).
    - journal_mode=WAL: better concurrent read while writing.
    - synchronous=NORMAL: safe with WAL, faster writes.
    """

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn: object, _conn_record: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_engine(db_path: Path | None = None) -> Engine:
    """Build a SQLAlchemy engine for the SQLite database.

    Resolution order: explicit `db_path` > env BLOASIS_DB_PATH > DEFAULT_DB_PATH.
    """
    if db_path is None:
        env = os.environ.get("BLOASIS_DB_PATH")
        db_path = Path(env) if env else DEFAULT_DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, future=True)
    _enable_sqlite_pragmas(engine)
    return engine


def create_all(engine: Engine) -> None:
    """Create all tables defined in `bloasis.storage.schema`.

    Idempotent — existing tables are not modified. For schema migrations
    use a dedicated migration tool (alembic in v2 when complexity demands).
    """
    metadata.create_all(engine)
