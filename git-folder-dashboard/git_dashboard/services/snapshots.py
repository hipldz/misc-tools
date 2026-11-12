import io
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import List
from zipfile import ZIP_DEFLATED, ZipFile

from .git import read_status, resolve_repo_file, run_git

SNAPSHOT_VERSION = 1


def _validate_snapshot_path(file_path: str) -> PurePosixPath:
    if not isinstance(file_path, str):
        raise ValueError("Snapshot entry path must be a string.")
    normalized = PurePosixPath(file_path)
    if not file_path.strip():
        raise ValueError("Snapshot entry path is required.")
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"Snapshot entry path is invalid: {file_path}")
    return normalized


def _collect_scope(index_status: str, worktree_status: str) -> List[str]:
    scopes: List[str] = []
    if index_status not in {" ", "?"}:
        scopes.append("staged")
    if worktree_status not in {" ", "?"}:
        scopes.append("unstaged")
    if index_status == "?" and worktree_status == "?":
        scopes.append("untracked")
    return scopes


def _classify_entry(index_status: str, worktree_status: str, exists: bool) -> str:
    if not exists:
        return "deleted"
    if index_status == "?" and worktree_status == "?":
        return "added"
    if index_status == "A":
        return "added"
    return "modified"


def _read_working_tree_entries(repo_path: Path) -> List[dict]:
    status_result, parsed_entries = read_status(repo_path)
    if not status_result["success"]:
        raise ValueError(status_result["stderr"] or status_result["stdout"] or "Failed to read repository status.")
    entries: List[dict] = []
    seen_paths = set()
    for parsed in parsed_entries:
        file_path = parsed["path"]
        if file_path in seen_paths:
            continue
        seen_paths.add(file_path)
        original = parsed.get("original_path")
        if original and "R" in parsed["index_status"] + parsed["worktree_status"]:
            original_exists = resolve_repo_file(repo_path, original).is_file()
            entries.append({"path": original, "kind": "modified" if original_exists else "deleted", "scope": _collect_scope(parsed["index_status"], parsed["worktree_status"]), "exists": original_exists})
            seen_paths.add(original)
        target = resolve_repo_file(repo_path, file_path)
        exists = target.exists() and target.is_file()
        entries.append({"path": file_path, "kind": _classify_entry(parsed["index_status"], parsed["worktree_status"], exists), "scope": _collect_scope(parsed["index_status"], parsed["worktree_status"]), "exists": exists})
    return entries


def build_snapshot_manifest(repo_path: Path) -> dict:
    branch_result = run_git(repo_path, ["branch", "--show-current"])
    base_branch = branch_result["stdout"].strip() if branch_result["success"] else ""
    entries = _read_working_tree_entries(repo_path)
    manifest_entries: List[dict] = []
    for index, entry in enumerate(sorted(entries, key=lambda item: item["path"]), start=1):
        manifest_entry = {"path": entry["path"], "kind": entry["kind"], "scope": entry["scope"]}
        if entry["exists"]:
            manifest_entry["content_file"] = f"files/{index:04d}"
        manifest_entries.append(manifest_entry)
    return {"version": SNAPSHOT_VERSION, "format": "git-folder-dashboard-working-tree", "repo_name": repo_path.name, "base_branch": base_branch, "created_at": datetime.now(timezone.utc).isoformat(), "entries": manifest_entries}


def export_working_tree_snapshot(repo_path: Path) -> bytes:
    manifest = build_snapshot_manifest(repo_path)
    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        for entry in manifest["entries"]:
            content_file = entry.get("content_file")
            if not content_file:
                continue
            target = resolve_repo_file(repo_path, entry["path"])
            if not target.exists() or not target.is_file():
                raise ValueError(f"Snapshot export failed because {entry['path']} is no longer a file.")
            archive.writestr(content_file, target.read_bytes())
    return buffer.getvalue()


def _remove_target(target: Path) -> None:
    if target.is_symlink():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def _ensure_parent_dirs(target: Path, repo_root: Path) -> None:
    current = repo_root
    for part in target.relative_to(repo_root).parts[:-1]:
        current = current / part
        if current.exists() and not current.is_dir():
            current.unlink()
        current.mkdir(exist_ok=True)


def import_working_tree_snapshot(repo_path: Path, archive_bytes: bytes) -> dict:
    try:
        archive = ZipFile(io.BytesIO(archive_bytes))
    except Exception as exc:
        raise ValueError(f"Invalid snapshot archive: {exc}") from exc
    with archive:
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("Snapshot archive does not contain manifest.json.") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Snapshot manifest is invalid JSON: {exc}") from exc
        if not isinstance(manifest, dict):
            raise ValueError("Snapshot manifest must be an object.")
        if manifest.get("version") != SNAPSHOT_VERSION:
            raise ValueError("Unsupported snapshot version.")
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise ValueError("Snapshot manifest entries are invalid.")
        deletions: List[Path] = []
        writes: List[dict] = []
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError("Snapshot entry is invalid.")
            relative_path = item.get("path", "")
            normalized = _validate_snapshot_path(relative_path)
            target = resolve_repo_file(repo_path, normalized.as_posix())
            kind = item.get("kind")
            if kind not in {"deleted", "added", "modified"}:
                raise ValueError("Snapshot entry kind is invalid.")
            if kind == "deleted":
                deletions.append(target)
                continue
            content_file = item.get("content_file")
            if not isinstance(content_file, str) or not content_file:
                raise ValueError(f"Snapshot entry {normalized.as_posix()} is missing content_file.")
            try:
                content = archive.read(content_file)
            except KeyError as exc:
                raise ValueError(f"Snapshot content file is missing: {content_file}") from exc
            writes.append({"target": target, "content": content})
        for target in deletions:
            if target.exists() or target.is_symlink():
                _remove_target(target)
        for item in writes:
            target = item["target"]
            _ensure_parent_dirs(target, repo_path.resolve())
            if target.exists() and target.is_dir():
                _remove_target(target)
            target.write_bytes(item["content"])
    return {"success": True, "exported_entries": len(entries), "written_files": len(writes), "deleted_files": len(deletions)}

