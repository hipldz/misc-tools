#!/usr/bin/env python3
"""Main CLI for the HTML TTS video factory."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from pipeline.factory import (
    ASPECT_RATIOS,
    DEFAULT_ASPECT_RATIO,
    LOCAL_WORK,
    PLAYWRIGHT_BROWSERS,
    PROJECT_MANIFEST_FILE,
    ROOT,
    SHELL,
    STARTER_SOURCE,
    atomic_write_json,
    default_manifest,
    ensure_starter_manifest,
    iter_project_roots,
    load_source,
    normalize_aspect_ratio,
    project_paths,
    read_json,
)
from pipeline.narration import narration_language_sample
from pipeline.prompt_composer import compose_prompt, detect_language


PYTHON = sys.executable


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(command, cwd=ROOT, check=True, env=env)
    except KeyboardInterrupt:
        print("\nInterrupted. Shutting down…")
        return
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)


def copy_source_template(args: argparse.Namespace) -> None:
    target = Path(args.target).expanduser().resolve()
    if target == STARTER_SOURCE.resolve():
        raise SystemExit("starter is read-only; choose a new project folder")
    if target.exists() and any(target.iterdir()) and not args.force:
        raise SystemExit(f"Refusing to overwrite non-empty target: {target}; use --force")
    existing = read_json(target / PROJECT_MANIFEST_FILE)
    requested_aspect_ratio = normalize_aspect_ratio(args.aspect_ratio)
    if isinstance(existing, dict) and existing.get("aspectRatio"):
        if normalize_aspect_ratio(existing.get("aspectRatio")) != requested_aspect_ratio:
            raise SystemExit("Project aspect ratio is fixed after creation; choose a new target folder")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(STARTER_SOURCE / "scenes.json", target / "scenes.json")
    shutil.copy2(STARTER_SOURCE / "body.html", target / "body.html")
    manifest = default_manifest(target, active=False)
    if isinstance(existing, dict):
        manifest = {**manifest, **existing}
    manifest.update({
        "aspectRatio": requested_aspect_ratio,
        "system": False,
        "readOnly": False,
    })
    atomic_write_json(target / PROJECT_MANIFEST_FILE, manifest)
    print(f"Created editable source folder: {target}")
    print(f"Aspect ratio: {requested_aspect_ratio}")
    print("Edit scenes.json and body.html, then run:")
    print(f"python main.py tts --source {target}")


def validate_source(source: str | None, *, scope: str = "project", require_media: bool = False) -> None:
    command = [PYTHON, "pipeline/validate_sources.py"]
    if source:
        command.extend(["--source", source])
    if scope != "project":
        command.extend(["--scope", scope])
    if require_media:
        command.append("--require-media")
    run(command)


def validate_agent_production(source: str | None, *, required: bool = False) -> None:
    from pipeline.production import validate_production

    validate_production(Path(source) if source else None, required=required)


def install(args: argparse.Namespace) -> None:
    pip_command = [PYTHON, "-m", "pip", "install", "-r", "requirements.txt"]
    if args.pip_index_url:
        pip_command.extend(["--index-url", args.pip_index_url])
        print(f"Using one-time Python package index: {args.pip_index_url}")
    run(pip_command)

    from pipeline.toolchain import configure_playwright_environment

    playwright_env = configure_playwright_environment(os.environ.copy())
    if args.playwright_download_host:
        playwright_env["PLAYWRIGHT_DOWNLOAD_HOST"] = args.playwright_download_host
        print(f"Using one-time Playwright download host: {args.playwright_download_host}")
    print("Installing Playwright Chromium Headless Shell (no system or headed browser required).")
    run([PYTHON, "-m", "playwright", "install", "--only-shell", "chromium"], env=playwright_env)


def tts(args: argparse.Namespace) -> None:
    validate_source(args.source, scope="narration")
    validate_agent_production(args.source)
    voice = args.voice
    if not voice:
        scenes = json.loads(project_paths(Path(args.source) if args.source else None).scenes.read_text(encoding="utf-8"))
        language = detect_language(narration_language_sample(scenes))
        voice = {
            "zh-CN": "zh-CN-XiaoxiaoNeural",
        }.get(language, "en-US-JennyNeural")
    command = [
        PYTHON,
        "pipeline/build_tts.py",
        "--provider",
        args.provider,
        "--voice",
        voice,
        "--rate",
        args.rate,
        "--pitch",
        args.pitch,
        "--gap",
        str(args.gap),
    ]
    if args.source:
        command.extend(["--source", args.source])
    if args.force:
        command.append("--force")
    run(command)


def offline(args: argparse.Namespace) -> None:
    validate_source(args.source, scope="narration")
    command = [PYTHON, "pipeline/build_offline_preview.py"]
    if args.source:
        command.extend(["--source", args.source])
    run(command)


def captions(args: argparse.Namespace) -> None:
    if args.source:
        load_source(Path(args.source))
    run([PYTHON, "studio/server.py"])


def studio(args: argparse.Namespace) -> None:
    from studio.web_paths import normalize_base_path

    try:
        base_path = normalize_base_path(args.base_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.source:
        load_source(Path(args.source))
    from pipeline.tts_provider import azure_configuration_status

    azure = azure_configuration_status()
    print(
        "Azure Speech: configured"
        if azure["configured"]
        else f"Azure Speech: unavailable - {azure['message']}"
    )
    run([
        PYTHON, "studio/server.py", "--host", args.host,
        "--port", str(args.port), "--base-path", base_path,
    ])


def render(args: argparse.Namespace) -> None:
    validate_source(args.source, require_media=True)
    validate_agent_production(args.source)
    if (args.width is None) != (args.height is None):
        raise SystemExit("--width and --height must be supplied together")
    if args.width is not None and (args.width <= 0 or args.height <= 0):
        raise SystemExit("--width and --height must be positive")
    command = [
        PYTHON,
        "pipeline/render_video.py",
        "--size",
        args.size,
        "--output",
        args.output,
        "--capture",
        args.capture,
        "--fps",
        str(args.fps),
        "--crf",
        str(args.crf),
        "--preset",
        args.preset,
        "--frame-format",
        args.frame_format,
        "--jpeg-quality",
        str(args.jpeg_quality),
        "--transition",
        str(args.transition),
    ]
    if args.source:
        command.extend(["--source", args.source])
    if args.width is not None:
        command.extend(["--width", str(args.width), "--height", str(args.height)])
    run(command)


def voices(args: argparse.Namespace) -> None:
    command = [PYTHON, "pipeline/voice_preview.py", "list", "--provider", args.provider]
    if args.json:
        command.append("--json")
    run(command)


def voice_preview(args: argparse.Namespace) -> None:
    command = [
        PYTHON,
        "pipeline/voice_preview.py",
        "preview",
        "--provider",
        args.provider,
        "--text",
        args.text,
        "--rate",
        args.rate,
        "--pitch",
        args.pitch,
    ]
    for voice in args.voice or []:
        command.extend(["--voice", voice])
    run(command)


def prompt(args: argparse.Namespace) -> None:
    result = compose_prompt({
        "topic": args.topic,
        "audience": args.audience,
        "tone": args.tone,
        "sceneCount": args.scene_count,
        "notes": args.notes,
        "language": args.language,
        "aspectRatio": args.aspect_ratio,
    })
    print(result["prompt"], end="")


def check(args: argparse.Namespace) -> None:
    validate_source(args.source or str(STARTER_SOURCE))
    validate_agent_production(args.source or str(STARTER_SOURCE), required=args.production)
    run(["node", "--check", str(SHELL / "runtime.js")])
    run(["node", "--check", "studio/web/captions/captions.js"])
    run(["node", "--check", "studio/web/source/source.js"])
    run(["node", "--check", "studio/web/studio/studio.js"])
    run(["node", "--check", "studio/web/voices/voices.js"])
    run(["node", "--check", "studio/web/shared/urls.js"])
    run(["node", "--check", "studio/web/shared/app-ui.js"])
    python_files = [
        ROOT / "main.py",
        *sorted((ROOT / "pipeline").glob("*.py")),
        *sorted((ROOT / "studio").glob("*.py")),
    ]
    run([PYTHON, "-m", "py_compile", *map(str, python_files)])
    validate_project_manifests()


def validate_project_manifests() -> None:
    ensure_starter_manifest()
    ids: set[str] = set()
    active: list[str] = []
    for root in iter_project_roots():
        manifest = read_json(root / PROJECT_MANIFEST_FILE)
        if not isinstance(manifest, dict):
            continue  # Agent-authored projects receive a manifest when Studio first discovers them.
        if manifest.get("version") != 5 or not isinstance(manifest.get("active"), bool):
            raise SystemExit(f"Project manifest must use version 5 and a boolean active field: {root}")
        try:
            aspect_ratio = normalize_aspect_ratio(manifest.get("aspectRatio"))
        except ValueError as exc:
            raise SystemExit(f"Invalid project aspect ratio in {root}: {exc}") from exc
        project_id = str(manifest.get("id") or "").strip().lower()
        if not project_id:
            raise SystemExit(f"Project manifest is missing id: {root}")
        if project_id in ids:
            raise SystemExit(f"Duplicate project manifest id: {project_id}")
        ids.add(project_id)
        if manifest.get("active") is True:
            active.append(project_id)
        if root.resolve() == STARTER_SOURCE.resolve():
            if project_id != "starter" or manifest.get("system") is not True or manifest.get("readOnly") is not True:
                raise SystemExit("Starter manifest must use id=starter, system=true, and readOnly=true")
            if aspect_ratio != DEFAULT_ASPECT_RATIO:
                raise SystemExit("Starter manifest must use aspectRatio=16:9")
    if len(active) != 1:
        raise SystemExit(f"Expected exactly one active project manifest; found {len(active)}")
    print(f"Project manifest validation passed: active={active[0]}")


def doctor(args: argparse.Namespace) -> None:
    del args
    from pipeline.toolchain import configure_playwright_environment, ffmpeg_executable
    from pipeline.tts_provider import azure_configuration_status

    configure_playwright_environment()
    ffmpeg = Path(ffmpeg_executable())
    print(f"FFmpeg: {ffmpeg}")
    print(f"Playwright browser cache: {PLAYWRIGHT_BROWSERS.resolve()}")
    azure = azure_configuration_status()
    print(
        "Azure Speech: configured"
        if azure["configured"]
        else f"Azure Speech: unavailable - {azure['message']}"
    )
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        shells = sorted(
            [
                *PLAYWRIGHT_BROWSERS.glob("chromium_headless_shell-*/**/chrome-headless-shell"),
                *PLAYWRIGHT_BROWSERS.glob("chromium_headless_shell-*/**/chrome-headless-shell.exe"),
            ]
        )
        if not shells:
            raise RuntimeError("managed chrome-headless-shell executable was not found")
        executable = shells[-1].resolve()
    except Exception as exc:  # noqa: BLE001 - doctor must report environment failures clearly.
        raise SystemExit(f"Playwright Chromium Headless Shell check failed: {exc}\nRun: python main.py install") from exc
    print(f"Chromium Headless Shell: {executable}")
    print("Toolchain doctor passed")


def smoke(args: argparse.Namespace) -> None:
    from pipeline.toolchain import configure_playwright_environment

    configure_playwright_environment()
    process = subprocess.Popen(
        [PYTHON, "studio/server.py", "--host", "127.0.0.1", "--port", str(args.port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    origin = f"http://127.0.0.1:{args.port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline = time.time() + 12
        state = None
        while time.time() < deadline:
            if process.poll() is not None:
                raise SystemExit(f"Studio smoke server exited early; port {args.port} may already be in use")
            try:
                with opener.open(f"{origin}/api/studio/state", timeout=1) as response:
                    state = json.loads(response.read().decode("utf-8"))
                    break
            except OSError:
                time.sleep(0.2)
        if not isinstance(state, dict):
            raise SystemExit("Studio smoke server did not become ready")

        from playwright.sync_api import sync_playwright

        shell = str(state["urls"]["shell"])
        separator = "&" if "?" in shell else "?"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(f"{origin}/studio", wait_until="domcontentloaded")
            page.wait_for_function(
                "expected => document.querySelector('#workspaceProjectId')?.textContent.trim() === expected",
                arg=str(state["activeProject"]["id"]),
            )
            page.wait_for_function(
                """expected => {
                  const voice = document.querySelector('#ttsVoiceInput');
                  const provider = document.querySelector('#ttsProviderInput');
                  const output = document.querySelector('#renderOutputInput');
                  return provider?.options.length === 2
                    && provider.value === expected.provider
                    && voice?.options.length > 0
                    && voice.value === expected.voice
                    && output?.value === expected.output;
                }""",
                arg={
                    "provider": str(state["settings"]["tts"]["provider"]),
                    "voice": str(state["settings"]["tts"]["voice"]),
                    "output": str(state["suggestedOutputName"]),
                },
            )
            page.goto(
                f"{origin}/source?project={state['activeProject']['id']}",
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "expected => document.querySelector('#projectSelect')?.value === expected",
                arg=str(state["activeProject"]["id"]),
            )
            page.wait_for_function(
                "() => document.querySelector('#previewFrame')?.contentWindow?.compositionReady === true"
            )
            page.wait_for_function(
                """() => {
                  const frame = document.querySelector('#previewFrame')?.contentWindow;
                  const scenes = frame?.getCompositionScenes?.() || [];
                  const playback = frame?.getPlaybackState?.();
                  const active = frame?.document.querySelector('[data-scene].is-active');
                  const steps = active ? [...active.querySelectorAll('[data-step]')] : [];
                  if (!frame?.document.documentElement.classList.contains('editor-mode')) return false;
                  if (!scenes[0] || !playback || active?.dataset.scene !== scenes[0].id) return false;
                  const sceneEnd = scenes[0].start + scenes[0].duration;
                  return playback.current >= sceneEnd - 0.001
                    && steps.every(step => step.classList.contains('active'));
                }"""
            )
            source_before_click = page.locator("#bodyEditor").input_value()
            text_object = page.frame_locator("#previewFrame").locator(
                '[data-scene].is-active [data-studio-kind="text"]'
            ).first
            selection_safe = True
            if text_object.count():
                style_before_click = text_object.get_attribute("style")
                text_object.click(position={"x": 4, "y": 4}, force=True)
                selection_safe = (
                    text_object.get_attribute("style") == style_before_click
                    and page.locator("#bodyEditor").input_value() == source_before_click
                )
            page.goto(f"{origin}{shell}{separator}render=1", wait_until="networkidle")
            page.wait_for_function("window.compositionReady === true || Boolean(window.compositionError)")
            error = page.evaluate("() => window.compositionError || ''")
            chapter_ok = page.evaluate(
                """() => {
                  const scenes = window.getCompositionScenes?.() || [];
                  const duration = window.getCompositionDuration?.() || 0;
                  const rail = document.querySelector('.chapter-rail')?.getBoundingClientRect();
                  const segments = [...document.querySelectorAll('.chapter-segment')];
                  const labels = [...document.querySelectorAll('.chapter-label-item')];
                  const endMarker = document.querySelector('.chapter-end-marker')?.getBoundingClientRect();
                  if (
                    !rail
                    || !duration
                    || !endMarker
                    || segments.length !== scenes.length
                    || labels.length !== scenes.length
                  ) {
                    return false;
                  }
                  const labelRects = labels.map(item => item.getBoundingClientRect());
                  const labelContentRects = labels.map(
                    item => item.querySelector('.chapter-label').getBoundingClientRect()
                  );
                  const overlaps = labelRects.some(
                    (rect, index) => index > 0 && rect.left < labelRects[index - 1].right - 0.5
                  );
                  const boundariesMatch = segments.every((segment, index) => {
                    const rect = segment.getBoundingClientRect();
                    const expected = index === 0
                      ? 0
                      : (
                        scenes[index - 1].start
                        + scenes[index - 1].duration
                        + scenes[index].start
                      ) / 2 / duration;
                    return Math.abs((rect.left - rail.left) / rail.width - expected) <= 0.002;
                  });
                  const labelsCentered = labels.every((item, index) => {
                    const rect = labelRects[index];
                    const left = rail.left + Number(item.dataset.leftRatio) * rail.width;
                    const right = rail.left + Number(item.dataset.rightRatio) * rail.width;
                    return Math.abs((rect.left + rect.right - left - right) / 2) <= 0.5;
                  });
                  return !overlaps
                    && boundariesMatch
                    && labelsCentered
                    && Math.abs((endMarker.left + endMarker.right) / 2 - rail.right) <= 0.5
                    && Math.max(...labelContentRects.map(rect => rect.bottom))
                      - Math.min(...labelContentRects.map(rect => rect.bottom)) <= 0.75
                    && segments.every(segment => getComputedStyle(segment).borderLeftWidth === '0px')
                    && !document.querySelector('.chapter-label-leader')
                    && !document.querySelector('.chapter-index')
                    && labels.every(item => getComputedStyle(item.querySelector('.chapter-label')).webkitLineClamp === '2');
                }"""
            )
            motion_ok = page.evaluate(
                """async () => {
                  const scene = window.getCompositionScenes?.()[0];
                  const object = document.querySelector('[data-studio-id]');
                  if (!scene || !object) return false;
                  object.dataset.motion = 'rise';
                  await window.renderAtTime(scene.start);
                  const first = `${object.style.opacity}|${object.style.transform}`;
                  await window.renderAtTime(scene.start + scene.duration * 0.5);
                  const second = `${object.style.opacity}|${object.style.transform}`;
                  const sourceStyle = window.getSourceStyleForNode?.(object) || '';
                  return first !== second && !sourceStyle.includes('translateY(');
                }"""
            )
            browser.close()
        if error:
            raise SystemExit(f"Studio composition smoke failed: {error}")
        if not motion_ok:
            raise SystemExit("Studio composition smoke failed: deterministic motion preset did not advance cleanly")
        if not chapter_ok:
            raise SystemExit("Studio composition smoke failed: adaptive chapter rail geometry is invalid")
        if not selection_safe:
            raise SystemExit("Studio source smoke failed: selecting text mutated its source style")
        print(f"Studio smoke passed: {state['activeProject']['id']}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", help="Folder containing scenes.json and body.html.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run HTML video factory tasks.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--target", default=str(LOCAL_WORK / "new-video"))
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument(
        "--aspect-ratio",
        choices=ASPECT_RATIOS,
        default=DEFAULT_ASPECT_RATIO,
        help="Immutable project canvas orientation (default: 16:9).",
    )
    init_parser.set_defaults(func=copy_source_template)

    install_parser = subparsers.add_parser(
        "install",
        help="Install Python dependencies and Playwright Chromium Headless Shell.",
        description=(
            "Install requirements.txt (including imageio-ffmpeg) and only Playwright's Chromium "
            "Headless Shell. No headed Chromium, system Chrome, or system Edge is installed or used."
        ),
    )
    install_parser.add_argument(
        "--pip-index-url",
        help="One-time Python package index URL; does not modify pip configuration.",
    )
    install_parser.add_argument(
        "--playwright-download-host",
        help="One-time host for the Playwright Chromium Headless Shell download; does not persist in the environment.",
    )
    install_parser.set_defaults(func=install)

    offline_parser = subparsers.add_parser("offline")
    add_source_args(offline_parser)
    offline_parser.set_defaults(func=offline)

    captions_parser = subparsers.add_parser("captions")
    add_source_args(captions_parser)
    captions_parser.set_defaults(func=captions)

    studio_parser = subparsers.add_parser("studio")
    add_source_args(studio_parser)
    studio_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface or hostname to bind (default: 127.0.0.1).",
    )
    studio_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        choices=range(1, 65536),
        metavar="PORT",
        help="TCP port to bind (default: 8765).",
    )
    studio_parser.set_defaults(func=studio)
    studio_parser.add_argument(
        "--base-path", default="", help="Public URL prefix, e.g. /xxx (default: domain root).",
    )

    check_parser = subparsers.add_parser("check")
    add_source_args(check_parser)
    check_parser.add_argument(
        "--production", action="store_true",
        help="Require and validate the agent's production.json, local assets, and shot/cue coverage.",
    )
    check_parser.set_defaults(func=check)

    doctor_parser = subparsers.add_parser("doctor", help="Verify managed FFmpeg and Chromium Headless Shell.")
    doctor_parser.set_defaults(func=doctor)

    smoke_parser = subparsers.add_parser("smoke", help="Load the active Studio composition in managed headless Chromium.")
    smoke_parser.add_argument("--port", type=int, default=8876, choices=range(1, 65536), metavar="PORT")
    smoke_parser.set_defaults(func=smoke)

    render_parser = subparsers.add_parser("render")
    add_source_args(render_parser)
    render_parser.add_argument("--size", default="720p", choices=["480p", "720p", "1080p", "2k", "1440p", "4k", "2160p"])
    render_parser.add_argument("--width", type=int)
    render_parser.add_argument("--height", type=int)
    render_parser.add_argument("--output", default="tts-video.mp4")
    render_parser.add_argument("--capture", default="auto", choices=["auto", "video", "frames"])
    render_parser.add_argument("--fps", type=int, default=15)
    render_parser.add_argument("--crf", type=int, default=14)
    render_parser.add_argument("--preset", default="slow")
    render_parser.add_argument("--frame-format", default="jpeg", choices=["jpeg", "png"])
    render_parser.add_argument("--jpeg-quality", type=int, default=96)
    render_parser.add_argument(
        "--transition",
        type=float,
        default=0.4,
        help="Dip-to-background duration in seconds, from 0 (off) to 2.",
    )
    render_parser.set_defaults(func=render)

    voices_parser = subparsers.add_parser("voices")
    voices_parser.add_argument("--provider", default="edge", choices=["edge", "azure"])
    voices_parser.add_argument("--json", action="store_true")
    voices_parser.set_defaults(func=voices)

    voice_preview_parser = subparsers.add_parser("voice-preview")
    voice_preview_parser.add_argument("--provider", default="edge", choices=["edge", "azure"])
    voice_preview_parser.add_argument("--voice", action="append")
    voice_preview_parser.add_argument(
        "--text",
        default="This is an English voice preview for comparing voices, rate, and overall delivery.",
    )
    voice_preview_parser.add_argument("--rate", default="+12%")
    voice_preview_parser.add_argument("--pitch", default="+0Hz")
    voice_preview_parser.set_defaults(func=voice_preview)

    prompt_parser = subparsers.add_parser("prompt", help="Compose the Web AI two-file slide-video source prompt.")
    prompt_parser.add_argument("--topic", required=True)
    prompt_parser.add_argument("--audience", default="")
    prompt_parser.add_argument("--tone", default="Clear and concise")
    prompt_parser.add_argument(
        "--scene-count",
        default="Choose based on the topic and content complexity",
        help="A number or a free-form structure instruction.",
    )
    prompt_parser.add_argument("--notes", default="")
    prompt_parser.add_argument("--language", choices=["auto", "zh-CN", "en-US"], default="auto")
    prompt_parser.add_argument("--aspect-ratio", choices=ASPECT_RATIOS, default=DEFAULT_ASPECT_RATIO)
    prompt_parser.set_defaults(func=prompt)

    tts_parser = subparsers.add_parser("tts")
    add_source_args(tts_parser)
    tts_parser.add_argument("--provider", default="edge", choices=["edge", "azure"])
    tts_parser.add_argument("--voice", default=None, help="Defaults from the detected narration language.")
    tts_parser.add_argument("--rate", default="+12%")
    tts_parser.add_argument("--pitch", default="+0Hz")
    tts_parser.add_argument("--gap", type=float, default=0.28)
    tts_parser.add_argument("--force", action="store_true")
    tts_parser.set_defaults(func=tts)

    from pipeline.media_assets import add_parser as add_media_parser

    add_media_parser(subparsers)

    return parser


def main() -> None:
    try:
        args = build_parser().parse_args()
        args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled.")


if __name__ == "__main__":
    main()
