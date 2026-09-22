

from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool, StaticPool
from shared.config import get_settings
from shared.logging_config import get_logger

logger = get_logger("app.db.session")

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None

def get_engine() -> Engine:
    """Returns or initializes global SQLAlchemy Engine singleton with WAL & busy timeout."""
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    db_url = settings.effective_database_url

    logger.debug(f"Initializing database engine: {settings.get_masked_dict().get('effective_database_url', db_url)}")

    if db_url.startswith("sqlite"):
        engine_args: Dict[str, Any] = {
            "connect_args": {"check_same_thread": False, "timeout": 30.0},
        }
        if ":memory:" in db_url:
            engine_args["poolclass"] = StaticPool
            _engine = create_engine(db_url, **engine_args)
            try:
                from shared.db.models import Base
                Base.metadata.create_all(bind=_engine)
            except Exception:
                pass
        else:
            _engine = create_engine(db_url, **engine_args)


        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()
    else:
        _engine = create_engine(
            db_url,
            poolclass=QueuePool,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True
        )

    return _engine

def get_sessionmaker() -> sessionmaker:
    """Returns global thread-safe SessionLocal factory."""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic commit, rollback, and cleanup."""
    sm = get_sessionmaker()
    session: Session = sm()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Transaction rollback executed due to error: {exc}")
        raise
    finally:
        session.close()

def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency for request-scoped database sessions."""
    sm = get_sessionmaker()
    session: Session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def reset_engine() -> None:
    """Resets engine and session factory singletons (useful for isolated unit testing)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
