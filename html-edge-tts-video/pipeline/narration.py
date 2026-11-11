#!/usr/bin/env python3
"""Canonical narration text and authored caption-segment helpers."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SEGMENT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SENTENCE_BREAK_RE = re.compile(r"(?<=[。！？!?；;])\s*")
SOFT_PIECE_RE = re.compile(r".+?(?:[，：,]|$)")
ASCII_SPOKEN_END_RE = re.compile(r"[A-Za-z0-9.!?,:;%)\]}\"']$")
ASCII_SPOKEN_START_RE = re.compile(r"^[“‘\"']*[A-Za-z0-9]")


def caption_units(text: str) -> float:
    units = 0.0
    for char in text.strip():
        if char.isspace():
            units += 0.3
        elif char.isascii() and (char.isalnum() or char in "-_/"):
            units += 0.55
        elif char.isascii():
            units += 0.45
        else:
            units += 1.0
    return units


def authored_segments(scene: dict[str, Any]) -> list[dict[str, str]] | None:
    narration = scene.get("narration")
    if not isinstance(narration, dict):
        return None
    raw_segments = narration.get("segments")
    if not isinstance(raw_segments, list):
        return None
    return [
        {
            "id": str(segment.get("id") or "").strip(),
            "text": str(segment.get("text") or "").strip(),
        }
        for segment in raw_segments
        if isinstance(segment, dict)
    ]


def narration_segment_layout(
    segments: list[dict[str, str]],
) -> tuple[str, list[tuple[int, int]]]:
    """Join authored cuts into stable spoken text and return each cut's text span."""
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    previous = ""
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        separator = ""
        if previous and ASCII_SPOKEN_END_RE.search(previous) and ASCII_SPOKEN_START_RE.match(text):
            separator = " "
        if separator:
            parts.append(separator)
            cursor += len(separator)
        start = cursor
        parts.append(text)
        cursor += len(text)
        spans.append((start, cursor))
        previous = text
    return "".join(parts).strip(), spans


def narration_text(scene: dict[str, Any]) -> str:
    narration = scene.get("narration")
    if isinstance(narration, str):
        return narration.strip()
    segments = authored_segments(scene)
    if segments is None:
        return ""
    return narration_segment_layout(segments)[0]


def narration_signature(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signature = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        segments = authored_segments(scene)
        signature.append({
            "id": str(scene.get("id") or ""),
            "segments": segments if segments is not None else [
                {"id": "legacy", "text": narration_text(scene)}
            ],
        })
    return signature


def source_revision(scenes: list[dict[str, Any]]) -> str:
    raw = json.dumps(narration_signature(scenes), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def narration_chars(scenes: list[dict[str, Any]]) -> int:
    return sum(len(narration_text(scene)) for scene in scenes if isinstance(scene, dict))


def narration_language_sample(scenes: list[dict[str, Any]]) -> str:
    return " ".join(narration_text(scene) for scene in scenes if isinstance(scene, dict))


def split_narration_text(text: str, maximum_units: float = 36.0) -> list[str]:
    """Split source text only at authored punctuation; never fracture a word or clause blindly."""
    sentences = [part.strip() for part in SENTENCE_BREAK_RE.split(text.strip()) if part.strip()]
    segments: list[str] = []
    for sentence in sentences:
        if caption_units(sentence) <= maximum_units:
            segments.append(sentence)
            continue
        pieces = [match.group(0).strip() for match in SOFT_PIECE_RE.finditer(sentence) if match.group(0).strip()]
        current = ""
        for piece in pieces:
            candidate = current + piece
            if current and caption_units(candidate) > maximum_units:
                segments.append(current)
                current = piece
            else:
                current = candidate
        if current:
            segments.append(current)
    return segments or ([text.strip()] if text.strip() else [])


def segmented_narration(
    cues: list[dict[str, Any]],
    scene_id: str,
) -> dict[str, list[dict[str, str]]]:
    return {
        "segments": [
            {
                "id": f"{scene_id}-{index + 1:02d}",
                "text": str(cue.get("text") or "").strip(),
            }
            for index, cue in enumerate(cues)
            if isinstance(cue, dict)
        ]
    }


def normalize_scene_narrations(
    scenes: list[dict[str, Any]],
    cues_by_scene: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Return a uniform segment schema, optionally taking cuts from a current timeline."""
    normalized = []
    for scene in scenes:
        scene_id = str(scene.get("id") or "")
        provided_cues = (cues_by_scene or {}).get(scene_id)
        if provided_cues:
            cues = provided_cues
        else:
            existing = authored_segments(scene)
            texts = (
                [segment["text"] for segment in existing]
                if existing is not None
                else split_narration_text(narration_text(scene))
            )
            cues = [{"text": text} for text in texts]
        normalized.append({
            **scene,
            "narration": segmented_narration(cues, scene_id),
        })
    return normalized
