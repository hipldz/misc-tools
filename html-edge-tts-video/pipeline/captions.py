#!/usr/bin/env python3
"""Caption timing overrides and direct narration-segment editing."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .factory import (
        STARTER_SOURCE,
        active_source_root,
        atomic_write_json,
        invalidate_composition_assets,
        load_scenes,
        project_paths,
    )
    from .narration import narration_signature, normalize_scene_narrations, source_revision
except ImportError:  # Direct script execution: python pipeline/captions.py
    from factory import (
        STARTER_SOURCE,
        active_source_root,
        atomic_write_json,
        invalidate_composition_assets,
        load_scenes,
        project_paths,
    )
    from narration import narration_signature, normalize_scene_narrations, source_revision


KIND = "html-edge-tts-captions"
VERSION = 2
TIME_EPSILON = 0.002


def cue_id(index: int) -> str:
    return f"cue-{index + 1:04d}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    atomic_write_json(path, value)


def timeline_path(source: Path | None = None) -> Path:
    return project_paths(source).generated / "timeline.json"


def captions_path(source: Path | None = None) -> Path:
    return project_paths(source).captions


def timeline_matches_scenes(timeline: dict, scenes: list[dict]) -> bool:
    timeline_scenes = [
        scene for scene in timeline.get("scenes", []) if isinstance(scene, dict)
    ]
    return narration_signature(scenes) == narration_signature(timeline_scenes)


def timeline_matches_source(timeline: dict) -> bool:
    return timeline_matches_scenes(timeline, load_scenes())


def load_timeline(source: Path | None = None) -> dict:
    path = timeline_path(source)
    if not path.exists():
        raise SystemExit("timeline.json is missing; run python main.py tts --source <folder> first")
    timeline = read_json(path)
    if not isinstance(timeline, dict) or not isinstance(timeline.get("cues"), list):
        raise SystemExit("timeline.json must contain a cues array")
    if not timeline_matches_scenes(timeline, load_scenes(source)):
        raise SystemExit("timeline/audio do not match current scenes; rerun python main.py tts --source <folder>")
    return timeline


def normalize_cue(raw: dict, index: int, fallback: dict | None = None) -> dict:
    fallback = fallback or {}
    return {
        "id": str(raw.get("id") or fallback.get("id") or cue_id(index)),
        "scene_id": str(raw.get("scene_id") or fallback.get("scene_id") or ""),
        "start": round(float(raw.get("start", fallback.get("start", 0))), 3),
        "end": round(float(raw.get("end", fallback.get("end", 0))), 3),
        "text": str(raw.get("text", fallback.get("text", ""))),
    }


def timeline_signature(timeline: dict) -> list[dict]:
    return [normalize_cue(cue, index) for index, cue in enumerate(timeline.get("cues", []))]


def default_doc(timeline: dict, source: Path | None = None) -> dict:
    cues = timeline_signature(timeline)
    return {
        "version": VERSION,
        "kind": KIND,
        "source": "timeline.cues",
        "source_revision": source_revision(load_scenes(source)),
        "timeline_signature": cues,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cues": cues,
    }


def coerce_doc(value: Any, timeline: dict, stamp_signature: bool = False) -> dict:
    raw_cues = value.get("cues") if isinstance(value, dict) else value
    if not isinstance(raw_cues, list):
        raise ValueError("captions.json must be an object with a cues array")

    timeline_cues = timeline.get("cues", [])
    if len(raw_cues) != len(timeline_cues):
        raise ValueError("caption cue count does not match timeline.json")

    cues = []
    for index, raw in enumerate(raw_cues):
        if not isinstance(raw, dict):
            raise ValueError(f"caption cue {index + 1} must be an object")
        try:
            cues.append(normalize_cue(raw, index, normalize_cue(timeline_cues[index], index)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"caption cue {index + 1} has invalid timing") from exc

    doc = {
        "version": VERSION,
        "kind": KIND,
        "source": "manual-timing",
        "source_revision": str(value.get("source_revision") or "") if isinstance(value, dict) else "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cues": cues,
    }
    signature = timeline_signature(timeline) if stamp_signature else (
        value.get("timeline_signature") if isinstance(value, dict) else None
    )
    if isinstance(signature, list):
        doc["timeline_signature"] = signature
    return doc


def cue_timing_is_valid(cue: dict, duration: float) -> bool:
    start = cue.get("start")
    end = cue.get("end")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return False
    if not math.isfinite(start) or not math.isfinite(end):
        return False
    return start >= 0 and end > start and end <= duration + TIME_EPSILON


def cue_identity_matches(current: dict, generated: dict) -> bool:
    return current["id"] == generated["id"] and current["scene_id"] == generated["scene_id"]


def signature_matches_current(doc: dict, timeline: dict) -> bool:
    signature = doc.get("timeline_signature")
    if not isinstance(signature, list):
        return False
    generated_signature = timeline_signature(timeline)
    if len(signature) != len(generated_signature):
        return False
    for index, raw in enumerate(signature):
        if not isinstance(raw, dict):
            return False
        try:
            saved = normalize_cue(raw, index)
            generated = generated_signature[index]
        except (TypeError, ValueError):
            return False
        if not cue_identity_matches(saved, generated):
            return False
        if saved["text"] != generated["text"]:
            return False
        if abs(saved["start"] - generated["start"]) > TIME_EPSILON:
            return False
        if abs(saved["end"] - generated["end"]) > TIME_EPSILON:
            return False
    return True


def captions_match_timeline(doc: dict, timeline: dict) -> bool:
    cues = doc.get("cues")
    timeline_cues = timeline.get("cues")
    duration = float(timeline.get("duration") or 0)
    if not isinstance(cues, list) or not isinstance(timeline_cues, list):
        return False
    if len(cues) != len(timeline_cues) or not signature_matches_current(doc, timeline):
        return False
    for index, cue in enumerate(cues):
        generated = normalize_cue(timeline_cues[index], index)
        try:
            current = normalize_cue(cue, index)
        except (TypeError, ValueError):
            return False
        if not cue_identity_matches(current, generated):
            return False
        if not cue_timing_is_valid(current, duration):
            return False
    return True


def _timing_doc_with_generated_text(doc: dict, timeline: dict) -> dict:
    generated = timeline_signature(timeline)
    current = [normalize_cue(cue, index) for index, cue in enumerate(doc.get("cues", []))]
    return {
        **doc,
        "cues": [
            {**generated[index], "start": cue["start"], "end": cue["end"]}
            for index, cue in enumerate(current)
        ],
    }


def _stored_timing_doc(doc: dict) -> dict:
    return {
        **doc,
        "cues": [
            {
                "id": cue["id"],
                "scene_id": cue["scene_id"],
                "start": cue["start"],
                "end": cue["end"],
            }
            for cue in doc.get("cues", [])
        ],
    }


def load_effective_doc(
    timeline: dict | None = None,
    source: Path | None = None,
) -> tuple[dict, bool]:
    timeline = timeline or load_timeline(source)
    path = captions_path(source)
    if not path.exists():
        return default_doc(timeline, source), False
    try:
        doc = coerce_doc(read_json(path), timeline)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default_doc(timeline, source), False
    if not captions_match_timeline(doc, timeline):
        return default_doc(timeline, source), False
    doc["source_revision"] = source_revision(load_scenes(source))
    return _timing_doc_with_generated_text(doc, timeline), True


def _changed_scene_ids(doc: dict, timeline: dict) -> list[str]:
    generated = timeline_signature(timeline)
    changed: list[str] = []
    for index, cue in enumerate(doc.get("cues", [])):
        current = normalize_cue(cue, index)
        if current["text"] != generated[index]["text"] and current["scene_id"] not in changed:
            changed.append(current["scene_id"])
    return changed


def save_doc(
    value: Any,
    timeline: dict | None = None,
    source: Path | None = None,
) -> dict:
    source_root = project_paths(source).root if source else active_source_root()
    if source_root.resolve() == STARTER_SOURCE.resolve():
        raise ValueError("starter is read-only; activate an editable project before saving captions")
    timeline = timeline or load_timeline(source_root)
    scenes = load_scenes(source_root)
    expected_revision = str(value.get("source_revision") or "") if isinstance(value, dict) else ""
    current_revision = source_revision(scenes)
    if not expected_revision or expected_revision != current_revision:
        raise ValueError("scenes.json changed after captions were loaded; reload before saving")

    doc = coerce_doc(value, timeline, stamp_signature=True)
    if not captions_match_timeline(doc, timeline):
        raise ValueError("captions do not match current timeline timing")
    changed_scene_ids = _changed_scene_ids(doc, timeline)
    paths = project_paths(source_root)

    if changed_scene_ids:
        cues_by_scene: dict[str, list[dict[str, Any]]] = {}
        for scene in scenes:
            scene_id = str(scene.get("id") or "")
            scene_cues = [cue for cue in doc["cues"] if cue["scene_id"] == scene_id]
            if not scene_cues or any(not str(cue.get("text") or "").strip() for cue in scene_cues):
                raise ValueError(f"scene {scene_id!r} must keep non-empty narration segments")
            cues_by_scene[scene_id] = scene_cues
        updated_scenes = normalize_scene_narrations(scenes, cues_by_scene)

        atomic_write_json(paths.scenes, updated_scenes)
        invalidate_composition_assets(source_root, scenes, updated_scenes)
        paths.captions.unlink(missing_ok=True)
        return {
            "doc": {**doc, "source_revision": source_revision(updated_scenes)},
            "saved": [str(paths.scenes)],
            "sourcePath": str(paths.scenes),
            "sourceRevision": source_revision(updated_scenes),
            "timelineInvalidated": True,
            "changedSceneIds": changed_scene_ids,
            "normalizedSceneIds": [str(scene.get("id") or "") for scene in updated_scenes],
        }

    doc = _timing_doc_with_generated_text(doc, timeline)
    write_json(paths.captions, _stored_timing_doc(doc))
    return {
        "doc": doc,
        "saved": [str(paths.captions)],
        "sourcePath": str(paths.captions),
        "sourceRevision": current_revision,
        "timelineInvalidated": False,
        "changedSceneIds": [],
    }
