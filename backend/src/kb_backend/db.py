from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        # expire_on_commit=False: objects stay usable after commit (needed since
        # FastAPI serializes the response after the request's `yield` resumes,
        # by which point the session has already committed). The tradeoff:
        # server-generated columns (created_at/updated_at, and any DB default)
        # keep whatever value was last loaded/set in Python and are NOT
        # refreshed from the row MySQL actually wrote. Future CRUD issues
        # (#2-5) that return a freshly-created row's timestamps to the client
        # must `db.refresh(obj)` after commit to get the real server value.
        # Found by the Kimi review gate on PR #17.
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a Session, always closed after the request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
