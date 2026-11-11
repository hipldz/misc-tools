import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, url_for

from .git_service import apply_bulk_file_action, apply_file_action, checkout_repo, commit_repo, discard_repo_changes, get_repo_status, preview_repo_file, push_origin_main, run_git
from .http_utils import api_error, read_json_body, send_bytes_download
from . import runtime
from .repo_store import RepoStore
from .snapshot_service import export_working_tree_snapshot, import_working_tree_snapshot


STATIC_DIR = runtime.resource_path("static")
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
store = RepoStore()


def index():
    template = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return render_template_string(
        template,
        app_base_path=request.script_root or "",
        style_url=url_for("static", filename="style.css"),
        message_js_url=url_for("static", filename="message.js"),
        app_js_url=url_for("static", filename="app.js"),
    )


def config():
    return jsonify(
        {
            "success": True,
            "default_workspace": runtime.DEFAULT_WORKSPACE,
            "host": runtime.HOST,
            "port": runtime.PORT,
            "base_path": request.script_root or "",
        }
    )


def select_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected_path = filedialog.askdirectory(title="Select workspace folder")
        root.destroy()
        return jsonify({"success": True, "path": selected_path})
    except ModuleNotFoundError:
        return api_error(
            "Folder picker is unavailable in this Python environment. Please type or paste the workspace path manually.",
            501,
        )
    except Exception as exc:
        return api_error(f"Failed to open folder picker: {exc}", 500)


def scan():
    payload = read_json_body()
    parent = Path(str(payload.get("path", ""))).expanduser()
    fetch_remote = bool(payload.get("fetch_remote", False))
    if not parent.exists() or not parent.is_dir():
        return api_error("Path does not exist or is not a directory.", 400)
    repos, non_git_dirs = scan_workspace(parent, fetch_remote=fetch_remote)
    return jsonify({"success": True, "repos": repos, "non_git_dirs": non_git_dirs})


def require_repo(repo_id: str) -> Path:
    repo_path = store.get_path(repo_id)
    if repo_path is None:
        raise LookupError("Repository id not found.")
    if not repo_path.exists() or not repo_path.is_dir():
        raise LookupError("Repository path no longer exists.")
    return repo_path


def refresh_repo(repo_id: str):
    repo_path = require_repo(repo_id)
    repo = get_repo_status(repo_id, repo_path)
    store.update(repo_id, repo)
    return repo


def scan_workspace(parent: Path, fetch_remote: bool = False):
    repos = []
    non_git_dirs = []
    store.clear()
    for child in sorted(parent.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        if (child / ".git").exists():
            repo_id = store.add(child)
            if fetch_remote:
                run_git(child, ["fetch", "--all", "--prune"])
            repo = get_repo_status(repo_id, child)
            store.update(repo_id, repo)
            repos.append(repo)
        else:
            non_git_dirs.append({"name": child.name, "path": str(child)})
    return repos, non_git_dirs


def with_repo(repo_id: str):
    try:
        return require_repo(repo_id), None
    except LookupError as exc:
        return None, api_error(str(exc), 404)


def refresh_all_repos(fetch_remote: bool = False):
    refreshed = []
    for repo in store.all():
        repo_id = repo.get("id")
        if not repo_id:
            continue
        try:
            repo_path = require_repo(repo_id)
            if fetch_remote:
                run_git(repo_path, ["fetch", "--all", "--prune"])
            refreshed.append(refresh_repo(repo_id))
        except LookupError:
            continue
    return refreshed


def run_repo_command(repo_id: str, args):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    result = run_git(repo_path, args)
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def repos():
    return jsonify({"success": True, "repos": store.all()})


def refresh(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    _ = repo_path
    return jsonify({"success": True, "repo": refresh_repo(repo_id)})


def refresh_all():
    payload = read_json_body()
    fetch_remote = bool(payload.get("fetch_remote", False))
    repos = refresh_all_repos(fetch_remote=fetch_remote)
    return jsonify({"success": True, "repos": repos})


def fetch(repo_id: str):
    return run_repo_command(repo_id, ["fetch"])


def pull(repo_id: str):
    return run_repo_command(repo_id, ["pull"])


def push(repo_id: str):
    return run_repo_command(repo_id, ["push"])


def push_origin_main_route(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    result = push_origin_main(repo_path)
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def open_repo(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    try:
        if sys.platform.startswith("win"):
            os.startfile(repo_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(repo_path)])
        else:
            subprocess.Popen(["xdg-open", str(repo_path)])
    except Exception as exc:
        return api_error(f"Failed to open repository folder: {exc}", 500)
    return jsonify({"success": True})


def commit(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    payload = read_json_body()
    result = commit_repo(repo_path, str(payload.get("message", "")))
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def checkout(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    payload = read_json_body()
    result = checkout_repo(repo_path, str(payload.get("branch", "")))
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def discard(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    result = discard_repo_changes(repo_path)
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def file_preview(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    payload = read_json_body()
    result = preview_repo_file(repo_path, str(payload.get("path", "")), str(payload.get("scope", "")))
    return jsonify(result)


def file_action(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    payload = read_json_body()
    result = apply_file_action(repo_path, str(payload.get("action", "")), str(payload.get("path", "")))
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def bulk_file_action(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    payload = read_json_body()
    repo_status = get_repo_status(repo_id, repo_path)
    result = apply_bulk_file_action(repo_path, str(payload.get("scope", "")), str(payload.get("action", "")), repo_status)
    repo = refresh_repo(repo_id)
    return jsonify({"success": result["success"], "result": result, "repo": repo})


def export_state(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    try:
        archive = export_working_tree_snapshot(repo_path)
    except ValueError as exc:
        return api_error(str(exc), 400)
    filename = "{0}-working-tree-snapshot.zip".format(repo_path.name)
    return send_bytes_download(archive, filename, "application/zip")


def import_state(repo_id: str):
    repo_path, error = with_repo(repo_id)
    if error:
        return error
    snapshot = request.files.get("snapshot")
    if snapshot is None:
        return api_error("Snapshot file is required.", 400)
    try:
        archive = snapshot.read()
        result = import_working_tree_snapshot(repo_path, archive)
    except ValueError as exc:
        return api_error(str(exc), 400)
    repo = refresh_repo(repo_id)
    return jsonify({"success": True, "result": result, "repo": repo})


def register_routes(flask_app: Flask):
    flask_app.before_request(runtime.require_authorization)
    flask_app.add_url_rule("/", "index", index)
    flask_app.add_url_rule("/api/config", "config", config)
    flask_app.add_url_rule("/api/select-folder", "select_folder", select_folder, methods=["POST"])
    flask_app.add_url_rule("/api/scan", "scan", scan, methods=["POST"])
    flask_app.add_url_rule("/api/repos", "repos", repos)
    flask_app.add_url_rule("/api/repos/<repo_id>/refresh", "refresh", refresh, methods=["POST"])
    flask_app.add_url_rule("/api/repos/refresh-all", "refresh_all", refresh_all, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/fetch", "fetch", fetch, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/pull", "pull", pull, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/push", "push", push, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/push-origin-main", "push_origin_main_route", push_origin_main_route, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/open", "open_repo", open_repo, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/commit", "commit", commit, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/checkout", "checkout", checkout, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/discard", "discard", discard, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/files/preview", "file_preview", file_preview, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/files/action", "file_action", file_action, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/files/bulk-action", "bulk_file_action", bulk_file_action, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/export-state", "export_state", export_state, methods=["POST"])
    flask_app.add_url_rule("/api/repos/<repo_id>/import-state", "import_state", import_state, methods=["POST"])
