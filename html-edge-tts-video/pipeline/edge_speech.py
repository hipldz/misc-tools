"""Edge TTS synthesis adapter with the same output contract as Azure Speech."""
from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

TICKS_PER_SECOND = 10_000_000


async def _synthesize(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: Path,
    capture_words: bool,
) -> tuple[list[dict], float]:
    words: list[dict] = []
    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=rate,
        pitch=pitch,
        boundary="WordBoundary",
    )
    with output_path.open("wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif capture_words and chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                duration = chunk["duration"] / TICKS_PER_SECOND
                words.append({"start": start, "end": start + duration, "text": chunk["text"]})
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Edge TTS returned an empty audio file")
    return words, 0.0


def synthesize_to_file(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    output_path: Path,
    *,
    capture_words: bool = True,
) -> tuple[list[dict], float]:
    return asyncio.run(_synthesize(text, voice, rate, pitch, output_path, capture_words))
