from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet


def encrypt_file(plain_path: Path, encrypted_path: Path, fernet: Fernet) -> None:
    data = plain_path.read_bytes()
    token = fernet.encrypt(data)
    encrypted_path.write_bytes(token)


def decrypt_file(encrypted_path: Path, plain_path: Path, fernet: Fernet) -> None:
    token = encrypted_path.read_bytes()
    data = fernet.decrypt(token)
    plain_path.write_bytes(data)
