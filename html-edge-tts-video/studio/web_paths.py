"""URL configuration for the Studio server, independent of project file paths."""
from __future__ import annotations

import re


BASE_PATH = ""


def normalize_base_path(value: str) -> str:
    path = value.strip()
    if path in {"", "/"}:
        return ""
    if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+/?", path):
        raise ValueError("base path must be / or slash-separated letters, numbers, underscores and hyphens")
    return path.rstrip("/")


def configure_base_path(value: str) -> None:
    global BASE_PATH
    BASE_PATH = normalize_base_path(value)


def app_url(path: str) -> str:
    """Prefix an internal root-relative URL; leave external/relative URLs alone."""
    if path.startswith("/") and not path.startswith("//"):
        return f"{BASE_PATH}{path}"
    return path


def internal_path(path: str) -> str | None:
    """Strip the configured mount prefix at a path-segment boundary."""
    if not BASE_PATH:
        return path
    if path == BASE_PATH:
        return ""
    if path.startswith(f"{BASE_PATH}/"):
        return path[len(BASE_PATH):]
    return None
