#!/usr/bin/env python3
"""Validate a loaded or provided video source folder and render shell."""
from __future__ import annotations

import argparse
import json
import math
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from .factory import DEFAULT_ASPECT_RATIO, SHELL, ensure_shell, normalize_aspect_ratio, project_paths, read_json
    from .narration import SEGMENT_ID_RE, authored_segments, caption_units, narration_chars, narration_text
except ImportError:  # Direct script execution: python pipeline/validate_sources.py
    from factory import DEFAULT_ASPECT_RATIO, SHELL, ensure_shell, normalize_aspect_ratio, project_paths, read_json
    from narration import SEGMENT_ID_RE, authored_segments, caption_units, narration_chars, narration_text


ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CATEGORY_UNIT_LIMIT = 12.0
PORTRAIT_CATEGORY_UNIT_LIMIT = 4.0
FORBIDDEN_BODY_MARKERS = {
    "topbar": "body.html must not include template chrome such as headers",
    "transport": "body.html must not include playback controls",
    "playbutton": "body.html must not include playback controls",
    "scrubber": "body.html must not include playback controls",
    "progress-line": "body.html must not draw per-scene progress bars; the shell owns the chapter rail",
    "chapterrail": "body.html must not include the chapter rail; it is generated from scenes.json",
    "chapter-rail": "body.html must not include the chapter rail; it is generated from scenes.json",
}
ASSISTANT_NARRATION_MARKERS = [
    "大家好",
    "接下来我们",
    "让我们",
    "我们不只",
    "不要只问",
    "值得注意的是",
    "可以看到",
    "不难发现",
    "总的来说",
    "希望能帮助你",
    "in this video",
    "let's take a look",
]
MOTION_PRESETS = {
    "fade",
    "rise",
    "slide-left",
    "wipe-left",
    "zoom-in",
    "ken-burns-in",
    "pan-left",
    "pan-right",
    "pulse-once",
}

MEDIA_TIMING_ATTRIBUTES = ("data-media-in", "data-media-out", "data-media-start", "data-media-rate")
CSS_URL_RE = re.compile(r"url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)]*))\s*\)", re.IGNORECASE)
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class VisualSourceParser(HTMLParser):
    """Collect source media and cue groups without interpreting scripts or fetching URLs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str | None]] = []
        self.media: list[dict] = []
        self.shots: list[dict] = []
        self.videos: list[dict] = []
        self.timed_elements: list[dict] = []
        self.studio_ids: list[str] = []

    def add_reference(self, value: str | None, scene_id: str | None, tag: str, attribute: str) -> None:
        value = (value or "").strip()
        if not value or value.startswith("#") or value.lower().startswith("data:"):
            return
        self.media.append({"path": value, "scene_id": scene_id, "tag": tag, "attribute": attribute})

    def add_css(self, css: str, scene_id: str | None, tag: str) -> None:
        for match in CSS_URL_RE.finditer(css):
            self.add_reference(next(value for value in match.groups() if value is not None), scene_id, tag, "url")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("data-studio-id"):
            self.studio_ids.append(attributes["data-studio-id"].strip())
        parent_scene = self.stack[-1][1] if self.stack else None
        scene_id = attributes.get("data-scene", parent_scene)
        if tag in {"img", "video", "source", "image"}:
            for attribute in ("src", "href", "xlink:href"):
                self.add_reference(attributes.get(attribute), scene_id, tag, attribute)
            if tag in {"img", "source"}:
                # Ordinary local/HTTP srcsets; data-URI candidates are intentionally ignored.
                srcset = re.sub(r"data:[^\s]+(?:\s+[0-9.]+[wx])?", "", attributes.get("srcset") or "", flags=re.IGNORECASE)
                for candidate in srcset.split(","):
                    tokens = candidate.strip().split()
                    if tokens and not tokens[0].lower().startswith("data:"):
                        self.add_reference(tokens[0], scene_id, tag, "srcset")
        if tag == "video":
            self.add_reference(attributes.get("poster"), scene_id, tag, "poster")
            self.videos.append({"scene_id": scene_id, "attributes": attributes})
        if "data-shot-cues" in attributes:
            self.shots.append({"scene_id": scene_id, "cues": (attributes["data-shot-cues"] or "").split()})
        if any(attribute in attributes for attribute in MEDIA_TIMING_ATTRIBUTES):
            self.timed_elements.append({"scene_id": scene_id, "tag": tag, "attributes": attributes})
        if attributes.get("style"):
            self.add_css(attributes["style"], scene_id, tag)
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, scene_id))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][0] == "style":
            self.add_css(data, self.stack[-1][1], "style")


def scan_visual_source(body: str) -> dict:
    """Return media references, cue groups and video attributes, each with its scene ID."""
    parser = VisualSourceParser()
    parser.feed(body)
    parser.close()
    return {"media": parser.media, "shots": parser.shots, "videos": parser.videos,
            "timed_elements": parser.timed_elements, "studio_ids": parser.studio_ids}


def extract_media_references(body: str) -> list[dict]:
    """Return {path, scene_id, tag, attribute} records, including CSS and poster sources."""
    return scan_visual_source(body)["media"]


def validate_media_source(body_file: Path, scenes: list[dict], scan: dict, *, require_media: bool) -> None:
    segment_scenes = {
        segment["id"]: scene["id"]
        for scene in scenes for segment in (authored_segments(scene) or [])
    }
    for shot in scan["shots"]:
        if not shot["scene_id"] or not shot["cues"]:
            fail("data-shot-cues must contain narration segment IDs inside a data-scene section")
        for cue_id in shot["cues"]:
            if segment_scenes.get(cue_id) != shot["scene_id"]:
                fail(f"data-shot-cues references unknown or different-scene narration segment {cue_id!r}")
    for item in scan["timed_elements"]:
        if item["tag"] != "video":
            fail("data-media-in/out/start/rate are supported only on video elements")
        values = {}
        for name in MEDIA_TIMING_ATTRIBUTES:
            if name not in item["attributes"]:
                continue
            try:
                value = float(item["attributes"][name])
            except (ValueError, TypeError):
                fail(f"{name} must be a finite number")
            if not math.isfinite(value) or (value <= 0 if name == "data-media-rate" else value < 0):
                fail(f"{name} must be {'positive' if name == 'data-media-rate' else 'non-negative'} and finite")
            values[name] = value
        if "data-media-out" in values and values["data-media-out"] <= values.get("data-media-in", 0):
            fail("data-media-out must be greater than data-media-in")

    root = body_file.parent.resolve()
    checked: set[str] = set()
    for reference in scan["media"]:
        value = reference["path"]
        if value in checked:
            continue
        checked.add(value)
        try:
            parsed = urlsplit(value)
        except ValueError:
            fail(f"invalid media URL: {value}")
        remote = bool(parsed.scheme or parsed.netloc or value.startswith("//"))
        # CSS font files are dependencies, not visual evidence; preserve existing font workflows.
        font = reference["attribute"] == "url" and Path(parsed.path).suffix.lower() in {".woff", ".woff2", ".ttf", ".otf"}
        if remote:
            if require_media and not font:
                fail(f"visual media must be saved inside the project before rendering: {value}")
            if not font:
                print(f"Media source warning: remote visual resource {value}; download it into media/ before rendering.")
            continue
        path = (root / unquote(parsed.path)).resolve()
        if not path.is_relative_to(root):
            if require_media:
                fail(f"media reference escapes the project folder: {value}")
            print(f"Media source warning: resource is outside the project folder: {value}")
            continue
        if not path.is_file():
            if require_media:
                fail(f"missing local media resource: {value}")
            print(f"Media source warning: missing {value}; Web output slots must be filled before rendering.")
            continue
        if path.suffix.lower() == ".gif":
            print(f"Media source warning: {value} is a GIF; convert animated GIFs to MP4/WebM for deterministic frame rendering.")


def embedded_script_source(body: str) -> str:
    """Return inline script contents for deterministic-source checks."""
    return "\n".join(
        match.group(1)
        for match in re.finditer(r"<script\b[^>]*>([\s\S]*?)</script\s*>", body, re.IGNORECASE)
    )


def validate_visual_source(source: str, label: str = "embedded JavaScript") -> None:
    if not source.strip():
        return
    if "requestAnimationFrame" in source:
        fail(f"{label} must use renderAtTime() instead of an independent requestAnimationFrame loop")
    for url in re.findall(r"https?://[^'\"\s<]+", source):
        if "three" in url.lower() and not re.search(r"three@\d+\.\d+\.\d+", url):
            fail(f"Three.js CDN imports in {label} must pin an exact three@x.y.z version")


def validate_embedded_visual_contract(source: str) -> None:
    mentions_visual = re.search(r"\b(?:mount|renderAtTime)\b", source)
    if not mentions_visual:
        return
    exported = all(
        re.search(rf"export\s+(?:async\s+)?function\s+{name}\b", source)
        for name in ["mount", "renderAtTime"]
    )
    registered = bool(
        re.search(r"window\.(?:__videoVisual|videoVisual)\s*=", source)
        and re.search(r"\bmount\b", source)
        and re.search(r"\brenderAtTime\b", source)
    )
    if not exported and not registered:
        fail("scripted visuals in body.html must export mount() and renderAtTime()")


def has_embedded_visual(body: str) -> bool:
    scripts = embedded_script_source(body)
    return bool(re.search(r"\bmount\b", scripts) and re.search(r"\brenderAtTime\b", scripts))


def fail(message: str) -> None:
    raise SystemExit(f"source validation failed: {message}")


def short_label_units(value: str) -> float:
    """Measure compact chapter labels without penalizing Latin text like CJK text."""
    units = 0.0
    for char in value.strip():
        if char.isspace():
            units += 0.25
        elif char.isascii():
            units += 0.5
        else:
            units += 1.0
    return units


def validate_scenes(
    scenes_file: Path,
    *,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    require_bookends: bool = True,
) -> list[dict]:
    if not scenes_file.exists():
        fail("missing scenes.json; initialize a project and pass its folder with --source")

    try:
        scenes = json.loads(scenes_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"scenes.json is invalid JSON: {exc}")

    if not isinstance(scenes, list) or not scenes:
        fail("scenes.json must be a non-empty JSON array")

    seen: set[str] = set()
    seen_segments: set[str] = set()
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            fail(f"scene {index} must be an object")

        scene_id = scene.get("id")
        if not isinstance(scene_id, str) or not ID_RE.match(scene_id):
            fail(f"scene {index} has invalid id {scene_id!r}; use lowercase letters, digits, and hyphens")
        if scene_id in seen:
            fail(f"duplicate scene id: {scene_id}")
        seen.add(scene_id)

        narration = scene.get("narration")
        if isinstance(narration, dict):
            raw_segments = narration.get("segments")
            segments = authored_segments(scene)
            if not isinstance(raw_segments, list) or not raw_segments or segments is None:
                fail(f"scene {scene_id} narration must contain a non-empty segments array")
            if len(segments) != len(raw_segments):
                fail(f"scene {scene_id} narration segments must be objects")
            for segment_index, segment in enumerate(segments, 1):
                segment_id = segment["id"]
                if not SEGMENT_ID_RE.fullmatch(segment_id):
                    fail(
                        f"scene {scene_id} narration segment {segment_index} has invalid id "
                        f"{segment_id!r}; use lowercase letters, digits, and hyphens"
                    )
                if segment_id in seen_segments:
                    fail(f"duplicate narration segment id: {segment_id}")
                seen_segments.add(segment_id)
                if not segment["text"]:
                    fail(f"scene {scene_id} narration segment {segment_id} must include text")
                if caption_units(segment["text"]) > 36:
                    print(
                        f"Caption readability warning: narration segment {segment_id} may exceed "
                        "two lines; consider a semantic split."
                    )
        else:
            fail(
                f"scene {scene_id} narration must use an object with segments; "
                "simple narration strings are accepted only by the Studio import/save API"
            )

        category = scene.get("category")
        if not isinstance(category, str) or not category.strip():
            fail(f"scene {scene_id} must include a short category for the generated chapter rail")
        category_limit = (
            PORTRAIT_CATEGORY_UNIT_LIMIT
            if normalize_aspect_ratio(aspect_ratio) == "9:16"
            else CATEGORY_UNIT_LIMIT
        )
        if short_label_units(category) > category_limit:
            if category_limit == PORTRAIT_CATEGORY_UNIT_LIMIT:
                fail(
                    f"scene {scene_id} category is too long for a portrait chapter rail; "
                    "use 2-3 CJK characters or one short English word (8 Latin characters maximum)"
                )
            fail(
                f"scene {scene_id} category is too long; keep it within 12 CJK characters "
                "or about 24 Latin characters"
            )

    if require_bookends:
        if scenes[0]["id"] != "intro":
            fail(
                "the first scene must use id 'intro' and open with the subject, "
                "a concrete fact, or the central editorial question"
            )
        if scenes[-1]["id"] != "outro":
            fail(
                "the last scene must use id 'outro' and end with a concise synthesis "
                "or forward-looking implication"
            )

    style_hits = []
    for scene in scenes:
        narration_folded = narration_text(scene).casefold()
        markers = [
            marker for marker in ASSISTANT_NARRATION_MARKERS
            if marker.casefold() in narration_folded
        ]
        if markers:
            style_hits.append(f"{scene['id']} ({', '.join(markers)})")
    if style_hits:
        print(
            "Narration style warning: assistant/presenter phrasing detected in "
            + "; ".join(style_hits)
            + ". Knowledge-show narration should state the claim directly unless a "
            "presenter-led tone was requested."
        )

    return scenes


def validate_body(body_file: Path, scenes: list[dict], *, require_media: bool = False) -> None:
    if not body_file.exists():
        fail("missing body.html; source folders must contain scenes.json and body.html")
    body = body_file.read_text(encoding="utf-8")
    body_lower = body.lower()
    stripped_body = body_lower.lstrip("\ufeff \t\r\n")
    required_document_markers = ["<html", "<head", "</head>", "<body", "</body>", "</html>"]
    if not stripped_body.startswith("<!doctype html>") or any(
        marker not in body_lower for marker in required_document_markers
    ):
        fail(
            "body.html must be a complete HTML document from <!doctype html> through </html>; "
            "do not return a <style>/<section> fragment or omit closing tags"
        )
    for marker, message in FORBIDDEN_BODY_MARKERS.items():
        if marker in body_lower:
            fail(message)
    if "<style" not in body_lower:
        fail("body.html must include its project styling in a <style> element")
    scan = scan_visual_source(body)
    validate_media_source(body_file, scenes, scan, require_media=require_media)

    script_tags = list(re.finditer(r"<script\b([^>]*)>([\s\S]*?)</script\s*>", body, re.IGNORECASE))
    if len(script_tags) > 1:
        fail("body.html may include at most one deterministic module script")
    if script_tags:
        attributes, scripts = script_tags[0].groups()
        if not re.search(r"\btype\s*=\s*(['\"])module\1", attributes, re.IGNORECASE):
            fail("the optional body.html script must use type=\"module\"")
        if re.search(r"\bsrc\s*=", attributes, re.IGNORECASE):
            fail("keep the optional module inline in body.html; import pinned dependencies from inside it")
        validate_visual_source(scripts)
        validate_embedded_visual_contract(scripts)
        if not has_embedded_visual(body):
            fail("the optional body.html module must export mount() and renderAtTime()")

    missing = [scene["id"] for scene in scenes if f'data-scene="{scene["id"]}"' not in body and f"data-scene='{scene['id']}'" not in body]
    if missing:
        fail(f"body.html is missing data-scene sections for: {', '.join(missing)}")

    studio_id_values = scan["studio_ids"]
    duplicate_studio_ids = sorted({
        value for value in studio_id_values
        if value and studio_id_values.count(value) > 1
    })
    if duplicate_studio_ids:
        fail(f"body.html has duplicate data-studio-id values: {', '.join(duplicate_studio_ids)}")

    motion_values = [
        value.strip()
        for _, value in re.findall(r"\bdata-motion\s*=\s*(['\"])(.*?)\1", body, re.IGNORECASE)
    ]
    unknown_motion = sorted({value for value in motion_values if value not in MOTION_PRESETS})
    if unknown_motion:
        fail(f"body.html uses unknown data-motion presets: {', '.join(unknown_motion)}")
    if len(motion_values) > len(scenes) * 2:
        print(
            f"Source quality warning: body.html contains {len(motion_values)} motion presets "
            f"across {len(scenes)} scenes; prefer at most two grouped motion objects per scene."
        )

    card_markers = ["comparison-card", "metric-card", "diagram-node", "step-chip", "formula-token", "concept-node"]
    component_count = sum(body_lower.count(marker) for marker in card_markers)
    if component_count > len(scenes) * 8:
        print(
            f"Source quality warning: body.html contains {component_count} card-like components; "
            "prefer one dominant composition per scene."
        )


def validate_captions(captions_file: Path) -> None:
    if not captions_file.exists():
        return
    try:
        captions = json.loads(captions_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"captions.json is invalid JSON: {exc}")

    cues = captions.get("cues") if isinstance(captions, dict) else captions
    if not isinstance(cues, list):
        fail("captions.json must be an object with a cues array or a cues array")
    for index, cue in enumerate(cues, 1):
        if not isinstance(cue, dict):
            fail(f"caption cue {index} must be an object")
        if "text" in cue and not isinstance(cue["text"], str):
            fail(f"caption cue {index} text must be a string")
        for name in ["start", "end"]:
            if name in cue and not isinstance(cue[name], (int, float)):
                fail(f"caption cue {index} {name} must be a number")


def validate_shell() -> None:
    shell = ensure_shell()
    index_source = (shell / "index.html").read_text(encoding="utf-8")
    runtime = SHELL / "runtime.js"
    if "runtime.js" not in index_source:
        fail("shell index.html must load runtime.js")
    if "shell.css" not in index_source:
        fail("shell index.html must load shell.css")
    source = runtime.read_text(encoding="utf-8")
    required = [
        "compositionReady",
        "getCompositionDuration",
        "renderAtTime",
        "startCompositionPlayback",
    ]
    for name in required:
        if name not in source:
            fail(f"shell runtime is missing {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    parser.add_argument("--scope", choices=["project", "narration"], default="project")
    parser.add_argument("--require-media", action="store_true", help="require local visual media to exist before rendering")
    args = parser.parse_args()

    paths = project_paths(Path(args.source) if args.source else None)
    scenes_file = paths.scenes
    body_file = paths.body
    captions_file = paths.captions
    manifest = read_json(paths.manifest)
    aspect_ratio = normalize_aspect_ratio(
        manifest.get("aspectRatio") if isinstance(manifest, dict) else DEFAULT_ASPECT_RATIO
    )
    scenes = validate_scenes(scenes_file, aspect_ratio=aspect_ratio)
    chars = narration_chars(scenes)
    if args.scope == "narration":
        print(f"Narration validation passed: {len(scenes)} scenes, {chars} narration characters")
        return
    validate_body(body_file, scenes, require_media=args.require_media)
    validate_captions(captions_file)
    validate_shell()
    print(f"Source validation passed: {len(scenes)} scenes, {chars} narration characters")


if __name__ == "__main__":
    main()
