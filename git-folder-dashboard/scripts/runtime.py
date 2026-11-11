import argparse
import hmac
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

from flask import Flask, Response, request

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
PORT = 8765
DEFAULT_WORKSPACE = ""
NO_BROWSER = False
BASE_PATH = ""
AUTHORIZATION: Optional[Tuple[str, str]] = None


def resource_path(relative_path: str) -> Path:
    base_path = getattr(sys, "_MEIPASS", PROJECT_ROOT)
    return Path(base_path) / relative_path


class PrefixMiddleware(object):
    def __init__(self, app, prefix=""):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if not self.prefix:
            return self.app(environ, start_response)
        path_info = environ.get("PATH_INFO", "") or "/"
        if path_info == self.prefix:
            start_response("308 Permanent Redirect", [("Location", self.prefix + "/")])
            return [b""]
        if path_info.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = self.prefix
            environ["PATH_INFO"] = path_info[len(self.prefix):] or "/"
            return self.app(environ, start_response)
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not Found"]


def open_browser():
    time.sleep(1)
    target = "http://{0}:{1}{2}/".format(HOST, PORT, BASE_PATH)
    webbrowser.open(target)


def normalize_base_path(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or cleaned == "/":
        return ""
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    return cleaned.rstrip("/")


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Invalid boolean value: {0}".format(value))


def parse_authorization(value: str) -> Tuple[str, str]:
    username, separator, password = value.partition(":")
    if not separator or not username or not password:
        raise argparse.ArgumentTypeError(
            "Authorization must use the format <username>:<password> with both values non-empty."
        )
    return username, password


def require_authorization():
    if AUTHORIZATION is None:
        return None
    supplied = request.authorization
    expected_username, expected_password = AUTHORIZATION
    is_basic = bool(supplied and (supplied.type or "").lower() == "basic")
    supplied_username = supplied.username if is_basic else ""
    supplied_password = supplied.password if is_basic else ""
    username_matches = hmac.compare_digest(
        (supplied_username or "").encode("utf-8"), expected_username.encode("utf-8")
    )
    password_matches = hmac.compare_digest(
        (supplied_password or "").encode("utf-8"), expected_password.encode("utf-8")
    )
    if username_matches and password_matches:
        return None
    return Response(
        "Authorization required.",
        401,
        {
            "WWW-Authenticate": 'Basic realm="Git Folder Dashboard", charset="UTF-8"',
            "Cache-Control": "no-store",
        },
    )


def parse_args() -> argparse.Namespace:
    """Keep the old import location while using the shared CLI parser."""
    from .cli import parse_args as parse_cli_args

    return parse_cli_args()


def apply_runtime_config(args: argparse.Namespace, app: Flask) -> None:
    global HOST, PORT, DEFAULT_WORKSPACE, NO_BROWSER, BASE_PATH, AUTHORIZATION
    HOST = args.host
    PORT = args.port
    DEFAULT_WORKSPACE = args.default_path.strip()
    NO_BROWSER = args.no_browser
    BASE_PATH = normalize_base_path(args.base_path)
    AUTHORIZATION = args.authorize
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, BASE_PATH)
