#!/usr/bin/env python3
"""JSON API helpers for the local Studio web UI."""
from __future__ import annotations

import json
import hashlib
import contextlib
import io
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pipeline.factory import (
    DEFAULT_ASPECT_RATIO,
    LOCAL,
    LOCAL_WORK,
    PROJECT_MANIFEST_FILE,
    PROJECT_OUTPUT_DIR,
    ROOT,
    STARTER_SOURCE,
    activate_source,
    active_source_root,
    atomic_write_json,
    atomic_write_text,
    invalidate_composition_assets,
    is_local_project,
    normalize_aspect_ratio,
    project_paths,
    reconcile_active_project,
    rel,
    resolve_source,
    slug,
    shell_relative_url,
)
from pipeline.narration import (
    narration_chars,
    narration_language_sample,
    narration_signature,
    normalize_scene_narrations,
    source_revision,
)
from pipeline.validate_sources import (
    has_embedded_visual,
    validate_body,
    validate_captions,
    validate_scenes,
    validate_shell,
)
from pipeline.prompt_composer import compose_prompt, detect_language
from pipeline.captions import captions_match_timeline
from pipeline.tts_provider import azure_configuration_status, azure_configured, provider_options
from pipeline.voices import VOICE_OPTIONS as SHARED_VOICE_OPTIONS, voice_option, voices_for_provider
from studio.web_paths import app_url


PYTHON = sys.executable
OUTPUT_EXTENSIONS = {".mp4", ".webm"}
MEDIA_EXTENSIONS = {
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mp4",
    ".png",
    ".webm",
    ".webp",
}
JOB_LOG_LIMIT = 500
RENDER_SIZES = {"480p", "720p", "1080p", "2k", "1440p", "4k", "2160p"}
CAPTURE_MODES = {"auto", "video", "frames"}
RENDER_PROGRESS_PREFIX = "RENDER_PROGRESS "
VOICE_PREVIEW_DIR = LOCAL / "voice-preview"
VOICE_OPTIONS = SHARED_VOICE_OPTIONS
DEFAULT_TTS_SETTINGS = {
    "provider": "edge",
    "voice": "en-US-JennyNeural",
    "rate": "+12%",
    "pitch": "+0Hz",
    "gap": "0.28",
}
DEFAULT_VOICE_BY_LANGUAGE = {
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "en-US": "en-US-JennyNeural",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_time(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def read_json_file(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def output_record(path: Path) -> dict[str, Any]:
    relative_path = rel(path)
    return {
        "name": path.name,
        "path": str(path),
        "relativePath": relative_path,
        "url": app_url(f"/{quote(relative_path, safe='/')}"),
        "size": path.stat().st_size,
        "modifiedAt": file_time(path),
        "extension": path.suffix.lower().lstrip("."),
    }


def project_display_name(value: str) -> str:
    cleaned = re.sub(r"[-_.]+", " ", value).strip()
    return cleaned or "New video project"


def normalize_tts_settings(value: Any | None = None, language: str = "en-US") -> dict[str, str]:
    data = value if isinstance(value, dict) else {}
    settings = {**DEFAULT_TTS_SETTINGS}
    settings["voice"] = DEFAULT_VOICE_BY_LANGUAGE.get(language, settings["voice"])
    provider = str(data.get("provider") or settings["provider"]).strip().lower()
    if provider == "azure-speech":
        provider = "azure"
    settings["provider"] = provider if provider in {"edge", "azure"} else "edge"
    settings["voice"] = str(data.get("voice") or settings["voice"]).strip()
    settings["rate"] = str(data.get("rate") or settings["rate"]).strip()
    settings["pitch"] = str(data.get("pitch") or settings["pitch"]).strip()
    settings["gap"] = str(data.get("gap") or settings["gap"]).strip()
    return settings


def voice_matches_language(voice: str, language: str) -> bool:
    option = voice_option(voice)
    locale = option["locale"] if option else ""
    if language == "zh-CN":
        return locale == "zh-CN" or locale.endswith("-CN") or locale.startswith("zh-CN-")
    if language == "en-US":
        return locale.startswith("en-")
    return True


def azure_speech_configured() -> bool:
    return azure_configured()


def require_azure_speech_configured() -> None:
    if not azure_speech_configured():
        status = azure_configuration_status()
        raise ApiError(
            422,
            f"Azure Speech 未配置：{status['message']}",
        )


def new_project_id() -> str:
    existing_ids = set()
    if LOCAL_WORK.exists():
        for child in LOCAL_WORK.iterdir():
            manifest = read_json_file(child / PROJECT_MANIFEST_FILE) if child.is_dir() else None
            if isinstance(manifest, dict):
                existing_ids.add(str(manifest.get("id") or "").lower())
    while True:
        value = uuid.uuid4().hex[:8]
        if value not in existing_ids and not (LOCAL_WORK / value).exists():
            return value


def project_name_from_source(source_root: Path) -> str:
    scenes = read_json_file(source_root / "scenes.json")
    if isinstance(scenes, list) and scenes and isinstance(scenes[0], dict):
        title = str(scenes[0].get("title") or "").strip()
        if title:
            return title
    return project_display_name(source_root.name)


def ensure_project_manifest(
    source_root: Path,
    *,
    name: str | None = None,
    project_id: str | None = None,
    language: str | None = None,
    aspect_ratio: str | None = None,
) -> dict[str, Any]:
    manifest_path = source_root / PROJECT_MANIFEST_FILE
    existing = read_json_file(manifest_path)
    data = existing if isinstance(existing, dict) else {}
    current_id = str(project_id or data.get("id") or "").strip().lower()
    if source_root.resolve() == STARTER_SOURCE.resolve():
        current_id = "starter"
    elif not re.fullmatch(r"[0-9a-f]{8}", current_id):
        folder_id = source_root.name.lower()
        if re.fullmatch(r"[0-9a-f]{8}", folder_id):
            current_id = folder_id
        elif is_local_project(source_root):
            current_id = new_project_id()
        else:
            current_id = hashlib.sha256(str(source_root.resolve()).encode("utf-8")).hexdigest()[:8]
    now = utc_now()
    requested_language = str(language or data.get("language") or "auto")
    if requested_language not in {"auto", "zh-CN", "en-US"}:
        requested_language = "auto"
    scenes = read_json_file(source_root / "scenes.json")
    language_text = ""
    if isinstance(scenes, list):
        visible_text = " ".join(
            str(scene.get(key) or "")
            for scene in scenes if isinstance(scene, dict)
            for key in ["title", "summary"]
        )
        language_text = f"{visible_text} {narration_language_sample(scenes)}".strip()
    resolved_language = detect_language(language_text) if requested_language == "auto" else requested_language
    retained = {key: value for key, value in data.items() if key not in {"contentTheme", "engine", "theme"}}
    starter = source_root.resolve() == STARTER_SOURCE.resolve()
    stored_aspect_ratio = data.get("aspectRatio")
    if stored_aspect_ratio is not None and aspect_ratio is not None:
        if normalize_aspect_ratio(stored_aspect_ratio) != normalize_aspect_ratio(aspect_ratio):
            raise ApiError(409, "project aspect ratio is fixed after creation")
    resolved_aspect_ratio = (
        DEFAULT_ASPECT_RATIO
        if starter
        else normalize_aspect_ratio(stored_aspect_ratio or aspect_ratio)
    )
    manifest = {
        **retained,
        "version": 5,
        "id": current_id,
        "name": (
            "Starter"
            if starter
            else str(name or data.get("name") or project_name_from_source(source_root)).strip() or "Untitled project"
        ),
        "active": bool(data.get("active", starter and not data)),
        "system": starter,
        "readOnly": starter,
        "aspectRatio": resolved_aspect_ratio,
        "language": requested_language,
        "resolvedLanguage": resolved_language,
        "createdAt": str(data.get("createdAt") or now),
        "updatedAt": str(data.get("updatedAt") or now),
        "activatedAt": data.get("activatedAt") or (now if bool(data.get("active", starter and not data)) else None),
        "tts": normalize_tts_settings(data.get("tts"), resolved_language),
    }
    if is_local_project(source_root):
        source_root.mkdir(parents=True, exist_ok=True)
        if manifest != existing:
            atomic_write_json(manifest_path, manifest)
    return manifest


def ensure_local_projects() -> None:
    LOCAL_WORK.mkdir(parents=True, exist_ok=True)
    for child in list(LOCAL_WORK.iterdir()):
        if child.name.startswith(".") or not child.is_dir() or not (child / "scenes.json").exists() or not (child / "body.html").exists():
            continue
        ensure_project_manifest(child)
    reconcile_active_project(repair=True)


def read_project_settings(source_root: Path) -> dict[str, Any]:
    manifest = ensure_project_manifest(source_root)
    return {"tts": normalize_tts_settings(manifest.get("tts"), str(manifest.get("resolvedLanguage") or "en-US"))}


def write_project_settings(source_root: Path, settings: dict[str, Any]) -> None:
    manifest = ensure_project_manifest(source_root)
    if "tts" in settings:
        manifest["tts"] = normalize_tts_settings(
            settings["tts"], str(manifest.get("resolvedLanguage") or "en-US")
        )
    manifest["updatedAt"] = utc_now()
    if is_local_project(source_root):
        atomic_write_json(source_root / PROJECT_MANIFEST_FILE, manifest)


def active_source_settings() -> dict[str, Any]:
    source = active_source_root()
    if not source:
        return {"tts": normalize_tts_settings()}
    return read_project_settings(source)


def safe_project_path(value: str) -> Path:
    ensure_local_projects()
    project_id = str(value or "").strip().lower()
    if project_id == "starter":
        return STARTER_SOURCE.resolve()
    if not re.fullmatch(r"[0-9a-f]{8}", project_id):
        raise ApiError(400, "project id must be 8 hexadecimal characters")
    for child in LOCAL_WORK.iterdir():
        if not child.is_dir():
            continue
        manifest = read_json_file(child / PROJECT_MANIFEST_FILE)
        if isinstance(manifest, dict) and str(manifest.get("id") or "").lower() == project_id:
            return child.resolve()
    return (LOCAL_WORK / project_id).resolve()


def source_summary(source_root: Path) -> dict[str, Any]:
    resolved = resolve_source(source_root)
    manifest = ensure_project_manifest(resolved["root"])
    scenes = read_json_file(resolved["scenes"]) or []
    scene_count = len(scenes) if isinstance(scenes, list) else 0
    narration_char_count = 0
    title = str(manifest["name"])
    if isinstance(scenes, list) and scenes:
        narration_char_count = narration_chars(scenes)
    updated_at = max(resolved["scenes"].stat().st_mtime, resolved["body"].stat().st_mtime)
    active = active_source_root()
    return {
        "id": manifest["id"],
        "name": title,
        "title": title,
        "path": str(resolved["root"]),
        "relativePath": rel(resolved["root"]),
        "sceneCount": scene_count,
        "narrationChars": narration_char_count,
        "updatedAt": datetime.fromtimestamp(updated_at, timezone.utc).isoformat(),
        "hasCaptions": bool(resolved["captions"]),
        "hasMedia": bool(resolved["media"]),
        "language": str(manifest.get("language") or "auto"),
        "resolvedLanguage": str(manifest.get("resolvedLanguage") or "zh-CN"),
        "aspectRatio": normalize_aspect_ratio(manifest.get("aspectRatio")),
        "settings": read_project_settings(resolved["root"]),
        "active": bool(active and active.resolve() == resolved["root"].resolve()),
    }


def list_projects() -> list[dict[str, Any]]:
    ensure_local_projects()
    projects = []
    for child in sorted(LOCAL_WORK.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        try:
            projects.append(source_summary(child))
        except SystemExit:
            continue
    return projects


def list_outputs(limit: int | None = None, project_path: str | None = None) -> list[dict[str, Any]]:
    files: list[Path] = []
    if project_path:
        project_outputs = Path(project_path) / PROJECT_OUTPUT_DIR
        if project_outputs.exists():
            files.extend(
                item for item in project_outputs.iterdir()
                if item.is_file() and item.suffix.lower() in OUTPUT_EXTENSIONS
            )
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    if limit:
        files = files[:limit]
    return [output_record(item) for item in files]


def active_scenes_summary() -> dict[str, Any]:
    paths = project_paths()
    scenes_path = paths.scenes
    body_path = paths.body
    scenes = read_json_file(scenes_path) if scenes_path.exists() else None
    scene_count = len(scenes) if isinstance(scenes, list) else 0
    narration_char_count = 0
    title = ""
    if isinstance(scenes, list) and scenes:
        first = scenes[0]
        if isinstance(first, dict):
            title = str(first.get("title") or "")
        narration_char_count = narration_chars(scenes)
    source = active_source_root()
    if source:
        manifest = ensure_project_manifest(source)
        title = str(manifest.get("name") or title)
    return {
        "hasSource": scenes_path.exists() and body_path.exists(),
        "sceneCount": scene_count,
        "narrationChars": narration_char_count,
        "title": title,
    }


def timeline_summary() -> dict[str, Any]:
    paths = project_paths()
    timeline_path = paths.generated / "timeline.json"
    narration_path = paths.generated / "narration.mp3"
    result: dict[str, Any] = {
        "exists": timeline_path.exists(),
        "hasNarration": narration_path.exists(),
        "matchesSource": False,
        "state": "estimated",
        "duration": None,
        "error": None,
    }
    if not timeline_path.exists():
        return result

    timeline = read_json_file(timeline_path)
    if not isinstance(timeline, dict):
        result["state"] = "invalid"
        result["error"] = "timeline.json is invalid"
        return result

    source_scenes = read_json_file(paths.scenes)
    source_signature = narration_signature(source_scenes) if isinstance(source_scenes, list) else []
    timeline_signature = narration_signature(
        [scene for scene in timeline.get("scenes", []) if isinstance(scene, dict)]
    )
    result["matchesSource"] = bool(source_signature and source_signature == timeline_signature)
    result["duration"] = timeline.get("duration")
    result["state"] = "ready" if result["matchesSource"] and narration_path.exists() else "stale"
    if not result["matchesSource"]:
        result["error"] = "timeline/audio do not match the active project source"
    return result


def caption_summary(timeline: dict[str, Any]) -> dict[str, Any]:
    paths = project_paths()
    captions = read_json_file(paths.captions)
    if not paths.captions.exists():
        return {
            "state": "generated" if timeline.get("matchesSource") else "estimated",
            "manual": False,
        }
    if captions is None:
        return {"state": "stale", "manual": True}
    generated_timeline = read_json_file(paths.generated / "timeline.json")
    try:
        current = bool(
            isinstance(generated_timeline, dict)
            and timeline.get("matchesSource")
            and captions_match_timeline(captions, generated_timeline)
        )
    except (TypeError, ValueError):
        current = False
    return {
        "state": "manual" if current else "stale",
        "manual": True,
    }


def active_project_meta(source_root: Path | None = None) -> dict[str, Any] | None:
    source = source_root or active_source_root()
    manifest = ensure_project_manifest(source)
    return {
        "id": manifest["id"],
        "name": manifest["name"],
        "path": str(source),
        "relativePath": rel(source),
        "language": manifest.get("language", "auto"),
        "resolvedLanguage": manifest.get("resolvedLanguage", "zh-CN"),
        "aspectRatio": normalize_aspect_ratio(manifest.get("aspectRatio")),
        "settings": read_project_settings(source),
        "loadedAt": manifest.get("activatedAt"),
    }


def guide_state(state: dict[str, Any]) -> dict[str, str]:
    has_projects = bool(state["projectCount"])
    has_source = bool(state["projectSummary"]["hasSource"])
    timeline = state["timeline"]
    has_ready_timeline = bool(timeline["exists"] and timeline["hasNarration"] and timeline["matchesSource"])
    has_outputs = bool(state["outputs"])
    if not has_projects and not has_source:
        return {
            "stage": "create",
            "title": "Create a video source first",
            "body": "Fill in the prompt, use a web AI to generate scenes.json and body.html, then paste them here to save a local project.",
        }
    if not has_source:
        return {
            "stage": "load",
            "title": "Choose a local project",
            "body": "Choose a project from the list. Studio previews it directly from its project folder.",
        }
    if not has_ready_timeline:
        return {
            "stage": "build",
            "title": "Generate TTS and the timeline next",
            "body": "The active project is ready. The preview uses estimated timing until real narration is generated.",
        }
    if not has_outputs:
        return {
            "stage": "preview",
            "title": "Ready to preview and render",
            "body": "The timeline and narration are ready. Review the visuals, then edit captions or render an MP4.",
        }
    return {
        "stage": "done",
        "title": "A rendered result is ready to view",
        "body": "You can continue iterating on the source files or play the latest finished video directly from Outputs.",
    }


def studio_state() -> dict[str, Any]:
    ensure_local_projects()
    active_project = active_project_meta()
    output_path = active_project["path"] if active_project else None
    project_summary = active_scenes_summary()
    timeline = timeline_summary()
    source_state = "missing"
    source_error = None
    if project_summary.get("hasSource"):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                validate_project(active_source_root())
            source_state = "ready"
        except ApiError as exc:
            source_state = "invalid"
            source_error = exc.message
    state: dict[str, Any] = {
        "activeProject": active_project,
        "hasStarter": STARTER_SOURCE.exists(),
        "projectSummary": project_summary,
        "settings": active_source_settings(),
        "voiceOptions": VOICE_OPTIONS,
        "ttsProviders": provider_options(),
        "suggestedOutputName": suggested_output_name(active_source_root()),
        "timeline": timeline,
        "status": {
            "source": source_state,
            "sourceError": source_error,
            "narration": timeline.get("state", "estimated"),
            "captions": caption_summary(timeline).get("state", "estimated"),
            "layout": "preview",
        },
        "projectCount": len(list_projects()),
        "outputs": list_outputs(limit=5, project_path=output_path),
        "urls": {
            "studio": app_url("/studio"),
            "source": app_url("/source"),
            "shell": app_url(shell_relative_url(active_source_root())),
            "captions": app_url("/captions"),
            "voices": app_url("/voices"),
        },
    }
    state["guide"] = guide_state(state)
    return state


def normalize_submitted_scenes(
    scenes_json: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Accept a simple draft at the API boundary and return canonical project source."""
    if not scenes_json.strip():
        raise ApiError(400, "scenesJson is required")
    try:
        parsed = json.loads(scenes_json)
    except json.JSONDecodeError as exc:
        raise ApiError(422, f"scenes.json is invalid JSON: {exc}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ApiError(422, "scenes.json must be a non-empty JSON array")
    for index, scene in enumerate(parsed, 1):
        if not isinstance(scene, dict):
            raise ApiError(422, f"scene {index} must be an object")
        narration = scene.get("narration")
        if isinstance(narration, dict):
            segments = narration.get("segments")
            if isinstance(segments, list) and any(not isinstance(segment, dict) for segment in segments):
                raise ApiError(422, f"scene {index} narration segments must be objects")
    normalized = normalize_scene_narrations(parsed)
    normalized_json = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    return parsed, normalized, normalized_json


def validate_normalized_source_text(
    scenes_json: str,
    body_html: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    *,
    require_bookends: bool = True,
) -> dict[str, Any]:
    if not body_html.strip():
        raise ApiError(400, "bodyHtml is required")
    with tempfile.TemporaryDirectory(prefix="studio-source-") as temp_dir:
        temp = Path(temp_dir)
        scenes_path = temp / "scenes.json"
        body_path = temp / "body.html"
        scenes_path.write_text(scenes_json, encoding="utf-8")
        body_path.write_text(body_html, encoding="utf-8")
        try:
            scenes = validate_scenes(
                scenes_path,
                aspect_ratio=aspect_ratio,
                require_bookends=require_bookends,
            )
            validate_body(body_path, scenes)
            validate_shell()
        except SystemExit as exc:
            raise ApiError(422, str(exc)) from exc
    return {
        "ok": True,
        "sceneCount": len(scenes),
        "narrationChars": narration_chars(scenes),
        "resolvedLanguage": detect_language(narration_language_sample(scenes)),
        "hasEmbeddedStyle": "<style" in body_html.lower(),
        "hasEmbeddedVisual": has_embedded_visual(body_html),
    }


def validate_source_text(
    scenes_json: str,
    body_html: str,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    *,
    require_bookends: bool = True,
) -> dict[str, Any]:
    parsed, normalized, normalized_json = normalize_submitted_scenes(scenes_json)
    result = validate_normalized_source_text(
        normalized_json,
        body_html,
        aspect_ratio,
        require_bookends=require_bookends,
    )
    return {
        **result,
        "narrationNormalized": parsed != normalized,
    }


def validate_project(source_root: Path) -> dict[str, Any]:
    try:
        resolved = resolve_source(source_root)
        manifest = ensure_project_manifest(resolved["root"])
        scenes = validate_scenes(
            resolved["scenes"],
            aspect_ratio=normalize_aspect_ratio(manifest.get("aspectRatio")),
        )
        validate_body(resolved["body"], scenes)
        if resolved["captions"]:
            validate_captions(resolved["captions"])
        validate_shell()
    except SystemExit as exc:
        raise ApiError(422, str(exc)) from exc
    return {
        "ok": True,
        "sceneCount": len(scenes),
        "narrationChars": narration_chars(scenes),
    }


def save_project_body(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("project") or payload.get("id") or "").strip()
    body_html = str(payload.get("bodyHtml") or "")
    if not body_html.strip():
        raise ApiError(400, "bodyHtml is required")

    source_root = project_for_id(project_id)
    manifest = ensure_project_manifest(source_root)
    try:
        scenes = validate_scenes(
            source_root / "scenes.json",
            aspect_ratio=normalize_aspect_ratio(manifest.get("aspectRatio")),
            # A visual-only edit must not be blocked by an unrelated narration
            # bookend problem in an existing project. Full validation still
            # enforces intro/outro before source replacement and builds.
            require_bookends=False,
        )
        with tempfile.TemporaryDirectory(prefix="studio-body-") as temp_dir:
            body_path = Path(temp_dir) / "body.html"
            body_path.write_text(body_html, encoding="utf-8")
            validate_body(body_path, scenes)
    except SystemExit as exc:
        raise ApiError(422, str(exc)) from exc

    saved_body = body_html.strip() + "\n"
    atomic_write_text(source_root / "body.html", saved_body)
    activate_source(source_root)
    return {
        "project": source_summary(source_root),
        "bodyHtml": saved_body,
        "timelineInvalidated": False,
    }


def create_project(
    payload: dict[str, Any],
    *,
    require_bookends: bool = True,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    project_id = str(payload.get("project") or payload.get("id") or "").strip().lower()
    scenes_json = str(payload.get("scenesJson") or "")
    body_html = str(payload.get("bodyHtml") or "")
    overwrite = bool(payload.get("overwrite"))
    try:
        aspect_ratio = normalize_aspect_ratio(payload.get("aspectRatio"))
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    if overwrite and project_id == "starter":
        raise ApiError(400, "starter is read-only; save the source as a new project")
    previous_scenes: Any = None
    if overwrite:
        if not project_id:
            raise ApiError(400, "project id is required when replacing a project")
        target = safe_project_path(project_id)
        if not target.exists():
            raise ApiError(404, f"project not found: {project_id}")
        previous_scenes = read_json_file(target / "scenes.json")
        expected_revision = str(payload.get("sourceRevision") or "")
        if expected_revision and isinstance(previous_scenes, list):
            if expected_revision != source_revision(previous_scenes):
                raise ApiError(409, "scenes.json changed in another editor; reload before saving")
        existing_manifest = ensure_project_manifest(target)
        existing_aspect_ratio = normalize_aspect_ratio(existing_manifest.get("aspectRatio"))
        if "aspectRatio" in payload and aspect_ratio != existing_aspect_ratio:
            raise ApiError(409, "project aspect ratio is fixed after creation")
        aspect_ratio = existing_aspect_ratio
        name = name or str(existing_manifest["name"])
    else:
        project_id = new_project_id()
        target = LOCAL_WORK / project_id
    name = name or "Untitled project"
    parsed_scenes, normalized_scenes, normalized_scenes_json = normalize_submitted_scenes(scenes_json)
    validation = validate_normalized_source_text(
        normalized_scenes_json,
        body_html,
        aspect_ratio,
        require_bookends=require_bookends,
    )

    write_target = target
    if not overwrite:
        write_target = LOCAL_WORK / f".{project_id}.creating"
        shutil.rmtree(write_target, ignore_errors=True)
    write_target.mkdir(parents=True, exist_ok=True)
    atomic_write_text(write_target / "scenes.json", normalized_scenes_json)
    atomic_write_text(write_target / "body.html", body_html.strip() + "\n")
    existing = existing_manifest if overwrite else {}
    language = str(payload.get("language") or existing.get("language") or "auto")
    ensure_project_manifest(
        write_target,
        name=name,
        project_id=project_id,
        language=language,
        aspect_ratio=aspect_ratio,
    )
    if payload.get("tts") is not None:
        write_project_settings(write_target, {"tts": payload.get("tts")})
    if not overwrite:
        write_target.replace(target)
    current_scenes = read_json_file(target / "scenes.json")
    previous_timeline_signature = (
        narration_signature(previous_scenes) if isinstance(previous_scenes, list) else []
    )
    current_timeline_signature = (
        narration_signature(current_scenes) if isinstance(current_scenes, list) else []
    )
    timeline_invalidated = bool(
        overwrite and previous_timeline_signature != current_timeline_signature
    )
    if timeline_invalidated:
        invalidate_composition_assets(target, previous_scenes, current_scenes)
    captions = target / "captions.json"
    if timeline_invalidated and captions.exists():
        captions.unlink()
    activate_source(target)
    return {
        "project": source_summary(target),
        "validation": validation,
        "scenesJson": normalized_scenes_json,
        "narrationNormalized": parsed_scenes != normalized_scenes,
        "timelineInvalidated": timeline_invalidated,
        "sourceRevision": source_revision(current_scenes) if isinstance(current_scenes, list) else "",
        "state": studio_state(),
    }


def save_project_draft(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("project") or payload.get("id") or "").strip()
    if not project_id:
        raise ApiError(400, "project id is required when saving a draft")
    result = create_project(
        {
            **payload,
            "project": project_id,
            "overwrite": True,
        },
        require_bookends=False,
    )
    result["draft"] = True
    return result


def activate_project(payload: dict[str, Any]) -> dict[str, Any]:
    value = str(payload.get("project") or payload.get("id") or "").strip()
    if value in {"starter", ".local/work/starter", "templates/starter"}:
        source_root = STARTER_SOURCE
    else:
        source_root = safe_project_path(value)
    ensure_project_manifest(source_root)
    try:
        resolve_source(source_root)
        activate_source(source_root)
    except SystemExit as exc:
        raise ApiError(422, str(exc)) from exc
    return {"project": source_summary(source_root), "state": studio_state()}


def project_source(query: dict[str, list[str]]) -> dict[str, Any]:
    value = (query.get("project") or query.get("id") or [""])[0].strip()
    source_root = safe_project_path(value) if value else active_source_root()
    if not source_root:
        raise ApiError(404, "project not found")
    try:
        resolved = resolve_source(source_root)
    except SystemExit as exc:
        raise ApiError(422, str(exc)) from exc
    source_scenes = read_json_file(resolved["scenes"])
    return {
        "project": source_summary(source_root),
        "sourceRevision": source_revision(source_scenes if isinstance(source_scenes, list) else []),
        "files": {
            "scenesJson": resolved["scenes"].read_text(encoding="utf-8"),
            "bodyHtml": resolved["body"].read_text(encoding="utf-8"),
        },
    }


def project_for_id(value: str = "") -> Path:
    source_root = safe_project_path(value) if value else active_source_root()
    if not source_root:
        raise ApiError(404, "project not found")
    if source_root.resolve() == STARTER_SOURCE.resolve():
        raise ApiError(400, "starter is read-only")
    try:
        resolve_source(source_root)
    except SystemExit as exc:
        raise ApiError(422, str(exc)) from exc
    return source_root


def normalize_media_path(value: str) -> Path:
    raw = str(value or "").strip().replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    if raw.startswith("media/"):
        raw = raw[6:]
    path = Path(raw)
    if not raw or path.is_absolute() or path.drive or any(part in {"", ".", ".."} for part in path.parts):
        raise ApiError(400, "media path must be a safe relative path inside media/")
    if path.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ApiError(400, "unsupported media type; use PNG, JPEG, WebP, AVIF, GIF, MP4, or WebM")
    return path


def body_media_references(body: str) -> list[str]:
    values = re.findall(
        r"""(?:src|poster)\s*=\s*["']([^"']+)["']|url\(\s*["']?([^"')]+)""",
        body,
        re.IGNORECASE,
    )
    references: set[str] = set()
    for groups in values:
        value = next((item for item in groups if item), "").strip()
        clean = value.split("#", 1)[0].split("?", 1)[0].replace("\\", "/")
        clean = clean[2:] if clean.startswith("./") else clean
        if not clean.startswith("media/"):
            continue
        try:
            references.add(f"media/{normalize_media_path(clean).as_posix()}")
        except ApiError:
            continue
    return sorted(references)


def media_state(query: dict[str, list[str]]) -> dict[str, Any]:
    project_id = (query.get("project") or query.get("id") or [""])[0].strip()
    source_root = project_for_id(project_id)
    paths = project_paths(source_root)
    references = body_media_references(paths.body.read_text(encoding="utf-8"))
    files = []
    if paths.media.exists():
        for path in sorted(item for item in paths.media.rglob("*") if item.is_file()):
            relative = path.relative_to(paths.media).as_posix()
            source_relative = f"media/{relative}"
            files.append({
                "name": path.name,
                "path": source_relative,
                "url": app_url(f"/{quote(rel(path), safe='/')}"),
                "size": path.stat().st_size,
                "contentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "referenced": source_relative in references,
            })
    existing = {item["path"] for item in files}
    return {
        "project": source_summary(source_root),
        "files": files,
        "references": references,
        "missing": [value for value in references if value not in existing],
    }


def save_media(project_id: str, value: str, data: bytes) -> dict[str, Any]:
    source_root = project_for_id(project_id)
    relative = normalize_media_path(value)
    target = (project_paths(source_root).media / relative).resolve()
    try:
        target.relative_to((source_root / "media").resolve())
    except ValueError as exc:
        raise ApiError(400, "media path escapes the project media folder") from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_bytes(data)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return {"saved": f"media/{relative.as_posix()}", "media": media_state({"project": [project_id]})}


def delete_media(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("project") or payload.get("id") or "").strip()
    source_root = project_for_id(project_id)
    relative = normalize_media_path(str(payload.get("path") or ""))
    target = (project_paths(source_root).media / relative).resolve()
    try:
        target.relative_to((source_root / "media").resolve())
    except ValueError as exc:
        raise ApiError(400, "media path escapes the project media folder") from exc
    if not target.exists() or not target.is_file():
        raise ApiError(404, f"media file not found: media/{relative.as_posix()}")
    target.unlink()
    parent = target.parent
    media_root = (source_root / "media").resolve()
    while parent != media_root and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    if media_root.exists() and not any(media_root.iterdir()):
        media_root.rmdir()
    return {"deleted": f"media/{relative.as_posix()}", "media": media_state({"project": [project_id]})}


def save_project_settings(payload: dict[str, Any]) -> dict[str, Any]:
    value = str(payload.get("project") or payload.get("id") or "").strip()
    source_root = safe_project_path(value) if value else active_source_root()
    if not source_root:
        raise ApiError(409, "no active project; activate or create a project first")
    if not source_root.exists() or not source_root.is_dir():
        raise ApiError(404, f"project not found: {source_root.name}")
    write_project_settings(source_root, {"tts": payload.get("tts") or payload})
    return {"project": source_summary(source_root), "settings": read_project_settings(source_root)}


def update_project_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    value = str(payload.get("project") or payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not value:
        raise ApiError(400, "project id is required")
    if value == "starter":
        raise ApiError(400, "starter is read-only")
    if not name:
        raise ApiError(400, "project name is required")
    source_root = safe_project_path(value)
    if not source_root.exists() or not source_root.is_dir():
        raise ApiError(404, f"project not found: {value}")
    manifest = ensure_project_manifest(source_root, name=name)
    manifest["updatedAt"] = utc_now()
    atomic_write_json(source_root / PROJECT_MANIFEST_FILE, manifest)
    return {"project": source_summary(source_root)}


def delete_project(payload: dict[str, Any]) -> dict[str, Any]:
    value = str(payload.get("project") or payload.get("id") or "").strip()
    if not value:
        raise ApiError(400, "project id is required")
    if value in {"starter", ".local/work/starter", "templates/starter"}:
        raise ApiError(400, "starter cannot be deleted")
    target = safe_project_path(value)
    if not target.exists() or not target.is_dir():
        raise ApiError(404, f"project not found: {target.name}")
    active = active_source_root()
    was_active = bool(active and active.resolve() == target.resolve())
    shutil.rmtree(target)
    if was_active:
        activate_source(STARTER_SOURCE)
    return {"deleted": target.name, "wasActive": was_active, "state": studio_state()}


def active_job() -> dict[str, Any] | None:
    with JOBS_LOCK:
        for job in JOBS.values():
            if job.get("status") in {"queued", "running"}:
                return job
    return None


def job_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    progress = job.get("progress")
    return {
        "id": job["id"],
        "task": job["task"],
        "status": job["status"],
        "exitCode": job.get("exitCode"),
        "createdAt": job["createdAt"],
        "startedAt": job.get("startedAt"),
        "finishedAt": job.get("finishedAt"),
        "command": job["command"],
        "log": job["log"][-JOB_LOG_LIMIT:],
        "progress": dict(progress) if isinstance(progress, dict) else None,
    }


def parse_render_progress(line: str) -> dict[str, Any] | None:
    if not line.startswith(RENDER_PROGRESS_PREFIX):
        return None
    try:
        progress = json.loads(line[len(RENDER_PROGRESS_PREFIX) :])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(progress, dict):
        return None
    try:
        progress["percent"] = min(100.0, max(0.0, float(progress.get("percent", 0))))
    except (TypeError, ValueError):
        progress["percent"] = 0.0
    return progress


def progress_console_line(progress: dict[str, Any]) -> str:
    percent = float(progress.get("percent") or 0)
    rendered = int(progress.get("renderedFrames") or 0)
    encoded = int(progress.get("encodedFrames") or 0)
    total = int(progress.get("totalFrames") or 0)
    fps = float(progress.get("encodeFps") or 0)
    speed = float(progress.get("speed") or 0)
    eta = progress.get("etaSeconds")
    eta_text = f"{max(0, round(float(eta)))}s" if eta is not None else "--"
    return (
        f"{progress.get('phase', 'rendering')} {percent:.2f}% "
        f"capture={rendered}/{total} encode={encoded}/{total} "
        f"fps={fps:.1f} speed={speed:.3f}x eta={eta_text}"
    )


def append_job_log(job_id: str, line: str) -> None:
    clean_line = line.rstrip()
    progress = parse_render_progress(clean_line)
    task = "job"
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        task = str(job.get("task") or task)
        if progress is not None:
            job["progress"] = progress
        else:
            job["log"].append(clean_line)
            if len(job["log"]) > JOB_LOG_LIMIT:
                job["log"] = job["log"][-JOB_LOG_LIMIT:]
    if clean_line:
        output = progress_console_line(progress) if progress is not None else clean_line
        print(f"[job:{job_id} {task}] {output}", flush=True)


def set_job_fields(job_id: str, **fields: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def finish_render_progress(job_id: str, succeeded: bool) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job.get("task") != "render":
            return
        progress = dict(job.get("progress") or {})
        progress["phase"] = "completed" if succeeded else "failed"
        if succeeded:
            progress.update({"percent": 100.0, "etaSeconds": 0.0})
        job["progress"] = progress


def run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        command = list(job["command"])
    set_job_fields(job_id, status="running", startedAt=utc_now())
    print(f"[job:{job_id} {job['task']}] started: {' '.join(command)}", flush=True)
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        set_job_fields(job_id, pid=process.pid)
        assert process.stdout is not None
        for line in process.stdout:
            append_job_log(job_id, line)
        exit_code = process.wait()
        set_job_fields(
            job_id,
            status="succeeded" if exit_code == 0 else "failed",
            exitCode=exit_code,
            finishedAt=utc_now(),
        )
        finish_render_progress(job_id, exit_code == 0)
        print(f"[job:{job_id} {job['task']}] {'completed' if exit_code == 0 else 'failed'} (exit {exit_code})", flush=True)
    except Exception as exc:  # noqa: BLE001 - surface background failures to the UI.
        append_job_log(job_id, f"Job failed before completion: {exc}")
        set_job_fields(job_id, status="failed", exitCode=-1, finishedAt=utc_now())
        finish_render_progress(job_id, False)


def clean_output_name(value: str) -> str:
    filename = Path(value or "video.mp4").name
    stem = re.sub(r"\.mp4$", "", filename, flags=re.IGNORECASE)
    name = re.sub(r"[^\w\-]+", "-", stem, flags=re.UNICODE).strip("-_") or "video"
    return f"{name}.mp4"


def next_sequenced_output_name(value: str, filenames: list[str]) -> str:
    base = Path(clean_output_name(value)).stem
    pattern = re.compile(rf"^{re.escape(base)}-(\d+)\.mp4$", re.IGNORECASE)
    highest = max(
        (int(match.group(1)) for name in filenames if (match := pattern.fullmatch(name))),
        default=0,
    )
    return f"{base}-{highest + 1:02d}.mp4"


def suggested_output_name(source_root: Path | None = None) -> str:
    source = source_root or active_source_root()
    if not source:
        return "video-01.mp4"
    manifest = ensure_project_manifest(source)
    base = str(manifest.get("name") or manifest.get("id") or "video")
    output_dir = source / PROJECT_OUTPUT_DIR
    filenames = (
        [item.name for item in output_dir.iterdir() if item.is_file()]
        if output_dir.exists()
        else []
    )
    return next_sequenced_output_name(base, filenames)


def command_for_job(payload: dict[str, Any], source_root: Path | None = None) -> tuple[str, list[str]]:
    task = str(payload.get("task") or "").strip().lower()
    if task not in {"tts", "offline", "check", "render", "voice-preview"}:
        raise ApiError(400, "unknown job task")

    if task == "voice-preview":
        provider = str(payload.get("provider") or "edge").strip().lower()
        if provider not in {"edge", "azure"}:
            raise ApiError(400, "unsupported TTS provider")
        if provider == "azure":
            require_azure_speech_configured()
        text = str(payload.get("text") or "").strip()
        voice = str(payload.get("voice") or "zh-CN-XiaoxiaoNeural").strip()
        rate = str(payload.get("rate") or "+0%").strip()
        pitch = str(payload.get("pitch") or "+0Hz").strip()
        if not text or len(text) > 3000:
            raise ApiError(400, "voice preview text must contain 1 to 3000 characters")
        if voice not in {item["id"] for item in voices_for_provider(provider)}:
            raise ApiError(400, "unsupported voice")
        if not re.fullmatch(r"[+-](?:[0-9]|[1-4][0-9]|50)%", rate):
            raise ApiError(400, "rate must be between -50% and +50%")
        if not re.fullmatch(r"[+-](?:[0-9]|1[0-9]|2[0-4])Hz", pitch):
            raise ApiError(400, "pitch must be between -24Hz and +24Hz")
        return task, [
            PYTHON,
            "main.py",
            "voice-preview",
            "--provider",
            provider,
            "--voice",
            voice,
            "--text",
            text,
            "--rate",
            rate,
            "--pitch",
            pitch,
        ]

    source = source_root or active_source_root()
    source_args = ["--source", str(source)]

    if task == "tts":
        if source and source.exists() and source.is_dir():
            manifest = ensure_project_manifest(source)
            language = str(manifest.get("resolvedLanguage") or "en-US")
            saved_tts = normalize_tts_settings(manifest.get("tts"), language)
        else:
            language = "en-US"
            saved_tts = normalize_tts_settings(language=language)
        if not payload.get("voice") and not voice_matches_language(saved_tts["voice"], language):
            saved_tts["voice"] = DEFAULT_VOICE_BY_LANGUAGE.get(language, DEFAULT_TTS_SETTINGS["voice"])
        overrides = {
            key: payload[key]
            for key in ["provider", "voice", "rate", "pitch", "gap"]
            if payload.get(key) not in {None, ""}
        }
        tts_settings = normalize_tts_settings({**saved_tts, **overrides}, language)
        if tts_settings["provider"] == "azure":
            require_azure_speech_configured()
        if tts_settings["voice"] not in {
            item["id"] for item in voices_for_provider(tts_settings["provider"])
        }:
            raise ApiError(400, "unsupported voice")
        if not re.fullmatch(r"[+-](?:[0-9]|[1-4][0-9]|50)%", tts_settings["rate"]):
            raise ApiError(400, "rate must be between -50% and +50%")
        if not re.fullmatch(r"[+-](?:[0-9]|1[0-9]|2[0-4])Hz", tts_settings["pitch"]):
            raise ApiError(400, "pitch must be between -24Hz and +24Hz")
        try:
            gap = float(tts_settings["gap"])
        except ValueError as exc:
            raise ApiError(400, "gap must be a number between 0 and 5") from exc
        if not 0 <= gap <= 5:
            raise ApiError(400, "gap must be a number between 0 and 5")
        if source and source.exists() and source.is_dir():
            write_project_settings(source, {"tts": tts_settings})
        command = [
            PYTHON,
            "main.py",
            "tts",
            "--provider",
            tts_settings["provider"],
            "--voice",
            tts_settings["voice"],
            "--rate",
            tts_settings["rate"],
            "--pitch",
            tts_settings["pitch"],
            "--gap",
            tts_settings["gap"],
            *source_args,
        ]
        if payload.get("force"):
            command.append("--force")
        return task, command

    if task == "offline":
        return task, [PYTHON, "main.py", "offline", *source_args]

    if task == "check":
        return task, [PYTHON, "main.py", "check", *source_args]

    size = str(payload.get("size") or "720p").lower()
    capture = str(payload.get("capture") or "auto").lower()
    if size not in RENDER_SIZES:
        raise ApiError(400, "invalid render size")
    if capture not in CAPTURE_MODES:
        raise ApiError(400, "invalid capture mode")
    fps = int(payload.get("fps") or 15)
    fps = min(max(fps, 1), 60)
    try:
        transition = float(payload.get("transition", 0.4))
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "transition must be a number between 0 and 2 seconds") from exc
    if not 0 <= transition <= 2:
        raise ApiError(400, "transition must be between 0 and 2 seconds")
    return task, [
        PYTHON,
        "main.py",
        "render",
        "--size",
        size,
        "--capture",
        capture,
        "--fps",
        str(fps),
        "--output",
        clean_output_name(str(payload.get("output") or suggested_output_name(source))),
        "--transition",
        f"{transition:g}",
        *source_args,
    ]


def start_job(payload: dict[str, Any]) -> dict[str, Any]:
    running = active_job()
    if running:
        raise ApiError(409, f"{running['task']} is already running")
    requested_task = str(payload.get("task") or "").strip().lower()
    source_snapshot = None if requested_task == "voice-preview" else active_source_root()
    task, command = command_for_job(payload, source_snapshot)
    if task in {"tts", "offline", "check", "render"}:
        try:
            project_paths(source_snapshot)
        except SystemExit as exc:
            raise ApiError(409, str(exc)) from exc

    job_id = uuid.uuid4().hex[:12]
    active_project = None if task == "voice-preview" else active_project_meta(source_snapshot)
    output_name = ""
    if task == "render":
        output_name = clean_output_name(
            str(payload.get("output") or suggested_output_name(source_snapshot))
        )
    job = {
        "id": job_id,
        "task": task,
        "command": command,
        "projectId": active_project["id"] if active_project else None,
        "projectPath": active_project["path"] if active_project else None,
        "outputName": output_name,
        "status": "queued",
        "exitCode": None,
        "createdAt": utc_now(),
        "startedAt": None,
        "finishedAt": None,
        "log": [],
        "progress": (
            {"phase": "queued", "percent": 0.0, "etaSeconds": None}
            if task == "render"
            else None
        ),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    thread.start()
    time.sleep(0.02)
    with JOBS_LOCK:
        return {"job": job_snapshot(JOBS[job_id])}


def get_job(query: dict[str, list[str]]) -> dict[str, Any]:
    job_id = (query.get("id") or [""])[0]
    if not job_id:
        raise ApiError(400, "job id is required")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise ApiError(404, "job not found")
        return {"job": job_snapshot(job)}


def voice_preview_state() -> dict[str, Any]:
    VOICE_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_json_file(VOICE_PREVIEW_DIR / "manifest.json")
    if not isinstance(manifest, dict):
        manifest = {"samples": [], "history": []}
    samples = manifest.get("samples")
    if not isinstance(samples, list):
        samples = []
    history = manifest.get("history")
    if not isinstance(history, list):
        history = samples
    samples = [
        {
            **item,
            "audio": app_url(str(item.get("audio") or "")),
            "provider": "azure" if item.get("provider") == "azure-speech" else item.get("provider") or "edge",
        }
        for item in samples if isinstance(item, dict)
    ]
    history = [
        {
            **item,
            "audio": app_url(str(item.get("audio") or "")),
            "provider": "azure" if item.get("provider") == "azure-speech" else item.get("provider") or "edge",
        }
        for item in history if isinstance(item, dict)
    ]
    manifest = {**manifest, "samples": samples, "history": history}
    return {
        "voices": VOICE_OPTIONS,
        "providers": provider_options(),
        "manifest": manifest,
        "history": history[:20],
        "outputUrl": app_url("/.local/voice-preview/"),
    }


def handle_get(path: str, query: dict[str, list[str]]) -> tuple[int, Any] | None:
    if path == "/api/studio/state":
        return 200, studio_state()
    if path == "/api/projects":
        return 200, {"projects": list_projects()}
    if path == "/api/projects/source":
        return 200, project_source(query)
    if path == "/api/projects/media":
        return 200, media_state(query)
    if path == "/api/outputs":
        active_project = active_project_meta()
        return 200, {
            "outputs": list_outputs(project_path=active_project["path"] if active_project else None),
            "suggestedOutputName": suggested_output_name(active_source_root()),
        }
    if path == "/api/voice-preview":
        return 200, voice_preview_state()
    if path == "/api/jobs":
        return 200, get_job(query)
    return None


def handle_post(path: str, payload: dict[str, Any]) -> tuple[int, Any] | None:
    if path == "/api/prompt":
        try:
            return 200, compose_prompt(payload)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise ApiError(422, str(exc)) from exc
    if path == "/api/projects":
        return 201, create_project(payload)
    if path == "/api/projects/source/draft":
        return 200, save_project_draft(payload)
    if path == "/api/projects/source/body":
        return 200, save_project_body(payload)
    if path == "/api/projects/activate":
        return 200, activate_project(payload)
    if path == "/api/projects/settings":
        return 200, save_project_settings(payload)
    if path == "/api/projects/update":
        return 200, update_project_metadata(payload)
    if path == "/api/projects/delete":
        return 200, delete_project(payload)
    if path == "/api/projects/media/delete":
        return 200, delete_media(payload)
    if path == "/api/source/validate":
        if payload.get("project") or payload.get("id"):
            return 200, validate_project(safe_project_path(str(payload.get("project") or payload.get("id"))))
        try:
            aspect_ratio = normalize_aspect_ratio(payload.get("aspectRatio"))
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        return 200, validate_source_text(
            str(payload.get("scenesJson") or ""),
            str(payload.get("bodyHtml") or ""),
            aspect_ratio,
        )
    if path == "/api/jobs":
        return 202, start_job(payload)
    return None
