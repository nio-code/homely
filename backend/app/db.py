from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine
from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def _migrate_sqlite() -> None:
    """Lightweight column-adds for SQLite. Avoids needing alembic for v1."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(listing)")).fetchall()}
        if cols and "status" not in cols:
            conn.execute(text("ALTER TABLE listing ADD COLUMN status VARCHAR DEFAULT 'approved'"))
            conn.execute(text("UPDATE listing SET status = 'approved' WHERE status IS NULL"))


def init_db() -> None:
    from . import models  # noqa: F401 — register models
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite()


def get_session():
    with Session(engine) as session:
        yield session
