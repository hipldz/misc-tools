#!/usr/bin/env python3
"""Validate source content against the shell's caption-safe layout boundary."""
from __future__ import annotations

import argparse
import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

try:
    from .factory import ROOT, load_scenes, normalize_aspect_ratio, project_paths, read_json
    from .toolchain import configure_playwright_environment
except ImportError:  # Direct script execution: python pipeline/validate_layout.py
    from factory import ROOT, load_scenes, normalize_aspect_ratio, project_paths, read_json
    from toolchain import configure_playwright_environment


SAFE_CONTENT_RATIO = 0.75


class LayoutHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: object, project_root: Path, **kwargs: object) -> None:
        self.project_root = project_root.resolve()
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *_: object) -> None:
        pass

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        if parsed.path == "/__project__" or parsed.path.startswith("/__project__/"):
            relative = unquote(parsed.path.removeprefix("/__project__/")).replace("/", os.sep)
            target = (self.project_root / relative).resolve()
            try:
                target.relative_to(self.project_root)
            except ValueError:
                return str(ROOT / ".invalid-project-path")
            return str(target)
        return super().translate_path(path)


def validate_layout(source: Path) -> None:
    paths = project_paths(source)
    scenes = load_scenes(paths.root)
    manifest = read_json(paths.manifest)
    aspect_ratio = normalize_aspect_ratio(
        manifest.get("aspectRatio") if isinstance(manifest, dict) else None
    )
    viewport = {"width": 720, "height": 1280} if aspect_ratio == "9:16" else {
        "width": 1280,
        "height": 720,
    }

    handler = functools.partial(LayoutHandler, project_root=paths.root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    configure_playwright_environment()
    from playwright.sync_api import sync_playwright

    violations: list[dict[str, object]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport=viewport)
            project_base = quote("/__project__", safe="")
            page.goto(
                f"http://127.0.0.1:{port}/pipeline/shell/index.html"
                f"?projectBase={project_base}&render=1&capture=frames&transition=0",
                wait_until="networkidle",
            )
            page.wait_for_function(
                "window.compositionReady === true || Boolean(window.compositionError)"
            )
            error = page.evaluate("window.compositionError || ''")
            if error:
                raise SystemExit(f"Layout validation could not load the composition: {error}")

            for scene in scenes:
                scene_id = str(scene.get("id") or "")
                result = page.evaluate(
                    """async ({ sceneId, safeRatio }) => {
                      await window.renderScene(sceneId, 0.5);
                      await new Promise(resolve => requestAnimationFrame(
                        () => requestAnimationFrame(resolve)
                      ));
                      const active = [...document.querySelectorAll('[data-scene]')]
                        .find(node => node.dataset.scene === sceneId && node.classList.contains('is-active'));
                      if (!active) return [{ selector: '[data-scene]', bottom: innerHeight }];
                      const boundary = innerHeight * safeRatio;
                      const mediaTags = new Set(['IMG', 'VIDEO', 'SVG', 'CANVAS']);
                      const selectorFor = node => {
                        if (node.dataset?.studioId) return `[data-studio-id="${node.dataset.studioId}"]`;
                        if (node.classList?.length) return `${node.tagName.toLowerCase()}.${[...node.classList].join('.')}`;
                        return node.tagName.toLowerCase();
                      };
                      return [...active.querySelectorAll('*')].flatMap(node => {
                        const style = getComputedStyle(node);
                        if (
                          style.display === 'none'
                          || style.visibility === 'hidden'
                          || Number(style.opacity) === 0
                        ) return [];
                        const directText = [...node.childNodes].some(child => (
                          child.nodeType === Node.TEXT_NODE && child.textContent.trim()
                        ));
                        const meaningful = directText
                          || mediaTags.has(node.tagName)
                          || Boolean(node.dataset?.studioId);
                        if (!meaningful) return [];
                        const rect = node.getBoundingClientRect();
                        if (
                          rect.width <= 1
                          || rect.height <= 1
                          || rect.bottom <= boundary + 1
                          || rect.top >= innerHeight
                        ) return [];
                        return [{
                          selector: selectorFor(node),
                          top: Math.round(rect.top),
                          bottom: Math.round(rect.bottom),
                          boundary: Math.round(boundary),
                          text: directText ? node.textContent.trim().replace(/\\s+/g, ' ').slice(0, 60) : '',
                        }];
                      });
                    }""",
                    {"sceneId": scene_id, "safeRatio": SAFE_CONTENT_RATIO},
                )
                violations.extend({"scene": scene_id, **item} for item in result)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    if violations:
        details = "\n".join(
            f"- scene {item['scene']}: {item['selector']} ends at y={item['bottom']} "
            f"(safe boundary y={item['boundary']})"
            + (f" — {item['text']}" if item.get("text") else "")
            for item in violations[:20]
        )
        extra = len(violations) - 20
        if extra > 0:
            details += f"\n- …and {extra} more violation(s)"
        raise SystemExit(
            "Layout validation failed: source content must stay inside the top 75% "
            "so shell captions and chapters remain unobstructed.\n" + details
        )

    print(
        f"Layout validation passed: {len(scenes)} scenes stay above the "
        f"{round(SAFE_CONTENT_RATIO * 100)}% caption-safe boundary"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source")
    args = parser.parse_args()
    validate_layout(project_paths(Path(args.source) if args.source else None).root)


if __name__ == "__main__":
    main()
