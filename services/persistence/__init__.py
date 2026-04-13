"""Persistence layer — SQLite-backed SQLAlchemy session factory."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///float_planner.db",
)

# echo=False keeps logs clean; set DATABASE_ECHO=1 env var for SQL logging
_engine = create_engine(
    _DATABASE_URL,
    connect_args={"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {},
    echo=os.environ.get("DATABASE_ECHO", "0") == "1",
)

_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def _apply_migrations() -> None:
    """Add columns that may be missing from older database files.

    SQLAlchemy's create_all() creates new tables but won't ALTER existing ones.
    Each migration is guarded by a try/except so it's safe to run repeatedly.
    """
    migrations = [
        "ALTER TABLE projects ADD COLUMN asana_project_gid VARCHAR(128)",
        "ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id)",
        "ALTER TABLE tasks ADD COLUMN hierarchy_depth INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE day_allocations ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0",
    ]
    with _engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                conn.rollback()


def create_all_tables() -> None:
    """Create all tables (idempotent — safe to call at startup)."""
    Base.metadata.create_all(bind=_engine)
    _apply_migrations()


def seed_demo_data() -> None:
    """Populate demo data if the tables are empty."""
    from .seed import seed_demo_data as _seed
    with get_db_session() as session:
        _seed(session)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and commit/rollback automatically."""
    session: Session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["create_all_tables", "seed_demo_data", "get_db_session", "Base"]
