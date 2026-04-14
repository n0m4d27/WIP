from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VERIFY_ITERATIONS = 600_000
KEY_ITERATIONS = 600_000


def create_auth_record(password: str) -> dict[str, Any]:
    verify_salt = secrets.token_bytes(16)
    key_salt = secrets.token_bytes(16)
    password_verify = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), verify_salt, VERIFY_ITERATIONS
    )
    return {
        "version": 1,
        "verify_salt": base64.b64encode(verify_salt).decode("ascii"),
        "key_salt": base64.b64encode(key_salt).decode("ascii"),
        "password_verify": base64.b64encode(password_verify).decode("ascii"),
    }


def verify_password(password: str, record: dict[str, Any]) -> bool:
    verify_salt = base64.b64decode(record["verify_salt"])
    expected = base64.b64decode(record["password_verify"])
    got = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), verify_salt, VERIFY_ITERATIONS
    )
    return secrets.compare_digest(got, expected)


def derive_fernet(password: str, record: dict[str, Any]) -> Fernet:
    key_salt = base64.b64decode(record["key_salt"])
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=key_salt,
        iterations=KEY_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return Fernet(key)


def load_auth_record(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
