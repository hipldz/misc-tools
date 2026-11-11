"""Check an agent's evidence/shot plan without changing the two-file source format."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from .factory import normalize_aspect_ratio, project_paths, read_json
    from .validate_sources import extract_media_references, validate_body, validate_scenes
except ImportError:
    from factory import normalize_aspect_ratio, project_paths, read_json
    from validate_sources import extract_media_references, validate_body, validate_scenes


REAL_ASSETS = {"capture", "demo", "figure"}
ASSET_KINDS = REAL_ASSETS | {"reconstruction", "generated"}


def fail(message: str) -> None:
    raise SystemExit(f"Production validation failed: {message}")


def required_text(item: dict, key: str, label: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{label} needs a non-empty {key}")
    return value.strip()


def validate_production(source: Path | None, *, required: bool = False) -> dict | None:
    paths = project_paths(source)
    plan_file = paths.root / "production.json"
    if not plan_file.exists():
        if required:
            fail("missing production.json; follow docs/agent-production.md for agent production")
        return None
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read production.json: {exc}")
    if not isinstance(plan, dict) or type(plan.get("version")) is not int or plan["version"] != 1:
        fail("production.json must be an object with version: 1")
    if plan.get("treatment") not in {"source-led", "explanatory"}:
        fail("treatment must be source-led or explanatory")
    manifest = read_json(paths.manifest)
    aspect_ratio = normalize_aspect_ratio(manifest.get("aspectRatio") if isinstance(manifest, dict) else None)
    scenes = validate_scenes(paths.scenes, aspect_ratio=aspect_ratio)
    validate_body(paths.body, scenes, require_media=True)
    body = paths.body.read_text(encoding="utf-8")
    scene_cues = {scene["id"]: {cue["id"] for cue in scene["narration"]["segments"]} for scene in scenes}
    references: dict[str | None, set[str]] = {}
    for ref in extract_media_references(body):
        url = urlsplit(ref["path"])
        if not url.scheme and not url.netloc:
            references.setdefault(ref["scene_id"], set()).add(
                str((paths.root / unquote(url.path)).resolve())
            )

    raw_assets = plan.get("assets")
    if not isinstance(raw_assets, list):
        fail("assets must be an array; use [] for self-contained explanatory diagrams")
    assets: dict[str, dict] = {}
    for index, asset in enumerate(raw_assets, 1):
        label = f"asset {index}"
        if not isinstance(asset, dict):
            fail(f"{label} must be an object")
        asset_id = required_text(asset, "id", label)
        if asset_id in assets:
            fail(f"duplicate asset id: {asset_id}")
        relative = required_text(asset, "path", asset_id)
        raw_path = Path(relative)
        target = (paths.root / raw_path).resolve()
        if raw_path.is_absolute() or not raw_path.parts or raw_path.parts[0] != "media":
            fail(f"{asset_id}: path must be project-relative media/...")
        if not target.is_relative_to(paths.media.resolve()) or not target.is_file():
            fail(f"{asset_id}: media file is missing or outside this project's media/")
        if asset.get("kind") not in ASSET_KINDS:
            fail(f"{asset_id}: kind must be one of {', '.join(sorted(ASSET_KINDS))}")
        required_text(asset, "source", asset_id)
        required_text(asset, "reuse", asset_id)
        if "date" in asset and not isinstance(asset["date"], str):
            fail(f"{asset_id}: date must be a string when supplied")
        assets[asset_id] = {**asset, "resolved": str(target)}

    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        fail("shots must be a non-empty array")
    covered = {scene: set() for scene in scene_cues}
    evidenced = {scene: set() for scene in scene_cues}
    for index, shot in enumerate(shots, 1):
        label = f"shot {index}"
        if not isinstance(shot, dict):
            fail(f"{label} must be an object")
        scene = required_text(shot, "scene", label)
        if scene not in scene_cues:
            fail(f"{label}: unknown scene {scene}")
        required_text(shot, "shows", label)
        cues, selected = shot.get("cues"), shot.get("assets")
        if not isinstance(cues, list) or not cues or any(not isinstance(c, str) for c in cues):
            fail(f"{label}: cues must list this scene's narration segment ids")
        if set(cues) - scene_cues[scene]:
            fail(f"{label}: unknown or wrong-scene cues: {set(cues) - scene_cues[scene]}")
        if not isinstance(selected, list) or any(not isinstance(a, str) for a in selected):
            fail(f"{label}: assets must be an array of asset ids (or [] for a diagram)")
        for asset_id in selected:
            if asset_id not in assets:
                fail(f"{label}: unknown asset {asset_id}")
            visible_refs = references.get(scene, set()) | references.get(None, set())
            if assets[asset_id]["resolved"] not in visible_refs:
                fail(f"{label}: {asset_id} is not referenced by scene {scene} in body.html")
        covered[scene].update(cues)
        if any(assets[a]["kind"] in REAL_ASSETS for a in selected):
            evidenced[scene].update(cues)
    for scene, cues in scene_cues.items():
        missing = cues - covered[scene]
        if missing:
            fail(f"{scene}: narration has no planned visual: {', '.join(sorted(missing))}")
        if plan["treatment"] == "source-led" and scene not in {"intro", "outro"}:
            if not evidenced[scene]:
                fail(f"{scene}: source-led content needs a capture, actual demo, or original figure")

    print(
        f"Production validation passed: {len(assets)} assets, {len(shots)} shots, "
        f"{sum(map(len, covered.values()))} narration segments covered. "
        "Review truth, legibility, and actual on-screen timing separately."
    )
    return plan
