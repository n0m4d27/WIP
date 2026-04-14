from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tasktracker.db.models import Base


def get_engine(db_path: Path) -> Engine:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.resolve().as_posix()}"
    return create_engine(url, echo=False, future=True)


def init_schema(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=True avoids stale relationship collections after commit (e.g. empty todos stuck in identity map).
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=True, future=True)
