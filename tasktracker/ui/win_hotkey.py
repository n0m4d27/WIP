"""Windows global hotkey via ``RegisterHotKey`` + Qt native event filter (plan 05)."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

# Win32 modifiers for RegisterHotKey
_MOD_NOREPEAT = 0x4000
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008

_WM_HOTKEY = 0x0312


def _portable_to_register_hotkey(portable: str) -> tuple[int, int] | None:
    """Return ``(fsModifiers | MOD_NOREPEAT, vk)`` or ``None`` if unsupported."""
    ks = QKeySequence(portable)
    if ks.isEmpty():
        return None
    kc = ks[0]
    key_val = int(kc.key())
    mask = int(Qt.KeyboardModifier.KeyboardModifierMask)
    key_only = key_val & ~mask
    qm = kc.keyboardModifiers()
    mods = _MOD_NOREPEAT
    if qm & Qt.KeyboardModifier.ShiftModifier:
        mods |= _MOD_SHIFT
    if qm & Qt.KeyboardModifier.ControlModifier:
        mods |= _MOD_CONTROL
    if qm & Qt.KeyboardModifier.AltModifier:
        mods |= _MOD_ALT
    if qm & Qt.KeyboardModifier.MetaModifier:
        mods |= _MOD_WIN

    # Map Qt.Key to virtual-key code for common keys.
    if int(Qt.Key.Key_A) <= key_only <= int(Qt.Key.Key_Z):
        vk = key_only
    elif int(Qt.Key.Key_0) <= key_only <= int(Qt.Key.Key_9):
        vk = key_only
    elif int(Qt.Key.Key_F1) <= key_only <= int(Qt.Key.Key_F24):
        vk = 0x70 + (key_only - int(Qt.Key.Key_F1))
    else:
        return None
    return mods, vk


class _HotkeyNativeFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, on_trigger: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_id = int(hotkey_id)
        self._on_trigger = on_trigger

    def nativeEventFilter(self, event_type, message):  # type: ignore[override]
        if event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (ValueError, TypeError):
            return False, 0
        if msg.message != _WM_HOTKEY or int(msg.wParam) != self._hotkey_id:
            return False, 0
        QTimer.singleShot(0, self._on_trigger)
        return True, 0


class WindowsGlobalHotkey:
    """Register a system-wide hotkey on Windows; no-op on other platforms."""

    _NEXT_ID = 0xB000

    def __init__(self, portable: str, on_trigger: Callable[[], None]) -> None:
        self._portable = portable
        self._on_trigger = on_trigger
        self._hotkey_id = WindowsGlobalHotkey._NEXT_ID
        WindowsGlobalHotkey._NEXT_ID += 1
        self._filter: _HotkeyNativeFilter | None = None
        self._registered = False

    def register(self, app: QApplication) -> bool:
        if sys.platform != "win32":
            return False
        parsed = _portable_to_register_hotkey(self._portable)
        if parsed is None:
            return False
        mods, vk = parsed
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, self._hotkey_id, mods, vk):
            return False
        self._filter = _HotkeyNativeFilter(self._hotkey_id, self._on_trigger)
        app.installNativeEventFilter(self._filter)
        self._registered = True
        return True

    def unregister(self, app: QApplication) -> None:
        if not self._registered or sys.platform != "win32":
            self._registered = False
            self._filter = None
            return
        user32 = ctypes.windll.user32
        user32.UnregisterHotKey(None, self._hotkey_id)
        if self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
        self._registered = False
