"""
SQLAlchemy engine/session wiring. One engine per process, sessions handed out
per-request via the `get_db` FastAPI dependency (see api/deps.py).
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import settings


class Base(DeclarativeBase):
    pass


# `future=True`/2.0 style is the SQLAlchemy default from 2.x, kept explicit
# connect_args only matters for SQLite (used in tests), ignored by Postgres.
_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
