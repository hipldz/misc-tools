from __future__ import annotations

import enum
import fcntl
import glob
import os
import select
import struct


EV_KEY = 0x01
KEY_LEFTCTRL = 29
KEY_RIGHTCTRL = 97
KEY_LEFTMETA = 125
KEY_RIGHTMETA = 126
KEY_MAX = 0x2FF
INPUT_EVENT = struct.Struct("llHHi")


class HotkeyTransition(enum.Enum):
    START = "start"
    STOP = "stop"
    RELEASED = "released"


def _ioc(direction: int, type_: int, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (type_ << 8) | number


def _eviocgbit(event_type: int, length: int) -> int:
    return _ioc(2, ord("E"), 0x20 + event_type, length)


def _has_bit(bits: bytearray, code: int) -> bool:
    return bool(bits[code // 8] & (1 << (code % 8)))


class EvdevPushToTalk:
    """Ctrl+Meta chord reader implemented with the Linux input ABI only."""

    def __init__(self) -> None:
        self._fds = self._open_keyboards()
        self._buffers = {fd: bytearray() for fd in self._fds}
        self._held: set[int] = set()
        self._active = False
        self._waiting_for_release = False

    def close(self) -> None:
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds.clear()

    @staticmethod
    def _open_keyboards() -> list[int]:
        opened: list[int] = []
        for path in sorted(glob.glob("/dev/input/event*")):
            fd: int | None = None
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                bits = bytearray((KEY_MAX + 8) // 8)
                fcntl.ioctl(fd, _eviocgbit(EV_KEY, len(bits)), bits, True)
                has_ctrl = _has_bit(bits, KEY_LEFTCTRL) or _has_bit(
                    bits, KEY_RIGHTCTRL
                )
                has_meta = _has_bit(bits, KEY_LEFTMETA) or _has_bit(
                    bits, KEY_RIGHTMETA
                )
                if has_ctrl and has_meta:
                    opened.append(fd)
                else:
                    os.close(fd)
            except OSError:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
        if not opened:
            raise PermissionError(
                "no readable keyboard event device; add the user to the input group"
            )
        return opened

    def next_transition(self) -> HotkeyTransition:
        while True:
            # Always drain bytes already read before blocking in select(). A
            # single kernel read can contain both modifier-release events; if
            # STOP returns after the first one, RELEASED must be consumed by
            # the next call even when no new fd activity arrives.
            for buffer in self._buffers.values():
                transition = self._consume_buffer(buffer)
                if transition is not None:
                    return transition

            readable, _, _ = select.select(self._fds, [], [])
            for fd in readable:
                try:
                    self._buffers[fd].extend(os.read(fd, INPUT_EVENT.size * 32))
                except BlockingIOError:
                    continue

    def _consume_buffer(self, buffer: bytearray) -> HotkeyTransition | None:
        while len(buffer) >= INPUT_EVENT.size:
            raw = bytes(buffer[: INPUT_EVENT.size])
            del buffer[: INPUT_EVENT.size]
            _, _, event_type, code, value = INPUT_EVENT.unpack(raw)
            if event_type != EV_KEY or value not in (0, 1):
                continue
            if value == 1:
                self._held.add(code)
            else:
                self._held.discard(code)
            transition = self._transition()
            if transition is not None:
                return transition
        return None

    def _transition(self) -> HotkeyTransition | None:
        ctrl = bool(self._held & {KEY_LEFTCTRL, KEY_RIGHTCTRL})
        meta = bool(self._held & {KEY_LEFTMETA, KEY_RIGHTMETA})
        chord = ctrl and meta
        if chord and not self._active:
            self._active = True
            self._waiting_for_release = False
            return HotkeyTransition.START
        if self._active and not chord:
            self._active = False
            self._waiting_for_release = True
            return HotkeyTransition.STOP
        if self._waiting_for_release and not ctrl and not meta:
            self._waiting_for_release = False
            return HotkeyTransition.RELEASED
        return None
