import argparse
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence
from zipfile import ZipFile

from .git_service import run_git
from .snapshot_service import export_working_tree_snapshot, import_working_tree_snapshot


class SnapshotInputError(Exception):
    """Raised when the snapshot command arguments or target are invalid."""


class SnapshotWriteError(Exception):
    """Raised when the generated snapshot cannot be written."""


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("Invalid boolean value: {0}".format(value))


def parse_authorization(value: str):
    username, separator, password = value.partition(":")
    if not separator or not username or not password:
        raise argparse.ArgumentTypeError(
            "Authorization must use the format <username>:<password> with both values non-empty."
        )
    return username, password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Git Folder Dashboard web server or transfer a repository snapshot."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--export",
        dest="export_repo",
        metavar="REPO",
        default=None,
        help="Export a working-tree snapshot for a Git repository and exit.",
    )
    mode.add_argument(
        "--import",
        dest="import_snapshot",
        nargs=2,
        metavar=("REPO", "SNAPSHOT"),
        default=None,
        help="Import a snapshot into a Git repository and exit; requires --force.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="Export output file. Defaults to a timestamped file in the current directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow export overwrite or confirm an import.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind. Default: 8765")
    parser.add_argument(
        "--default-path",
        "--defaut-path",
        dest="default_path",
        default="",
        help="Default workspace path shown in the UI.",
    )
    parser.add_argument(
        "--base-path",
        dest="base_path",
        default="",
        help="Mount the app under a URL prefix such as /git.",
    )
    parser.add_argument(
        "--authorize",
        type=parse_authorization,
        metavar="USERNAME:PASSWORD",
        default=None,
        help="Require HTTP Basic authentication for every page, static asset, and API request.",
    )
    parser.add_argument(
        "--no-browser",
        "--no-brower",
        dest="no_browser",
        nargs="?",
        const="true",
        default="false",
        type=parse_bool,
        help="Disable auto-opening the browser. Supports true/false.",
    )
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _absolute_path(value: str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(value)))


def _resolve_git_repository(value: str) -> Path:
    if not value or not value.strip():
        raise SnapshotInputError("Repository path is required.")

    candidate = _absolute_path(value)
    if not candidate.exists() or not candidate.is_dir():
        raise SnapshotInputError("Repository path does not exist or is not a directory: {0}".format(candidate))

    root_result = run_git(candidate, ["rev-parse", "--show-toplevel"])
    if not root_result["success"]:
        message = root_result["stderr"].strip() or root_result["stdout"].strip()
        raise SnapshotInputError(
            "Path is not inside a Git working tree: {0}".format(message or candidate)
        )

    root_text = root_result["stdout"].strip()
    if not root_text:
        raise SnapshotInputError("Git did not return a repository root for: {0}".format(candidate))
    repository = _absolute_path(root_text)

    worktree_result = run_git(repository, ["rev-parse", "--is-inside-work-tree"])
    if not worktree_result["success"] or worktree_result["stdout"].strip().lower() != "true":
        raise SnapshotInputError("Target is not a Git working tree: {0}".format(repository))
    return repository


def _default_output_path(repository: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = "{0}-working-tree-snapshot-{1}".format(repository.name, timestamp)
    candidate = Path.cwd() / (base_name + ".zip")
    suffix = 2
    while candidate.exists():
        candidate = Path.cwd() / (base_name + "-{0}.zip".format(suffix))
        suffix += 1
    return candidate


def _resolve_output_path(repository: Path, value: Optional[str], force: bool) -> Path:
    output = _default_output_path(repository) if value is None else _absolute_path(value)
    if output.exists() and output.is_dir():
        raise SnapshotInputError("Snapshot output is a directory: {0}".format(output))
    if output.exists() and not force:
        raise SnapshotInputError(
            "Snapshot output already exists; use --force to overwrite it: {0}".format(output)
        )
    if not output.parent.exists() or not output.parent.is_dir():
        raise SnapshotInputError("Snapshot output directory does not exist: {0}".format(output.parent))
    return output


def _write_snapshot(output: Path, archive: bytes) -> None:
    temporary_path = None
    file_descriptor = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=".{0}.".format(output.name), suffix=".tmp", dir=str(output.parent)
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = None
            handle.write(archive)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary_path), str(output))
        temporary_path = None
    except OSError as exc:
        raise SnapshotWriteError("Failed to write snapshot {0}: {1}".format(output, exc)) from exc
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def export_snapshot(repository_value: str, output_value: Optional[str], force: bool) -> int:
    repository = _resolve_git_repository(repository_value)
    output = _resolve_output_path(repository, output_value, force)

    try:
        archive = export_working_tree_snapshot(repository)
    except (OSError, ValueError) as exc:
        raise SnapshotWriteError("Failed to generate snapshot: {0}".format(exc)) from exc

    try:
        with ZipFile(io.BytesIO(archive)) as zip_file:
            manifest = json.loads(zip_file.read("manifest.json").decode("utf-8"))
    except (KeyError, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise SnapshotWriteError("Generated snapshot has an invalid manifest: {0}".format(exc)) from exc

    _write_snapshot(output, archive)

    branch = manifest.get("base_branch") or "(detached/unborn)"
    print("Snapshot created: {0}".format(output))
    print("Repository: {0}".format(repository))
    print("Branch: {0}".format(branch))
    print("Entries: {0}".format(len(manifest.get("entries", []))))
    return 0


def import_snapshot(repository_value: str, snapshot_value: str, force: bool) -> int:
    if not force:
        raise SnapshotInputError(
            "Import overwrites files in the working tree; use --force to confirm."
        )

    repository = _resolve_git_repository(repository_value)
    snapshot_path = _absolute_path(snapshot_value)
    if not snapshot_path.exists() or not snapshot_path.is_file():
        raise SnapshotInputError(
            "Snapshot file does not exist or is not a regular file: {0}".format(snapshot_path)
        )

    try:
        archive = snapshot_path.read_bytes()
        result = import_working_tree_snapshot(repository, archive)
    except (OSError, ValueError) as exc:
        raise SnapshotWriteError("Failed to import snapshot: {0}".format(exc)) from exc

    print("Snapshot imported: {0}".format(snapshot_path))
    print("Repository: {0}".format(repository))
    print("Written files: {0}".format(result.get("written_files", 0)))
    print("Deleted files: {0}".format(result.get("deleted_files", 0)))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.export_repo is not None:
        try:
            return export_snapshot(args.export_repo, args.output, args.force)
        except SnapshotInputError as exc:
            print("Error: {0}".format(exc), file=sys.stderr)
            return 2
        except SnapshotWriteError as exc:
            print("Error: {0}".format(exc), file=sys.stderr)
            return 1

    if args.import_snapshot is not None:
        if args.output is not None:
            print("Error: --output can only be used with --export.", file=sys.stderr)
            return 2
        try:
            repository_value, snapshot_value = args.import_snapshot
            return import_snapshot(repository_value, snapshot_value, args.force)
        except SnapshotInputError as exc:
            print("Error: {0}".format(exc), file=sys.stderr)
            return 2
        except SnapshotWriteError as exc:
            print("Error: {0}".format(exc), file=sys.stderr)
            return 1

    if args.output is not None or args.force:
        print("Error: --output and --force require --export or --import.", file=sys.stderr)
        return 2

    from .webapp import serve

    serve(args)
    return 0
