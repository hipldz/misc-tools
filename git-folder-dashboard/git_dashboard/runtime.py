"""Runtime configuration and resource paths for source and one-file builds."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resource_path(relative_path):
    return Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / relative_path


def normalize_base_path(value):
    cleaned = value.strip().strip("/")
    return "/" + cleaned if cleaned else ""


class PrefixMiddleware:
    def __init__(self, app, prefix=""):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if not self.prefix:
            return self.app(environ, start_response)
        path = environ.get("PATH_INFO", "/")
        if path == self.prefix:
            location = self.prefix + "/"
            if environ.get("QUERY_STRING"):
                location += "?" + environ["QUERY_STRING"]
            start_response("308 Permanent Redirect", [("Location", location)])
            return [b""]
        if path.startswith(self.prefix + "/"):
            environ["SCRIPT_NAME"] = self.prefix
            environ["PATH_INFO"] = path[len(self.prefix):]
            return self.app(environ, start_response)
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not Found"]
