from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Callable, Protocol


@dataclass(frozen=True, slots=True)
class InputTarget:
    """The exact application input-focus window captured before recording."""

    window_id: int | None


@dataclass(frozen=True, slots=True)
class TranscriptUpdate:
    text: str
    final: bool


TranscriptCallback = Callable[[TranscriptUpdate], None]


class AudioSource(Protocol):
    async def chunks(self, stop_requested: "AsyncFlag") -> AsyncIterator[bytes]: ...


class AsrClient(Protocol):
    async def transcribe(
        self, audio: AsyncIterator[bytes], on_update: TranscriptCallback | None = None
    ) -> str: ...


class FocusTracker(Protocol):
    def capture(self) -> InputTarget: ...


class TextInjector(Protocol):
    def inject(self, text: str, target: InputTarget) -> None: ...


class Overlay(Protocol):
    def listening(self) -> None: ...

    def update(self, update: TranscriptUpdate) -> None: ...

    def transcribing(self) -> None: ...

    def complete(self, text: str) -> None: ...

    def error(self, message: str) -> None: ...


class AsyncFlag(Protocol):
    def is_set(self) -> bool: ...
