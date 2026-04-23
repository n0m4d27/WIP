"""Attachments storage + vault crypto (plan 04)."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from tasktracker.db.session import get_engine, init_schema, make_session_factory
from tasktracker.db.schema_upgrade import upgrade_schema
from tasktracker.services.task_service import TaskService
from tasktracker.vault_attachments_crypto import (
    decrypt_attachments_folder,
    encrypt_attachments_folder,
)


@pytest.fixture
def fernet() -> Fernet:
    return Fernet(Fernet.generate_key())


def test_encrypt_decrypt_roundtrip(tmp_path: Path, fernet: Fernet) -> None:
    vault = tmp_path
    f = vault / "attachments" / "1" / "dummy.txt"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"payload-bytes")
    encrypt_attachments_folder(vault, fernet)
    assert not f.is_file()
    enc = f.with_name(f.name + ".enc")
    assert enc.is_file()
    assert enc.read_bytes() != b"payload-bytes"
    decrypt_attachments_folder(vault, fernet)
    assert f.is_file()
    assert f.read_bytes() == b"payload-bytes"
    assert not enc.is_file()


def test_decrypt_drops_stale_enc_when_plain_exists(tmp_path: Path, fernet: Fernet) -> None:
    vault = tmp_path
    plain = vault / "attachments" / "2" / "a.pdf"
    plain.parent.mkdir(parents=True)
    plain.write_bytes(b"x")
    stale = plain.with_name(plain.name + ".enc")
    stale.write_bytes(b"stale")
    decrypt_attachments_folder(vault, fernet)
    assert plain.is_file()
    assert not stale.exists()


def test_add_remove_attachment_row_and_file(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    engine = get_engine(db)
    init_schema(engine)
    upgrade_schema(engine)
    factory = make_session_factory(engine)
    vault = tmp_path
    src = tmp_path / "src.bin"
    src.write_bytes(b"abc123")

    with factory() as s:
        svc = TaskService(s, vault)
        t = svc.create_task(title="t1", received_date=dt.date(2026, 1, 1))
        att, err = svc.add_task_attachment(t.id, src)
        assert err is None
        assert att is not None
        abs_p = vault / att.storage_relpath.replace("/", os.sep)
        assert abs_p.is_file()
        assert abs_p.read_bytes() == b"abc123"
        aid = att.id

    with factory() as s:
        svc = TaskService(s, vault)
        assert svc.remove_task_attachment(aid)
        assert not abs_p.exists()


def test_delete_task_purges_attachment_folder(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    engine = get_engine(db)
    init_schema(engine)
    upgrade_schema(engine)
    factory = make_session_factory(engine)
    vault = tmp_path
    src = tmp_path / "src.bin"
    src.write_bytes(b"z")

    with factory() as s:
        svc = TaskService(s, vault)
        t = svc.create_task(title="t2", received_date=dt.date(2026, 1, 2))
        svc.add_task_attachment(t.id, src)
        tid = t.id

    task_dir = vault / "attachments" / str(tid)
    assert task_dir.is_dir()

    with factory() as s:
        svc = TaskService(s, vault)
        assert svc.delete_task(tid)

    assert not task_dir.exists()


def test_oversize_requires_confirm(tmp_path: Path) -> None:
    db = tmp_path / "tasks.db"
    engine = get_engine(db)
    init_schema(engine)
    upgrade_schema(engine)
    factory = make_session_factory(engine)
    vault = tmp_path
    big = vault / "big.bin"
    big.write_bytes(b"x" * (TaskService.ATTACHMENT_SOFT_CAP_BYTES + 1))

    with factory() as s:
        svc = TaskService(s, vault)
        t = svc.create_task(title="t3", received_date=dt.date(2026, 1, 3))
        att, err = svc.add_task_attachment(t.id, big, confirm_large=False)
        assert att is None
        assert err == "oversize"
        att2, err2 = svc.add_task_attachment(t.id, big, confirm_large=True)
        assert err2 is None
        assert att2 is not None
