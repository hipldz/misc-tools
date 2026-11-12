"""Git operations. All paths and arguments are passed without a shell."""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

GIT_TIMEOUT_SECONDS = 30
GIT_PROXY = ""


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def failure(message):
    return {"success": False, "stdout": "", "stderr": message, "returncode": 1}


def run_git(repo_path, args):
    command = ["git", "--literal-pathspecs", "-c", "core.quotepath=false", "-c", "color.ui=false"]
    if GIT_PROXY:
        command += ["-c", "http.proxy=" + GIT_PROXY]
    environment = os.environ.copy()
    environment.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    try:
        completed = subprocess.run(
            command + list(args), cwd=str(repo_path), shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_SECONDS,
            env=environment,
        )
        return {"success": completed.returncode == 0, "stdout": completed.stdout,
                "stderr": completed.stderr, "returncode": completed.returncode}
    except subprocess.TimeoutExpired:
        return failure("Git command timed out after {0} seconds.".format(GIT_TIMEOUT_SECONDS))
    except FileNotFoundError:
        return failure("Git executable was not found. Install Git and add it to PATH.")
    except OSError as exc:
        return failure(str(exc))


def parse_porcelain_line(line):
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return {"path": path, "index_status": line[:1], "worktree_status": line[1:2]}


def read_status(repo_path):
    result = run_git(repo_path, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    entries = []
    records = iter(result["stdout"].split("\0"))
    for record in records:
        if not record:
            continue
        entry = {"path": record[3:], "index_status": record[:1], "worktree_status": record[1:2]}
        if "R" in record[:2] or "C" in record[:2]:
            entry["original_path"] = next(records, "")
        entries.append(entry)
    return result, entries


def build_file_entry(path, status, original_path=""):
    return {"path": path, "name": PurePosixPath(path).name, "status": status,
            "original_path": original_path}


def get_repo_status(repo_id, repo_path):
    base = {
        "id": repo_id, "name": repo_path.name, "path": str(repo_path), "branch": "",
        "local_branches": [], "remote_branches": [], "upstream": "", "remotes": [],
        "dirty": False, "untracked": False, "changed_files": 0, "untracked_files": 0,
        "staged_files": [], "unstaged_files": [], "untracked_list": [], "conflicts": [],
        "has_remote": False, "has_upstream": False, "ahead": 0, "behind": 0,
        "status": "clean", "message": "", "checked_at": timestamp(),
    }
    result, entries = read_status(repo_path)
    if not result["success"]:
        base.update(status="error", message=result["stderr"] or result["stdout"])
        return base
    branch = run_git(repo_path, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    base["branch"] = branch["stdout"].strip() or "(detached)"
    locals_result = run_git(repo_path, ["for-each-ref", "--format=%(refname:short)%00%(upstream:short)", "refs/heads"])
    remotes_result = run_git(repo_path, ["for-each-ref", "--format=%(refname:short)", "refs/remotes"])
    remote_names = run_git(repo_path, ["remote"])
    for metadata in (locals_result, remotes_result, remote_names):
        if not metadata["success"]:
            base.update(status="error", message=metadata["stderr"] or metadata["stdout"])
            return base
    for line in locals_result["stdout"].splitlines():
        name, _, upstream = line.partition("\0")
        base["local_branches"].append(name)
        if name == base["branch"]:
            base["upstream"] = upstream
    base["remote_branches"] = [name for name in remotes_result["stdout"].splitlines() if not name.endswith("/HEAD")]
    base["remotes"] = remote_names["stdout"].splitlines()
    base["has_remote"] = bool(base["remotes"])
    base["has_upstream"] = bool(base["upstream"])
    for entry in entries:
        index, tree, path = entry["index_status"], entry["worktree_status"], entry["path"]
        original = entry.get("original_path", "")
        if index + tree in ("DD", "AU", "UD", "UA", "DU", "AA", "UU"):
            base["conflicts"].append(path)
        if index not in (" ", "?"):
            base["staged_files"].append(build_file_entry(path, index, original))
        if tree not in (" ", "?"):
            base["unstaged_files"].append(build_file_entry(path, tree, original))
        if index == tree == "?":
            base["untracked_list"].append(build_file_entry(path, "?"))
    base["dirty"] = bool(entries)
    base["untracked"] = bool(base["untracked_list"])
    base["changed_files"] = len({entry["path"] for entry in base["staged_files"] + base["unstaged_files"]})
    base["untracked_files"] = len(base["untracked_list"])
    if base["has_upstream"]:
        counts = run_git(repo_path, ["rev-list", "--left-right", "--count", "HEAD...@{u}"])
        if not counts["success"]:
            base.update(status="error", message=counts["stderr"] or counts["stdout"])
            return base
        parts = counts["stdout"].split()
        if len(parts) == 2:
            base["ahead"], base["behind"] = map(int, parts)
    if base["conflicts"]:
        base["status"] = "conflict"
    elif base["dirty"]:
        base["status"] = "dirty"
    elif base["ahead"] and base["behind"]:
        base["status"] = "diverged"
    elif base["ahead"]:
        base["status"] = "ahead"
    elif base["behind"]:
        base["status"] = "behind"
    elif not base["has_upstream"]:
        base["status"] = "no_upstream"
    return base


def commit_repo(repo_path, message, stage_all=False):
    if not message.strip():
        return failure("Commit message is required.")
    if stage_all:
        result = run_git(repo_path, ["add", "--all"])
        if not result["success"]:
            return result
    staged = run_git(repo_path, ["diff", "--cached", "--name-only", "-z"])
    if not staged["success"]:
        return staged
    if not staged["stdout"]:
        return failure("No staged changes. Stage files before committing.")
    return run_git(repo_path, ["commit", "-m", message.strip()])


def checkout_repo(repo_path, branch):
    if not branch.strip() or branch.startswith("-"):
        return failure("A valid branch name is required.")
    local = run_git(repo_path, ["show-ref", "--verify", "--quiet", "refs/heads/" + branch])
    if local["success"]:
        return run_git(repo_path, ["checkout", branch])
    remote = run_git(repo_path, ["show-ref", "--verify", "--quiet", "refs/remotes/" + branch])
    if remote["success"]:
        name = branch.split("/", 1)[1]
        exists = run_git(repo_path, ["show-ref", "--verify", "--quiet", "refs/heads/" + name])
        return run_git(repo_path, ["checkout", name] if exists["success"] else ["checkout", "--track", branch])
    return failure("Branch no longer exists. Refresh the repository and try again.")


def resolve_repo_file(repo_path, file_path):
    if not file_path or not file_path.strip():
        raise ValueError("File path is required.")
    root = repo_path.resolve()
    target = (root / file_path).resolve()
    if root not in target.parents:
        raise ValueError("File path must be inside the repository.")
    if any(part.lower() == ".git" for part in target.relative_to(root).parts):
        raise ValueError("Git metadata cannot be modified by file operations.")
    return target


def preview_repo_file(repo_path, file_path, scope):
    target = resolve_repo_file(repo_path, file_path)
    if scope in ("staged", "unstaged"):
        args = ["diff", "--no-ext-diff", "--no-textconv"]
        if scope == "staged":
            args.append("--cached")
        result = run_git(repo_path, args + ["--", file_path])
        return {"success": result["success"], "mode": "diff", "content": result["stdout"], "stderr": result["stderr"]}
    if scope != "untracked":
        raise ValueError("Unsupported preview scope.")
    if not target.is_file():
        raise ValueError("File no longer exists or is a directory.")
    with target.open("rb") as handle:
        content = handle.read(2 * 1024 * 1024 + 1)
    if b"\0" in content[:8192]:
        return {"success": True, "mode": "binary", "content": "", "stderr": ""}
    return {"success": True, "mode": "text", "content": content[:2 * 1024 * 1024].decode("utf-8", errors="replace"),
            "truncated": len(content) > 2 * 1024 * 1024, "stderr": ""}


def open_path(target):
    if sys.platform.startswith("win"):
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def unstage_file(repo_path, file_path):
    head = run_git(repo_path, ["rev-parse", "--verify", "HEAD"])
    return run_git(repo_path, ["reset", "HEAD", "--", file_path] if head["success"] else ["rm", "--cached", "-f", "--", file_path])


def apply_file_action(repo_path, action, file_path):
    target = resolve_repo_file(repo_path, file_path)
    if action in ("stage", "add"):
        return run_git(repo_path, ["add", "--", file_path])
    if action == "unstage":
        return unstage_file(repo_path, file_path)
    if action == "discard":
        return run_git(repo_path, ["checkout", "--", file_path])
    if action == "open":
        open_path(target)
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    if action in ("delete", "ignore"):
        result, entries = read_status(repo_path)
        if not result["success"]:
            return result
        if not any(entry["path"] == file_path and entry["index_status"] == entry["worktree_status"] == "?" for entry in entries):
            return failure("Only untracked files can be deleted or ignored here.")
        if action == "delete":
            target.unlink()
        else:
            location = run_git(repo_path, ["rev-parse", "--git-path", "info/exclude"])
            if not location["success"]:
                return location
            exclude = Path(location["stdout"].strip())
            if not exclude.is_absolute():
                exclude = repo_path / exclude
            exclude.parent.mkdir(parents=True, exist_ok=True)
            existing = exclude.read_text(encoding="utf-8", errors="replace") if exclude.exists() else ""
            escaped = "".join("\\" + char if char in "\\*?[]!# " else char for char in file_path)
            rule = "/" + escaped
            if rule not in existing.splitlines():
                with exclude.open("a", encoding="utf-8") as handle:
                    handle.write(("\n" if existing and not existing.endswith("\n") else "") + rule + "\n")
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    return failure("Unsupported file action: " + action)


def apply_bulk_file_action(repo_path, scope, action, repo_status):
    supported = {("staged", "unstage_all"): ("staged_files", "unstage"),
                 ("unstaged", "stage_all"): ("unstaged_files", "stage"),
                 ("unstaged", "discard_all"): ("unstaged_files", "discard"),
                 ("untracked", "add_all"): ("untracked_list", "stage"),
                 ("untracked", "delete_all"): ("untracked_list", "delete")}
    if (scope, action) not in supported:
        return failure("Unsupported bulk action.")
    key, file_action = supported[(scope, action)]
    paths = [item["path"] for item in repo_status.get(key, [])]
    for path in paths:
        resolve_repo_file(repo_path, path)
    if file_action == "delete":
        status, entries = read_status(repo_path)
        if not status["success"]:
            return status
        untracked = {entry["path"] for entry in entries if entry["index_status"] == entry["worktree_status"] == "?"}
        if not set(paths).issubset(untracked):
            return failure("Some files are no longer untracked. Refresh before deleting.")
        for path in paths:
            resolve_repo_file(repo_path, path).unlink()
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    head = run_git(repo_path, ["rev-parse", "--verify", "HEAD"]) if file_action == "unstage" else None
    if file_action == "stage":
        args = ["add", "--"]
    elif file_action == "unstage":
        args = ["reset", "HEAD", "--"] if head["success"] else ["rm", "--cached", "-f", "--"]
    else:
        args = ["checkout", "--"]
    for offset in range(0, len(paths), 100):
        result = run_git(repo_path, args + paths[offset:offset + 100])
        if not result["success"]:
            return result
    return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
