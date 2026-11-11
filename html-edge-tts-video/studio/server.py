#!/usr/bin/env python3
"""Serve the Studio web app and its local JSON API."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from pipeline.captions import default_doc, load_effective_doc, load_timeline, save_doc
from pipeline.factory import ROOT, active_source_root, project_web_base, shell_relative_url
from studio.api import ApiError, active_project_meta, handle_get, handle_post, save_media
from studio import web_paths


APP_HTML_PATHS = {
    "/studio/web/studio/index.html",
    "/studio/web/source/index.html",
    "/studio/web/captions/index.html",
    "/studio/web/voices/index.html",
    "/pipeline/shell/index.html",
}


def render_app_html(source: str) -> bytes:
    source = source.replace(
        '<meta name="app-base-path" content="" />',
        f'<meta name="app-base-path" content="{web_paths.BASE_PATH}" />',
    )
    source = re.sub(
        r"\b(href|src)=([\"'])(/(?!/)[^\"']*)(\2)",
        lambda match: f'{match[1]}={match[2]}{web_paths.app_url(match[3])}{match[4]}',
        source,
    )
    return source.encode("utf-8")


class FactoryHandler(SimpleHTTPRequestHandler):
    _byte_range: tuple[int, int] | None = None

    def normalize_request_path(self) -> bool:
        parsed = urlparse(self.path)
        path = web_paths.internal_path(parsed.path)
        if path is None:
            self.send_error(404, "outside configured base path")
            return False
        if path == "":
            location = web_paths.app_url("/")
            if parsed.query:
                location += f"?{parsed.query}"
            self.send_response(308)
            # Already a public URL; bypass the internal-redirect prefix helper.
            super().send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        self.path = path + (f"?{parsed.query}" if parsed.query else "")
        return True

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "location":
            value = web_paths.app_url(value)
        super().send_header(keyword, value)

    def do_HEAD(self) -> None:
        if self.normalize_request_path():
            parsed = urlparse(self.path)
            self.path = self.tool_routes().get(parsed.path, self.path)
            super().do_HEAD()

    @staticmethod
    def tool_routes() -> dict[str, str]:
        return {
            "/": "/studio/web/studio/index.html",
            "/studio": "/studio/web/studio/index.html",
            "/studio/main": "/studio/web/studio/index.html",
            "/studio/new": "/studio/web/studio/index.html",
            "/studio/voice": "/studio/web/voices/index.html",
            "/voices": "/studio/web/voices/index.html",
            "/captions": "/studio/web/captions/index.html",
            "/source": "/studio/web/source/index.html",
        }

    def log_message(self, message: str, *args: object) -> None:
        if self.path.startswith("/api/"):
            print(f"[http] {self.command} {self.path} - {message % args}", flush=True)

    def copyfile(self, source, outputfile) -> None:
        try:
            if self._byte_range is not None:
                start, end = self._byte_range
                source.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = source.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    outputfile.write(chunk)
                    remaining -= len(chunk)
                return
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers commonly cancel asset requests during reloads or navigation.
            # Treat those disconnects as normal and avoid noisy tracebacks on Windows.
            return
        finally:
            self._byte_range = None

    def end_headers(self) -> None:
        static_path = urlparse(self.path).path
        if (
            static_path.startswith("/studio/web/")
            and Path(static_path).suffix in {".html", ".css", ".js"}
        ):
            # Studio is a local editing surface. Always load matching UI assets
            # so a changed page stylesheet cannot run against a stale app shell.
            self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        file_path = Path(self.translate_path(self.path))
        if file_path.is_dir() and urlparse(self.path).path.endswith("/"):
            file_path /= "index.html"
        if file_path in {ROOT / path.lstrip("/") for path in APP_HTML_PATHS}:
            try:
                source = file_path.read_text(encoding="utf-8")
            except OSError:
                self.send_error(404, "app entry not found")
                return None
            body = render_app_html(source)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if not urlparse(self.path).path.startswith("/studio/web/"):
                self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return io.BytesIO(body)
        range_header = self.headers.get("Range", "")
        if not range_header.startswith("bytes=") or "," in range_header:
            return super().send_head()

        file_path = Path(self.translate_path(self.path))
        if not file_path.is_file():
            return super().send_head()

        size = file_path.stat().st_size
        try:
            start_text, end_text = range_header[6:].split("-", 1)
            if start_text:
                start = int(start_text)
                end = min(int(end_text), size - 1) if end_text else size - 1
            else:
                suffix_length = int(end_text)
                start = max(0, size - suffix_length)
                end = size - 1
            if start < 0 or start >= size or end < start:
                raise ValueError
        except ValueError:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None

        source = file_path.open("rb")
        self._byte_range = (start, end)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(file_path)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(file_path.stat().st_mtime))
        self.end_headers()
        return source

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json(status, {"error": message})

    def send_redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def read_json_body(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "invalid content length") from exc
        if length <= 0 or length > 2_000_000:
            raise ApiError(400, "invalid request body size")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(400, str(exc)) from exc

    def do_GET(self) -> None:
        if not self.normalize_request_path():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        tool_routes = self.tool_routes()
        if path in tool_routes:
            # Serve the app entry internally so the browser keeps the friendly
            # route. Studio uses that route to select the main/prompt/import view.
            self.path = tool_routes[path]
            super().do_GET()
            return

        try:
            studio_response = handle_get(path, query)
        except ApiError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        if studio_response:
            status, payload = studio_response
            self.send_json(status, payload)
            return

        if path == "/api/captions":
            try:
                timeline = load_timeline()
                doc, saved = load_effective_doc(timeline)
            except SystemExit as exc:
                self.send_error_json(409, str(exc))
                return
            source_root = active_source_root()
            project_meta = active_project_meta(source_root)
            web_base = project_web_base(source_root)
            self.send_json(
                200,
                {
                    "captions": doc,
                    "generated": default_doc(timeline),
                    "saved": saved,
                    "duration": timeline.get("duration"),
                    "scenes": timeline.get("scenes", []),
                    "previewUrl": web_paths.app_url(shell_relative_url(source_root)),
                    "audioUrl": web_paths.app_url(f"{web_base}/generated/narration.mp3"),
                    "sourcePath": str(source_root / "captions.json") if source_root else None,
                    "narrationSourcePath": str(source_root / "scenes.json") if source_root else None,
                    "sourceUrl": web_paths.app_url(f"{web_base}/"),
                    "aspectRatio": project_meta.get("aspectRatio", "16:9"),
                },
            )
            return
        super().do_GET()

    def do_POST(self) -> None:
        if not self.normalize_request_path():
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/projects/media":
            query = parse_qs(parsed.query)
            project_id = (query.get("project") or [""])[0]
            media_path = (query.get("path") or [""])[0]
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 150 * 1024 * 1024:
                    raise ApiError(400, "media upload must contain 1 byte to 150 MB")
                result = save_media(project_id, media_path, self.rfile.read(length))
            except ValueError:
                self.send_error_json(400, "invalid content length")
                return
            except ApiError as exc:
                self.send_error_json(exc.status, exc.message)
                return
            except OSError as exc:
                self.send_error_json(500, f"cannot write project media: {exc}")
                return
            self.send_json(201, result)
            return

        try:
            payload = self.read_json_body()
        except ApiError as exc:
            self.send_error_json(exc.status, exc.message)
            return

        if not isinstance(payload, dict) and path != "/api/captions":
            self.send_error_json(400, "request body must be a JSON object")
            return

        try:
            studio_response = handle_post(path, payload if isinstance(payload, dict) else {})
        except ApiError as exc:
            self.send_error_json(exc.status, exc.message)
            return
        if studio_response:
            status, result = studio_response
            self.send_json(status, result)
            return

        if path == "/api/captions":
            try:
                result = save_doc(payload)
            except (TypeError, ValueError) as exc:
                self.send_error_json(400, str(exc))
                return
            except OSError as exc:
                self.send_error_json(500, f"cannot write project captions.json: {exc}")
                return
            except SystemExit as exc:
                self.send_error_json(409, str(exc))
                return

            self.send_json(200, result)
            return

        self.send_error_json(404, "unknown endpoint")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Studio web app and JSON API.")
    parser.add_argument("--host", default="127.0.0.1", help="Interface or hostname to bind.")
    parser.add_argument("--port", type=int, default=8765, choices=range(1, 65536), metavar="PORT")
    parser.add_argument("--base-path", type=web_paths.normalize_base_path, default="", help="Public URL prefix, e.g. /xxx.")
    return parser.parse_args()


def display_host(host: str) -> str:
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def main() -> None:
    args = parse_args()
    web_paths.configure_base_path(args.base_path)
    os.chdir(ROOT)
    origin = f"http://{display_host(args.host)}:{args.port}"
    print(f"Studio: {origin}{web_paths.app_url('/')}")
    server = ThreadingHTTPServer((args.host, args.port), FactoryHandler)
    try:
        print(
            f"[server] Listening on {args.host}:{args.port} for browser and API activity. "
            "Press Ctrl+C to stop.",
            flush=True,
        )
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Shutdown requested.", flush=True)
    finally:
        server.server_close()
        print("[server] Stopped.", flush=True)


if __name__ == "__main__":
    main()
