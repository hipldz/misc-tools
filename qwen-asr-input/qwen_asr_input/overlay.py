from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from .config import OverlaySettings
from .contracts import TranscriptUpdate


class QtStreamingOverlay:
    """Bottom-centered Qt overlay managed by a small isolated process."""

    def __init__(self, settings: OverlaySettings) -> None:
        self.settings = settings
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._hide_timer: threading.Timer | None = None

    def listening(self) -> None:
        if not self.settings.enabled:
            return
        with self._lock:
            if self._hide_timer is not None:
                self._hide_timer.cancel()
                self._hide_timer = None
            self._close_locked()
            self._process = subprocess.Popen(
                [
                    "/usr/bin/python3",
                    str(Path(__file__).with_name("qt_overlay_worker.py")),
                    "--width",
                    str(self.settings.width),
                    "--bottom-margin",
                    str(self.settings.bottom_margin),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._write_locked("listening", "正在聆听…")

    def update(self, update: TranscriptUpdate) -> None:
        self._write("final" if update.final else "streaming", update.text)

    def transcribing(self) -> None:
        self._write("transcribing", "正在完成识别…")

    def complete(self, text: str) -> None:
        self._write("complete", text)
        self._schedule_hide()

    def error(self, message: str) -> None:
        self._write("error", message)
        self._schedule_hide()

    def _write(self, state: str, text: str) -> None:
        with self._lock:
            self._write_locked(state, text)

    def _write_locked(self, state: str, text: str) -> None:
        if self._process is None or self._process.stdin is None:
            return
        message = {"state": state, "text": " ".join(text.splitlines())}
        try:
            self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError):
            self._process = None

    def _schedule_hide(self) -> None:
        if self._hide_timer is not None:
            self._hide_timer.cancel()
        self._hide_timer = threading.Timer(
            self.settings.final_hold_ms / 1000, self.hide
        )
        self._hide_timer.daemon = True
        self._hide_timer.start()

    def hide(self) -> None:
        with self._lock:
            self._hide_timer = None
            self._close_locked()

    def _close_locked(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
