from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tasktracker.db.models import Base
from tasktracker.services.task_service import TaskService


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=True, future=True)
    with SessionLocal() as s:
        yield s

@pytest.fixture
def svc(session: Session) -> TaskService:
    return TaskService(session)
