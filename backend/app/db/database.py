"""Database engine and session factory.

Everything goes through SQLAlchemy using DATABASE_URL, so moving from SQLite to
PostgreSQL is a configuration change (plus installing a driver such as psycopg).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def create_db_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        # The agent runs in a worker thread; SQLite must allow cross-thread use.
        connect_args["check_same_thread"] = False
    return create_engine(database_url, connect_args=connect_args)


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine = create_db_engine(database_url)
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_tables(self) -> None:
        from app.db import models  # noqa: F401  (registers the tables on Base.metadata)

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """A unit of work: commits on success, rolls back on error."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
