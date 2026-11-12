"""HTTP validation and orchestration. Git logic lives in services/."""

from flask import jsonify, render_template, request

from .http import read_json_body, send_bytes_download
from .services.folders import choose_folder
from .services.git import (apply_bulk_file_action, apply_file_action, checkout_repo,
                           commit_repo, get_repo_status, open_path, preview_repo_file, run_git)
from .services.snapshots import export_working_tree_snapshot, import_working_tree_snapshot


def register_routes(app, workspace, tasks, version):
    def state_payload():
        return dict(workspace.snapshot(), tasks=tasks.snapshot(), success=True, instance_id=app.config["INSTANCE_ID"])

    @app.route("/")
    def index():
        return render_template("index.html", version=version, base_path=request.script_root)

    @app.route("/api/config")
    def config():
        return jsonify(success=True, version=version, default_workspace=app.config["DEFAULT_WORKSPACE"],
                       sync_interval=app.config["SYNC_INTERVAL"], remote_ttl=app.config["REMOTE_TTL"])

    @app.route("/api/state")
    def state():
        return jsonify(state_payload())

    @app.route("/api/workspace", methods=["POST"])
    def select_workspace():
        payload = read_json_body()
        workspace.select(str(payload.get("path", "")))
        tasks.start(fetch_remote=bool(payload.get("fetch_remote", True)))
        return jsonify(state_payload()), 202

    @app.route("/api/workspace/refresh", methods=["POST"])
    def refresh_workspace():
        if not workspace.path:
            raise ValueError("Select a workspace first.")
        payload = read_json_body()
        workspace.select(workspace.path, preserve_generation=True)
        task = tasks.start(fetch_remote=bool(payload.get("fetch_remote", False)))
        return jsonify(dict(state_payload(), task=task)), 202

    @app.route("/api/select-folder", methods=["POST"])
    def select_folder():
        try:
            return jsonify(success=True, path=choose_folder())
        except Exception as exc:
            raise ValueError("Folder picker is unavailable. Paste a workspace path instead. " + str(exc))

    @app.route("/api/repos/<repo_id>/refresh", methods=["POST"])
    def refresh(repo_id):
        repo = workspace.refresh(repo_id)
        return jsonify(success=True, repo=repo)

    @app.route("/api/repos/<repo_id>/fetch", methods=["POST"])
    def fetch(repo_id):
        return jsonify(success=True, task=tasks.start(fetch_remote=True, repo_ids=[repo_id])), 202

    @app.route("/api/repos/<repo_id>/<action>", methods=["POST"])
    def repo_action(repo_id, action):
        payload = read_json_body()

        def operation(path):
            if action == "commit":
                return commit_repo(path, str(payload.get("message", "")), payload.get("stage_all") is True)
            if action == "checkout":
                return checkout_repo(path, str(payload.get("branch", "")))
            if action in ("pull", "push"):
                return run_git(path, ["pull", "--ff-only"] if action == "pull" else ["push"])
            if action == "open":
                open_path(path)
                return {"success": True, "stdout": "", "stderr": ""}
            raise ValueError("Unsupported repository action.")

        result, repo = workspace.mutate(repo_id, operation)
        return jsonify(success=result["success"], result=result, repo=repo)

    @app.route("/api/repos/<repo_id>/files/preview", methods=["POST"])
    def file_preview(repo_id):
        payload = read_json_body()
        # Diff is read-only and remains available while a network fetch is running.
        result = preview_repo_file(workspace.require(repo_id), str(payload.get("path", "")),
                                   str(payload.get("scope", "")))
        return jsonify(result)

    @app.route("/api/repos/<repo_id>/files/action", methods=["POST"])
    def file_action(repo_id):
        payload = read_json_body()
        result, repo = workspace.mutate(repo_id, lambda path: apply_file_action(
            path, str(payload.get("action", "")), str(payload.get("path", ""))))
        return jsonify(success=result["success"], result=result, repo=repo)

    @app.route("/api/repos/<repo_id>/files/bulk-action", methods=["POST"])
    def bulk_file_action(repo_id):
        payload = read_json_body()
        result, repo = workspace.mutate(repo_id, lambda path: apply_bulk_file_action(
            path, str(payload.get("scope", "")), str(payload.get("action", "")), get_repo_status(repo_id, path)))
        return jsonify(success=result["success"], result=result, repo=repo)

    @app.route("/api/repos/<repo_id>/export-state", methods=["POST"])
    def export_state(repo_id):
        with workspace.repo_lock(repo_id):
            path = workspace.require(repo_id)
            archive = export_working_tree_snapshot(path)
        return send_bytes_download(archive, path.name + "-working-tree-snapshot.zip", "application/zip")

    @app.route("/api/repos/<repo_id>/import-state", methods=["POST"])
    def import_state(repo_id):
        snapshot = request.files.get("snapshot")
        if snapshot is None:
            raise ValueError("Choose a snapshot zip file first.")
        content = snapshot.read()
        result, repo = workspace.mutate(repo_id, lambda path: import_working_tree_snapshot(path, content))
        return jsonify(success=True, result=result, repo=repo)
