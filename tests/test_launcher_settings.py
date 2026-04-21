"""Pure unit tests for tasktracker.launcher_settings.

Deliberately Qt-free so these run fast on Windows without tripping the
PySide6 offscreen-renderer hang observed elsewhere. The module itself
imports Qt lazily inside :func:`launcher_config_path`, so nothing here
needs a QApplication.
"""

from __future__ import annotations

import json
from pathlib import Path

from tasktracker.launcher_settings import (
    LauncherSettings,
    MAX_RECENTS,
    SCHEMA_VERSION,
    clear_default,
    load,
    record_opened,
    save,
    set_default,
)


def test_load_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = tmp_path / "launcher.json"
    settings = load(cfg)
    assert settings.version == SCHEMA_VERSION
    assert settings.last_opened is None
    assert settings.default_vault is None
    assert settings.recent_vaults == []


def test_load_malformed_json_returns_defaults(tmp_path: Path) -> None:
    cfg = tmp_path / "launcher.json"
    cfg.write_text("not json at all {", encoding="utf-8")
    settings = load(cfg)
    assert settings.last_opened is None
    assert settings.recent_vaults == []


def test_load_unexpected_top_level_type(tmp_path: Path) -> None:
    cfg = tmp_path / "launcher.json"
    cfg.write_text("[]", encoding="utf-8")  # list, not dict
    settings = load(cfg)
    assert settings.last_opened is None


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    cfg = tmp_path / "sub" / "launcher.json"  # parent must be auto-created
    s = LauncherSettings(
        last_opened="/vaults/a",
        default_vault="/vaults/b",
        recent_vaults=["/vaults/a", "/vaults/b"],
    )
    save(cfg, s)
    assert cfg.exists()
    loaded = load(cfg)
    assert loaded.last_opened == "/vaults/a"
    assert loaded.default_vault == "/vaults/b"
    assert loaded.recent_vaults == ["/vaults/a", "/vaults/b"]


def test_record_opened_promotes_to_front(tmp_path: Path) -> None:
    s = LauncherSettings(recent_vaults=["/a", "/b", "/c"])
    target = tmp_path / "b"
    target.mkdir()
    record_opened(s, target)
    expected = str(target.resolve())
    assert s.last_opened == expected
    assert s.recent_vaults[0] == expected
    # Original "/a" and "/c" still present
    assert "/a" in s.recent_vaults
    assert "/c" in s.recent_vaults


def test_record_opened_deduplicates(tmp_path: Path) -> None:
    target = tmp_path / "vault"
    target.mkdir()
    expected = str(target.resolve())
    s = LauncherSettings(recent_vaults=[expected, "/older/one"])
    record_opened(s, target)
    assert s.recent_vaults.count(expected) == 1
    assert s.recent_vaults[0] == expected


def test_record_opened_trims_to_max(tmp_path: Path) -> None:
    existing = [f"/vaults/{i}" for i in range(MAX_RECENTS)]
    s = LauncherSettings(recent_vaults=list(existing))
    newpath = tmp_path / "new"
    newpath.mkdir()
    record_opened(s, newpath)
    assert len(s.recent_vaults) <= MAX_RECENTS
    assert s.recent_vaults[0] == str(newpath.resolve())


def test_set_and_clear_default_round_trip(tmp_path: Path) -> None:
    cfg = tmp_path / "launcher.json"
    vault = tmp_path / "main"
    vault.mkdir()
    s = LauncherSettings()
    set_default(s, vault)
    save(cfg, s)
    reloaded = load(cfg)
    assert reloaded.default_vault == str(vault.resolve())
    clear_default(reloaded)
    save(cfg, reloaded)
    again = load(cfg)
    assert again.default_vault is None


def test_forward_compat_higher_version(tmp_path: Path) -> None:
    """A newer binary wrote a higher `version`; we must read what we
    understand without raising so the user isn't locked out."""
    cfg = tmp_path / "launcher.json"
    cfg.write_text(
        json.dumps(
            {
                "version": 9999,
                "last_opened": "/some/vault",
                "default_vault": None,
                "recent_vaults": ["/some/vault"],
                "future_key_we_dont_know": {"anything": True},
            }
        ),
        encoding="utf-8",
    )
    settings = load(cfg)
    assert settings.last_opened == "/some/vault"
    assert settings.recent_vaults == ["/some/vault"]


def test_malformed_types_are_tolerated(tmp_path: Path) -> None:
    cfg = tmp_path / "launcher.json"
    cfg.write_text(
        json.dumps(
            {
                "version": "not-an-int",
                "last_opened": 42,  # wrong type
                "default_vault": "",  # empty string treated as unset
                "recent_vaults": ["/a", 7, "/b", None],  # filters non-strings
            }
        ),
        encoding="utf-8",
    )
    settings = load(cfg)
    assert settings.version == SCHEMA_VERSION
    assert settings.last_opened is None
    assert settings.default_vault is None
    assert settings.recent_vaults == ["/a", "/b"]
