from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tasktracker.db.models import Base


def default_db_path() -> Path:
    raw = os.environ.get("WIP_DB_PATH")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".wip_tasktracker" / "tasks.db"


def get_engine(db_path: Path | None = None) -> Engine:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.as_posix()}"
    return create_engine(url, echo=False, future=True)


def init_schema(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=True avoids stale relationship collections after commit (e.g. empty todos stuck in identity map).
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=True, future=True)
