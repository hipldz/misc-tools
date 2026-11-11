from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator

from .config import AudioSettings
from .contracts import AsyncFlag


class ArecordAudioSource:
    """PCM source backed by ALSA's arecord; no Python audio package required."""

    def __init__(self, settings: AudioSettings) -> None:
        self.settings = settings

    async def chunks(self, stop_requested: AsyncFlag) -> AsyncIterator[bytes]:
        command = [
            "arecord",
            "-q",
            "-D",
            self.settings.device,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-c",
            "1",
            "-r",
            str(self.settings.sample_rate),
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert process.stdout is not None
        try:
            while not stop_requested.is_set():
                chunk = await asyncio.to_thread(
                    process.stdout.read, self.settings.chunk_bytes
                )
                if not chunk:
                    detail = ""
                    if process.stderr is not None:
                        detail = process.stderr.read().decode(errors="replace").strip()
                    raise RuntimeError(f"arecord stopped unexpectedly: {detail}")
                yield chunk
        finally:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 1)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait)
