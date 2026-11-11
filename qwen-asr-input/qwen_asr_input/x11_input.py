from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import time

from .contracts import InputTarget


class X11FocusTracker:
    def __init__(self) -> None:
        self._x11 = _load_library("X11")
        _declare_x11(self._x11)

    def capture(self) -> InputTarget:
        display = self._x11.XOpenDisplay(None)
        if not display:
            raise RuntimeError("cannot open X11 display")
        try:
            window = ctypes.c_ulong()
            revert = ctypes.c_int()
            self._x11.XGetInputFocus(display, ctypes.byref(window), ctypes.byref(revert))
            return InputTarget(window_id=int(window.value) or None)
        finally:
            self._x11.XCloseDisplay(display)


class X11XTestPasteInjector:
    """Unicode-safe input: CLIPBOARD + native XTEST Shift+Insert."""

    def __init__(self, keep_clipboard: bool = True) -> None:
        self.keep_clipboard = keep_clipboard
        self._x11 = _load_library("X11")
        self._xtst = _load_library("Xtst")
        _declare_x11(self._x11)
        self._xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self._xtst.XTestFakeKeyEvent.restype = ctypes.c_int

    def inject(self, text: str, target: InputTarget) -> None:
        if not text:
            return
        # xclip forks a tiny selection owner, so the Unicode payload remains
        # available while the target handles Shift+Insert.
        subprocess.run(
            ["xclip", "-selection", "clipboard", "-in"],
            input=text.encode(),
            check=True,
        )
        time.sleep(0.08)

        display = self._x11.XOpenDisplay(None)
        if not display:
            raise RuntimeError("cannot open X11 display for injection")
        try:
            if target.window_id not in (None, 0, 1):
                self._x11.XSetInputFocus(
                    display, ctypes.c_ulong(target.window_id), 2, 0
                )
                self._x11.XSync(display, 0)
                time.sleep(0.04)

            shift = self._keycode(display, b"Shift_L")
            insert = self._keycode(display, b"Insert")
            for keycode, pressed in (
                (shift, True),
                (insert, True),
                (insert, False),
                (shift, False),
            ):
                if not self._xtst.XTestFakeKeyEvent(
                    display, keycode, int(pressed), 0
                ):
                    raise RuntimeError("XTestFakeKeyEvent failed")
                self._x11.XFlush(display)
                time.sleep(0.01)
            self._x11.XSync(display, 0)
            time.sleep(0.25)
        finally:
            self._x11.XCloseDisplay(display)

    def _keycode(self, display, name: bytes) -> int:
        keysym = self._x11.XStringToKeysym(name)
        keycode = self._x11.XKeysymToKeycode(display, keysym)
        if not keycode:
            raise RuntimeError(f"X11 keymap does not contain {name.decode()}")
        return int(keycode)


def _load_library(name: str):
    path = ctypes.util.find_library(name)
    if not path:
        raise RuntimeError(f"required runtime library lib{name} was not found")
    return ctypes.cdll.LoadLibrary(path)


def _declare_x11(x11) -> None:
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XGetInputFocus.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
    ]
    x11.XSetInputFocus.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_ulong,
    ]
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XKeysymToKeycode.restype = ctypes.c_uint
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
