"""Encrypt / decrypt the vault ``attachments/`` tree at lock / unlock (plan 04).

While the vault is open, files are stored as plaintext under
``<vault>/attachments/<task_id>/…``. On shutdown each file is replaced by a
Fernet ciphertext sibling ``<name>.enc`` using the same key as ``tasks.db``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from cryptography.fernet import Fernet

from tasktracker.paths import attachments_dir
from tasktracker.security.crypto import decrypt_file, encrypt_file

_ENC = ".enc"
_TMP = ".tmp"


def _is_encrypted_path(p: Path) -> bool:
    return p.is_file() and p.name.endswith(_ENC) and not p.name.endswith(_ENC + _TMP)


def decrypt_attachments_folder(vault_root: Path, fernet: Fernet) -> None:
    """Decrypt every ``*.enc`` under ``attachments/`` to plaintext; delete ciphertext."""
    root = attachments_dir(vault_root)
    if not root.is_dir():
        return

    # If plaintext survived a partial shutdown, drop stale ciphertext siblings.
    for enc in list(root.rglob(f"*{_ENC}")):
        if not _is_encrypted_path(enc):
            continue
        plain_name = enc.name[: -len(_ENC)]
        plain = enc.parent / plain_name
        if plain.is_file():
            try:
                enc.unlink()
            except OSError:
                pass

    enc_files = sorted(
        (p for p in root.rglob(f"*{_ENC}") if _is_encrypted_path(p)),
        key=lambda x: str(x),
    )
    for enc in enc_files:
        plain_name = enc.name[: -len(_ENC)]
        plain = enc.parent / plain_name
        if plain.exists():
            try:
                enc.unlink()
            except OSError:
                pass
            continue
        tmp_plain = plain.with_name(plain.name + _TMP)
        try:
            if tmp_plain.exists():
                tmp_plain.unlink()
            decrypt_file(enc, tmp_plain, fernet)
            os.replace(tmp_plain, plain)
        finally:
            if tmp_plain.exists():
                try:
                    tmp_plain.unlink()
                except OSError:
                    pass
        try:
            enc.unlink()
        except OSError:
            pass


def encrypt_attachments_folder(vault_root: Path, fernet: Fernet) -> None:
    """Encrypt every plaintext file under ``attachments/`` to ``*.enc``; remove plaintext."""
    root = attachments_dir(vault_root)
    if not root.is_dir():
        return

    candidates: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.endswith(_ENC):
            continue
        if p.name.endswith(_TMP):
            continue
        candidates.append(p)
    for plain in sorted(candidates, key=lambda x: str(x)):
        enc = plain.with_name(plain.name + _ENC)
        tmp_enc = enc.with_name(enc.name + _TMP)
        try:
            if tmp_enc.exists():
                tmp_enc.unlink()
            encrypt_file(plain, tmp_enc, fernet)
            os.replace(tmp_enc, enc)
        finally:
            if tmp_enc.exists():
                try:
                    tmp_enc.unlink()
                except OSError:
                    pass
        try:
            plain.unlink()
        except OSError:
            pass


def purge_task_attachments_folder(vault_root: Path, task_id: int) -> None:
    """Remove ``attachments/<task_id>/`` after the task row is gone."""
    d = attachments_dir(vault_root) / str(int(task_id))
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
