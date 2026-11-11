#!/usr/bin/env python3
"""Generate TTS audio, WordBoundary caption timing, and one narration MP3."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path

try:
    from .factory import load_scenes, project_paths
    from .narration import (
        authored_segments,
        caption_units,
        narration_segment_layout,
        narration_text,
    )
    from .toolchain import ffmpeg_executable, media_duration
    from .tts_provider import resolve_provider, synthesize_to_file
except ImportError:  # Direct script execution: python pipeline/build_tts.py
    from factory import load_scenes, project_paths
    from narration import authored_segments, caption_units, narration_segment_layout, narration_text
    from toolchain import ffmpeg_executable, media_duration
    from tts_provider import resolve_provider, synthesize_to_file


SCENE_AUDIO = Path()
HARD_BREAK_RE = re.compile(r"[\u3002\uff01\uff1f\uff1b.!?;][\u201d\u2019\"'\uff09\u3011\u300b]*\s*$")
SOFT_BREAK_RE = re.compile(r"[\uff0c\u3001\uff1a,:][\u201d\u2019\"'\uff09\u3011\u300b]*\s*$")
LEADING_DEPENDENT_RE = re.compile(r"^[\s\u201c\u2018\"']*(?:\u7684|\u4e86|\u7740|\u8fc7|\u548c|\u4e0e|\u53ca|\u6216|\u800c|\u4f46|\u5e76)")
CONNECTOR_WORD_RE = re.compile(r"^(?:\u548c|\u4e0e|\u53ca|\u6216|\u800c|\u4f46|\u5e76|and|or|but)$", re.IGNORECASE)
TARGET_CAPTION_UNITS = 18.0
MAX_CAPTION_UNITS = 26.0
ABSOLUTE_CAPTION_UNITS = 36.0
MIN_TAIL_UNITS = 7.0
MAX_CAPTION_SECONDS = 3.6
ABSOLUTE_CAPTION_SECONDS = 5.2


def audio_duration(path: Path) -> float:
    return media_duration(path)


def text_hash(text: str, voice: str, rate: str, pitch: str, boundary: str) -> str:
    return hashlib.sha256(f"{voice}|{rate}|{pitch}|{boundary}|{text}".encode()).hexdigest()[:16]


def validate_scenes(scenes: list[dict]) -> None:
    if not isinstance(scenes, list) or not scenes:
        raise SystemExit("scenes.json must be a non-empty JSON array")
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict) or not scene.get("id"):
            raise SystemExit(f"scene {index} must include id and narration.segments")
        segments = authored_segments(scene)
        if not segments or not narration_text(scene):
            raise SystemExit(f"scene {index} narration must use a non-empty segments array")


def source_word_pieces(words: list[dict], narration: str) -> list[dict]:
    """Attach original spaces and punctuation to provider WordBoundary items."""
    positions: list[int] = []
    cursor = 0
    folded_narration = narration.casefold()
    for word in words:
        raw = str(word.get("text") or "")
        position = narration.find(raw, cursor)
        if position < 0:
            position = folded_narration.find(raw.casefold(), cursor)
        if position < 0:
            # Provider-normalized text is not always a source substring. Keep
            # timing usable and fall back to readable spacing in that case.
            fallback: list[dict] = []
            previous = ""
            for item in words:
                value = str(item.get("text") or "")
                separator = " " if previous[-1:].isascii() and value[:1].isascii() else ""
                fallback.append({**item, "display_text": separator + value})
                previous = value
            return fallback
        positions.append(position)
        cursor = position + len(raw)

    prepared = []
    for index, word in enumerate(words):
        start = 0 if index == 0 else positions[index]
        end = positions[index + 1] if index + 1 < len(words) else len(narration)
        prepared.append({**word, "display_text": narration[start:end]})
    return prepared


def source_word_positions(words: list[dict], narration: str) -> list[int] | None:
    positions: list[int] = []
    cursor = 0
    folded_narration = narration.casefold()
    for word in words:
        raw = str(word.get("text") or "")
        position = narration.find(raw, cursor)
        if position < 0:
            position = folded_narration.find(raw.casefold(), cursor)
        if position < 0:
            return None
        positions.append(position)
        cursor = position + len(raw)
    return positions


def authored_segment_cues(
    words: list[dict],
    scene_id: str,
    scene_start: float,
    scene_duration: float,
    segments: list[dict[str, str]],
    narration: str,
) -> list[dict]:
    positions = source_word_positions(words, narration)
    joined_narration, segment_spans = narration_segment_layout(segments)
    if joined_narration != narration:
        positions = None

    first_word_indexes: list[int] = []
    if positions is not None:
        for start, end in segment_spans:
            indexes = [
                index
                for index, position in enumerate(positions)
                if position < end and position + len(str(words[index].get("text") or "")) > start
            ]
            if not indexes:
                first_word_indexes = []
                break
            first_word_indexes.append(indexes[0])

    if len(first_word_indexes) == len(segments):
        boundaries = [0.0]
        boundaries.extend(float(words[index]["start"]) for index in first_word_indexes[1:])
        boundaries.append(scene_duration)
    else:
        weights = [max(1.0, caption_units(segment["text"])) for segment in segments]
        total = sum(weights)
        elapsed = 0.0
        boundaries = [0.0]
        for weight in weights[:-1]:
            elapsed += scene_duration * weight / total
            boundaries.append(elapsed)
        boundaries.append(scene_duration)

    return [
        {
            "id": segment["id"],
            "start": scene_start + boundaries[index],
            "end": scene_start + boundaries[index + 1],
            "text": segment["text"],
            "scene_id": scene_id,
        }
        for index, segment in enumerate(segments)
    ]


def group_text(group: list[dict]) -> str:
    return "".join(str(item.get("display_text") or item.get("text") or "") for item in group).strip()


def group_words(words: list[dict], scene_id: str, scene_start: float, narration: str) -> list[dict]:
    prepared = source_word_pieces(words, narration)
    groups: list[list[dict]] = []
    group: list[dict] = []
    protect_phrase = False

    for index, word in enumerate(prepared):
        raw_word = str(word.get("text") or "").strip()
        if group and CONNECTOR_WORD_RE.fullmatch(raw_word):
            current_units = caption_units(group_text(group))
            current_duration = float(group[-1]["end"]) - float(group[0]["start"])
            if current_units >= TARGET_CAPTION_UNITS or current_duration >= 3.2:
                groups.append(group)
                group = []
                protect_phrase = False

        group.append(word)
        text = group_text(group)
        duration = float(group[-1]["end"]) - float(group[0]["start"])
        units = caption_units(text)
        hard_break = bool(HARD_BREAK_RE.search(text))
        soft_break = bool(SOFT_BREAK_RE.search(text)) and (units >= 8 or duration >= 1.5)
        size_break = units >= MAX_CAPTION_UNITS or duration >= MAX_CAPTION_SECONDS
        should_break = hard_break or soft_break or size_break

        if size_break and index + 1 < len(prepared) and not hard_break:
            remaining_text = group_text(prepared[index + 1 :])
            if LEADING_DEPENDENT_RE.search(remaining_text):
                protect_phrase = True
            combined_units = caption_units(text + remaining_text)
            combined_duration = float(prepared[-1]["end"]) - float(group[0]["start"])
            if caption_units(remaining_text) <= MIN_TAIL_UNITS and combined_units <= ABSOLUTE_CAPTION_UNITS and combined_duration <= ABSOLUTE_CAPTION_SECONDS:
                protect_phrase = True

        if protect_phrase and not hard_break:
            if units < ABSOLUTE_CAPTION_UNITS and duration < ABSOLUTE_CAPTION_SECONDS:
                should_break = False

        if should_break:
            groups.append(group)
            group = []
            protect_phrase = False

    if group:
        groups.append(group)

    if len(groups) > 1:
        tail = groups[-1]
        previous = groups[-2]
        previous_text = group_text(previous)
        combined = previous + tail
        combined_duration = float(combined[-1]["end"]) - float(combined[0]["start"])
        if (
            caption_units(group_text(tail)) <= MIN_TAIL_UNITS
            and not HARD_BREAK_RE.search(previous_text)
            and caption_units(group_text(combined)) <= ABSOLUTE_CAPTION_UNITS
            and combined_duration <= ABSOLUTE_CAPTION_SECONDS
        ):
            groups[-2:] = [combined]

    return [
        {
            "start": scene_start + float(group[0]["start"]),
            "end": scene_start + float(group[-1]["end"]),
            "text": group_text(group),
            "scene_id": scene_id,
        }
        for group in groups
        if group_text(group)
    ]


async def synth_scene(
    scene: dict,
    provider: str,
    voice: str,
    rate: str,
    pitch: str,
    force: bool,
) -> tuple[Path, list[dict]]:
    SCENE_AUDIO.mkdir(parents=True, exist_ok=True)
    audio_path = SCENE_AUDIO / f"{scene['id']}.mp3"
    temp_audio_path = SCENE_AUDIO / f"{scene['id']}.mp3.part"
    meta_path = SCENE_AUDIO / f"{scene['id']}.words.json"
    stamp_path = SCENE_AUDIO / f"{scene['id']}.build.json"
    boundary = f"{provider}:WordBoundary:v1"
    text = narration_text(scene)
    build_hash = text_hash(text, voice, rate, pitch, boundary)

    if not force and audio_path.exists() and meta_path.exists() and stamp_path.exists():
        stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        words = json.loads(meta_path.read_text(encoding="utf-8"))
        if stamp.get("hash") == build_hash and stamp.get("boundary") == boundary and words:
            return audio_path, words

    words: list[dict] = []
    temp_audio_path.unlink(missing_ok=True)
    try:
        words, _provider_duration = await asyncio.to_thread(
            synthesize_to_file,
            provider,
            text,
            voice,
            rate,
            pitch,
            temp_audio_path,
        )
        if not temp_audio_path.exists() or temp_audio_path.stat().st_size == 0:
            raise RuntimeError(f"{provider} returned an empty audio file")
        if not words:
            raise RuntimeError(f"{provider} returned no WordBoundary metadata")
        duration = audio_duration(temp_audio_path)
        words.sort(key=lambda item: float(item["start"]))
        for index, word in enumerate(words):
            next_start = float(words[index + 1]["start"]) if index + 1 < len(words) else duration
            if float(word["end"]) <= float(word["start"]):
                word["end"] = max(float(word["start"]), next_start)
        temp_audio_path.replace(audio_path)
    except Exception as exc:  # noqa: BLE001 - add scene and voice context to provider failures.
        temp_audio_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"{provider} TTS failed for scene {scene['id']!r} with voice {voice!r}: {exc}"
        ) from exc

    meta_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
    stamp_path.write_text(
        json.dumps(
            {
                "hash": build_hash,
                "voice": voice,
                "rate": rate,
                "pitch": pitch,
                "boundary": boundary,
                "provider": provider,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return audio_path, words


def write_gap_audio(path: Path, duration: float) -> None:
    subprocess.run(
        [
            ffmpeg_executable(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(duration),
            "-q:a",
            "9",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def main_async(args: argparse.Namespace) -> None:
    global SCENE_AUDIO
    paths = project_paths(Path(args.source) if args.source else None)
    assets = paths.generated
    SCENE_AUDIO = assets / "scenes"
    provider = resolve_provider(args.provider)
    print(f"TTS provider: {provider}", flush=True)
    scenes = load_scenes(paths.root)
    validate_scenes(scenes)
    assets.mkdir(parents=True, exist_ok=True)
    SCENE_AUDIO.mkdir(parents=True, exist_ok=True)

    timeline_scenes: list[dict] = []
    all_cues: list[dict] = []
    concat: list[str] = []
    cursor = 0.0

    for index, scene in enumerate(scenes, 1):
        print(f"[{index:02d}/{len(scenes):02d}] {scene['id']}")
        audio_path, words = await synth_scene(
            scene, provider, args.voice, args.rate, args.pitch, args.force
        )
        duration = audio_duration(audio_path)
        timeline_scenes.append({**scene, "start": round(cursor, 3), "duration": round(duration, 3)})
        text = narration_text(scene)
        segments = authored_segments(scene)
        if segments is None:
            all_cues.extend(group_words(words, scene["id"], cursor, text))
        else:
            all_cues.extend(
                authored_segment_cues(words, scene["id"], cursor, duration, segments, text)
            )
        concat.append(f"file '{audio_path.as_posix()}'")

        if index != len(scenes):
            silence = SCENE_AUDIO / f"gap-{index:02d}.mp3"
            write_gap_audio(silence, args.gap)
            concat.append(f"file '{silence.as_posix()}'")
            cursor += duration + args.gap
        else:
            cursor += duration

    concat_file = assets / "concat.txt"
    concat_file.write_text("\n".join(concat), encoding="utf-8")
    narration = assets / "narration.mp3"
    subprocess.run(
        [ffmpeg_executable(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:a", "libmp3lame", "-q:a", "2", str(narration)],
        check=True,
    )
    timeline = {
        "duration": round(audio_duration(narration), 3),
        "voice": args.voice,
        "rate": args.rate,
        "pitch": args.pitch,
        "provider": provider,
        "scenes": timeline_scenes,
        "cues": all_cues,
    }
    timeline_path = assets / "timeline.json"
    timeline_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    if paths.captions.exists():
        paths.captions.unlink(missing_ok=True)
        print("Manual caption timing was replaced by timing derived from the new narration.")
    print(f"\nCreated: {narration}\nCreated: {timeline_path}\nDuration: {timeline['duration']:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    parser.add_argument("--provider", default="edge", choices=["edge", "azure"])
    parser.add_argument("--voice", default="en-US-JennyNeural")
    parser.add_argument("--rate", default="+12%")
    parser.add_argument("--pitch", default="+0Hz")
    parser.add_argument("--gap", type=float, default=0.28)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
