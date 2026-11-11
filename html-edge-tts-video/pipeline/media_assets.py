"""Bounded, project-local media acquisition and short-clip preparation for agents."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from .factory import PLAYWRIGHT_PROFILES, PLAYWRIGHT_SCREENSHOTS, PLAYWRIGHT_TMP, STARTER_SOURCE, project_paths


EXTENSIONS = {"png": {".png"}, "jpeg": {".jpg", ".jpeg"}, "gif": {".gif"},
              "webp": {".webp"}, "avif": {".avif"}, "mp4": {".mp4", ".m4v", ".mov"},
              "webm": {".webm"}}


def positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def nonnegative(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return number


def media_target(args: argparse.Namespace) -> tuple[Path, Path]:
    paths = project_paths(Path(args.source))
    if paths.root == STARTER_SOURCE.resolve():
        raise ValueError("starter is read-only; acquire media in an editable project")
    if Path(args.name).name != args.name or "\\" in args.name or args.name in {"", ".", ".."}:
        raise ValueError("--name must be a filename, without directories")
    paths.media.mkdir(exist_ok=True)
    if not paths.media.resolve().is_relative_to(paths.root):
        raise ValueError("media/ must stay inside the selected project")
    target = paths.media / args.name
    if target.exists() or target.is_symlink():
        raise ValueError(f"refusing to replace an existing asset: {target}")
    return paths.root, target


def remote_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--url must be an http(s) source URL")
    return value


def inspect_asset(path: Path, *, expected_suffix: str | None = None) -> dict:
    with path.open("rb") as stream:
        header = stream.read(32)
    info: dict = {"bytes": path.stat().st_size}
    if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
        kind = "png"
        info["width"], info["height"] = struct.unpack(">II", header[16:24])
    elif header.startswith(b"\xff\xd8\xff"):
        kind = "jpeg"
    elif header.startswith((b"GIF87a", b"GIF89a")) and len(header) >= 10:
        kind = "gif"
        info["width"], info["height"] = struct.unpack("<HH", header[6:10])
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        kind = "webp"
    elif header[4:8] == b"ftyp":
        kind = "avif" if b"avif" in header or b"avis" in header else "mp4"
    elif header.startswith(b"\x1a\x45\xdf\xa3"):
        kind = "webm"
    else:
        raise ValueError("download is not a supported image/video; it may be an HTML error page")
    suffix = (expected_suffix or path.suffix).lower()
    if suffix not in EXTENSIONS[kind]:
        raise ValueError(f"file is {kind}, but the chosen filename ends in {suffix}")
    info["type"] = kind
    return info


def fetch(args: argparse.Namespace) -> dict:
    """Download one original image or short video with a size limit."""
    url = remote_url(args.url)
    _, target = media_target(args)
    if args.max_mb > 128:
        raise ValueError("--max-mb cannot exceed 128; select a short source clip")
    limit = int(args.max_mb * 1024 * 1024)
    request = urllib.request.Request(url, headers={"User-Agent": "html-edge-tts-video/1.0"})
    # A sibling temporary file keeps replacement atomic without leaving partial assets.
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=target.suffix, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            deadline = time.monotonic() + 45
            with urllib.request.urlopen(request, timeout=15) as response:
                if int(response.headers.get("Content-Length") or 0) > limit:
                    raise ValueError("source exceeds --max-mb; choose a shorter/smaller asset")
                total = 0
                while chunk := response.read(64 * 1024):
                    total += len(chunk)
                    if total > limit or time.monotonic() > deadline:
                        raise ValueError("download exceeded its size/time budget")
                    stream.write(chunk)
            stream.close()
            info = inspect_asset(temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"path": str(target), "source": url, **info}


def capture(args: argparse.Namespace) -> dict:
    """Capture one visible source page or a bounded CSS-selector excerpt."""
    url = remote_url(args.url)
    _, target = media_target(args)
    if target.suffix.lower() != ".png":
        raise ValueError("captures use a .png filename")
    from .toolchain import configure_playwright_environment

    configure_playwright_environment()
    for folder in (PLAYWRIGHT_TMP, PLAYWRIGHT_PROFILES, PLAYWRIGHT_SCREENSHOTS):
        folder.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(dir=PLAYWRIGHT_PROFILES, prefix="source-") as profile:
        scratch = PLAYWRIGHT_SCREENSHOTS / f"{Path(profile).name}.png"
        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    profile, headless=True, viewport={"width": 1280, "height": 720},
                    device_scale_factor=1, downloads_path=str(PLAYWRIGHT_TMP),
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(10000)
                    page.set_default_navigation_timeout(20000)
                    response = page.goto(url, wait_until="domcontentloaded")
                    if response is not None and not response.ok:
                        raise ValueError(f"source page returned HTTP {response.status}")
                    page.evaluate("() => Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 2000))])")
                    if args.selector:
                        locator = page.locator(args.selector).first
                        locator.wait_for(state="visible")
                        box = locator.bounding_box()
                        if not box or box["width"] > 2560 or box["height"] > 1440:
                            raise ValueError("selector is too large; capture a relevant excerpt")
                        locator.screenshot(path=str(scratch), animations="disabled")
                    else:
                        page.screenshot(path=str(scratch), full_page=False, animations="disabled")
                    info = inspect_asset(scratch)
                    shutil.copyfile(scratch, target)
                finally:
                    context.close()
        finally:
            scratch.unlink(missing_ok=True)
    return {"path": str(target), "source": url, **info}


def clip(args: argparse.Namespace) -> dict:
    """Convert a useful short excerpt to a silent, seekable MP4."""
    from .toolchain import ffmpeg_executable

    root, target = media_target(args)
    original = (root / args.input).resolve()
    if not original.is_relative_to((root / "media").resolve()) or not original.is_file():
        raise ValueError("--input must be an existing asset inside this project's media/")
    if target.suffix.lower() != ".mp4":
        raise ValueError("prepared clips use a .mp4 filename")
    if args.duration > 30:
        raise ValueError("--duration cannot exceed 30 seconds; select a useful short excerpt")
    inspect_asset(original)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".mp4", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        process = subprocess.run([
            ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-threads", "1", "-ss", str(args.start), "-i", str(original), "-t", str(args.duration),
            "-an", "-filter_threads", "1", "-vf", "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=15",
            "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
        ], capture_output=True, text=True, timeout=60, check=False)
        if process.returncode:
            raise ValueError(f"clip conversion failed: {process.stderr[-1500:]}")
        info = inspect_asset(temporary)
        probe = subprocess.run(
            [ffmpeg_executable(), "-hide_banner", "-i", str(temporary)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if not re.search(r"Stream .*Video:", probe.stderr):
            raise ValueError("selected interval produced no video stream; check --start and the source duration")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(target), "input": args.input, "start": args.start, "durationLimit": args.duration, **info}


def execute(args: argparse.Namespace) -> None:
    try:
        result = {"fetch": fetch, "capture": capture, "clip": clip}[args.media_command](args)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"Media preparation failed: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Inspect this asset, record its source/reuse basis, and bind it to narration in production.json.")


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("media", help="Acquire project media or prepare a bounded silent clip.")
    commands = parser.add_subparsers(dest="media_command", required=True)
    for name, handler in (("fetch", fetch), ("capture", capture), ("clip", clip)):
        command = commands.add_parser(name, help=handler.__doc__)
        command.add_argument("--source", required=True)
        command.add_argument("--name", required=True, help="New filename inside the project's media/.")
        if name == "clip":
            command.add_argument("--input", required=True, help="Project-relative media/ input.")
            command.add_argument("--start", type=nonnegative, default=0)
            command.add_argument("--duration", type=positive, default=12)
        else:
            command.add_argument("--url", required=True)
            if name == "fetch":
                command.add_argument("--max-mb", type=positive, default=32)
            else:
                command.add_argument("--selector", help="CSS selector for one relevant excerpt/figure.")
        command.set_defaults(func=execute)
