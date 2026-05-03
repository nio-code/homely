from sqlmodel import SQLModel, Session, create_engine
from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def init_db() -> None:
    from . import models  # noqa: F401 — register models
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
