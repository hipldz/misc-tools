import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import List

GIT_TIMEOUT_SECONDS = 30


def run_git(repo_path: Path, args: List[str]) -> dict:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        return {
            "success": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {"success": False, "stdout": exc.stdout or "", "stderr": "Git command timed out.", "returncode": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Git executable was not found.", "returncode": -1}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1}


def parse_porcelain_line(line: str) -> dict:
    index_status = line[:1]
    worktree_status = line[1:2]
    file_path = line[3:].strip()
    if " -> " in file_path:
        file_path = file_path.split(" -> ", 1)[1].strip()
    return {"path": file_path, "index_status": index_status, "worktree_status": worktree_status}


def normalize_status(code: str, fallback: str = "M") -> str:
    if code in {"M", "A", "D", "R", "C", "T", "U"}:
        return code
    if code == "?":
        return "U"
    return fallback


def build_file_entry(path: str, status: str) -> dict:
    return {"path": path, "name": PurePosixPath(path).name or path, "status": status}


def chunked(items: List[str], size: int = 100) -> List[List[str]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def get_repo_status(repo_id: str, repo_path: Path) -> dict:
    base = {
        "id": repo_id,
        "name": repo_path.name,
        "path": str(repo_path),
        "branch": "",
        "local_branches": [],
        "remote_branches": [],
        "dirty": False,
        "untracked": False,
        "changed_files": 0,
        "untracked_files": 0,
        "staged_files": [],
        "unstaged_files": [],
        "untracked_list": [],
        "has_remote": False,
        "ahead": 0,
        "behind": 0,
        "status": "error",
        "message": "",
    }
    status_result = run_git(repo_path, ["status", "--porcelain"])
    if not status_result["success"]:
        base["message"] = status_result["stderr"] or status_result["stdout"] or "Failed to read git status."
        return base
    branch_result = run_git(repo_path, ["branch", "--show-current"])
    base["branch"] = branch_result["stdout"].strip() or "(detached)" if branch_result["success"] else "(unknown)"
    local_branches_result = run_git(repo_path, ["for-each-ref", "--format=%(refname:short)", "refs/heads"])
    if local_branches_result["success"]:
        base["local_branches"] = [branch.strip() for branch in local_branches_result["stdout"].splitlines() if branch.strip()]
    remote_branches_result = run_git(repo_path, ["for-each-ref", "--format=%(refname:short)", "refs/remotes"])
    if remote_branches_result["success"]:
        base["remote_branches"] = [branch.strip() for branch in remote_branches_result["stdout"].splitlines() if branch.strip() and "/" in branch.strip() and not branch.strip().endswith("/HEAD")]
    lines = [line for line in status_result["stdout"].splitlines() if line]
    parsed_lines = [parse_porcelain_line(line) for line in lines]
    base["dirty"] = len(lines) > 0
    base["untracked"] = any(line.startswith("??") for line in lines)
    base["staged_files"] = [build_file_entry(item["path"], normalize_status(item["index_status"])) for item in parsed_lines if item["index_status"] not in (" ", "?")]
    base["unstaged_files"] = [build_file_entry(item["path"], normalize_status(item["worktree_status"])) for item in parsed_lines if item["worktree_status"] not in (" ", "?")]
    base["untracked_list"] = [build_file_entry(item["path"], "U") for item in parsed_lines if item["index_status"] == "?" and item["worktree_status"] == "?"]
    base["changed_files"] = len({item["path"] for item in base["staged_files"]} | {item["path"] for item in base["unstaged_files"]})
    base["untracked_files"] = len(base["untracked_list"])
    upstream_result = run_git(repo_path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not upstream_result["success"]:
        base["status"] = "no_remote"
        base["message"] = "No upstream remote configured."
        return base
    base["has_remote"] = True
    count_result = run_git(repo_path, ["rev-list", "--left-right", "--count", "HEAD...@{u}"])
    if not count_result["success"]:
        base["status"] = "error"
        base["message"] = count_result["stderr"] or count_result["stdout"] or "Failed to compare with upstream."
        return base
    parts = count_result["stdout"].strip().split()
    if len(parts) == 2:
        base["ahead"] = int(parts[0])
        base["behind"] = int(parts[1])
    if base["dirty"]:
        base["status"] = "dirty"
        base["message"] = "Current repository has modified files.(仓库存在改动.)"
    elif base["ahead"] > 0 and base["behind"] > 0:
        base["status"] = "diverged"
        base["message"] = "Local branch is not synchronized with the remote branch.(本地分支和远程分支不一致.)"
    elif base["ahead"] > 0:
        base["status"] = "ahead"
        base["message"] = "The local branch is ahead of the remote branch.(本地分支领先远程分支.)"
    elif base["behind"] > 0:
        base["status"] = "behind"
        base["message"] = "The local branch is behind of the remote branch.(本地分支落后远程分支)."
    else:
        base["status"] = "clean"
        base["message"] = "No update.(状态一致, 无需更新.)"
    return base


def commit_repo(repo_path: Path, message: str) -> dict:
    message = message.strip()
    if not message:
        return {"success": False, "stdout": "", "stderr": "Commit message is required.", "returncode": 1}
    status_result = run_git(repo_path, ["status", "--porcelain"])
    if not status_result["success"]:
        return status_result
    if not status_result["stdout"].strip():
        return {"success": False, "stdout": "", "stderr": "There are no changes to commit.", "returncode": 1}
    add_result = run_git(repo_path, ["add", "."])
    if not add_result["success"]:
        return add_result
    return run_git(repo_path, ["commit", "-m", message])


def checkout_repo(repo_path: Path, branch: str) -> dict:
    branch = branch.strip()
    if not branch:
        return {"success": False, "stdout": "", "stderr": "Branch name is required.", "returncode": 1}
    local_branches_result = run_git(repo_path, ["for-each-ref", "--format=%(refname:short)", "refs/heads"])
    local_branches = {item.strip() for item in local_branches_result["stdout"].splitlines() if item.strip()} if local_branches_result["success"] else set()
    if branch in local_branches:
        return run_git(repo_path, ["checkout", branch])
    remote_branches_result = run_git(repo_path, ["for-each-ref", "--format=%(refname:short)", "refs/remotes"])
    remote_branches = {item.strip() for item in remote_branches_result["stdout"].splitlines() if item.strip() and "/" in item.strip() and not item.strip().endswith("/HEAD")} if remote_branches_result["success"] else set()
    if branch in remote_branches:
        local_name = branch.split("/", 1)[1]
        if local_name in local_branches:
            return run_git(repo_path, ["checkout", local_name])
        return run_git(repo_path, ["checkout", "--track", branch])
    return run_git(repo_path, ["checkout", branch])


def discard_repo_changes(repo_path: Path) -> dict:
    reset_result = run_git(repo_path, ["reset", "--hard", "HEAD"])
    if not reset_result["success"]:
        return reset_result
    clean_result = run_git(repo_path, ["clean", "-fd"])
    if not clean_result["success"]:
        return clean_result
    return {"success": True, "stdout": "\n".join(filter(None, [reset_result["stdout"], clean_result["stdout"]])), "stderr": "\n".join(filter(None, [reset_result["stderr"], clean_result["stderr"]])), "returncode": 0}


def resolve_repo_file(repo_path: Path, file_path: str) -> Path:
    if not file_path.strip():
        raise ValueError("File path is required.")
    target = (repo_path / file_path).resolve()
    if repo_path.resolve() not in target.parents and target != repo_path.resolve():
        raise ValueError("File path is outside the repository.")
    return target


def preview_repo_file(repo_path: Path, file_path: str, scope: str) -> dict:
    if scope == "staged":
        result = run_git(repo_path, ["diff", "--cached", "--", file_path])
        return {"success": result["success"], "mode": "diff", "content": result["stdout"], "stderr": result["stderr"]}
    if scope == "unstaged":
        result = run_git(repo_path, ["diff", "--", file_path])
        return {"success": result["success"], "mode": "diff", "content": result["stdout"], "stderr": result["stderr"]}
    if scope == "untracked":
        target = resolve_repo_file(repo_path, file_path)
        if not target.exists():
            return {"success": False, "mode": "text", "content": "", "stderr": "File does not exist."}
        if target.is_dir():
            return {"success": False, "mode": "text", "content": "", "stderr": "Directories cannot be previewed."}
        return {"success": True, "mode": "text", "content": target.read_text(encoding="utf-8", errors="replace"), "stderr": ""}
    return {"success": False, "mode": "text", "content": "", "stderr": "Unsupported preview scope."}


def stage_file(repo_path: Path, file_path: str) -> dict:
    return run_git(repo_path, ["add", "--", file_path])


def unstage_file(repo_path: Path, file_path: str) -> dict:
    result = run_git(repo_path, ["restore", "--staged", "--", file_path])
    if result["success"]:
        return result
    return run_git(repo_path, ["reset", "HEAD", "--", file_path])


def discard_file(repo_path: Path, file_path: str) -> dict:
    result = run_git(repo_path, ["restore", "--", file_path])
    if result["success"]:
        return result
    return run_git(repo_path, ["checkout", "--", file_path])


def delete_untracked_file(repo_path: Path, file_path: str) -> dict:
    try:
        target = resolve_repo_file(repo_path, file_path)
        if not target.exists():
            return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "returncode": 1}


def ignore_untracked_file(repo_path: Path, file_path: str) -> dict:
    try:
        exclude_path = repo_path / ".git" / "info" / "exclude"
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude_path.read_text(encoding="utf-8", errors="replace") if exclude_path.exists() else ""
        entries = {line.strip() for line in existing.splitlines() if line.strip()}
        if file_path not in entries:
            prefix = "\n" if existing and not existing.endswith("\n") else ""
            exclude_path.write_text(f"{existing}{prefix}{file_path}\n", encoding="utf-8")
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "returncode": 1}


def apply_file_action(repo_path: Path, action: str, file_path: str) -> dict:
    if action in {"stage", "add"}:
        return stage_file(repo_path, file_path)
    if action == "unstage":
        return unstage_file(repo_path, file_path)
    if action == "discard":
        return discard_file(repo_path, file_path)
    if action == "delete":
        return delete_untracked_file(repo_path, file_path)
    if action == "ignore":
        return ignore_untracked_file(repo_path, file_path)
    if action == "open":
        try:
            target = resolve_repo_file(repo_path, file_path)
            if sys.platform.startswith("win"):
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
        except Exception as exc:
            return {"success": False, "stdout": "", "stderr": str(exc), "returncode": 1}
    return {"success": False, "stdout": "", "stderr": f"Unsupported file action: {action}", "returncode": 1}


def apply_bulk_file_action(repo_path: Path, scope: str, action: str, repo_status: dict) -> dict:
    if scope == "staged" and action == "unstage_all":
        paths = [item["path"] for item in repo_status.get("staged_files", [])]
    elif scope == "unstaged" and action in {"stage_all", "discard_all"}:
        paths = [item["path"] for item in repo_status.get("unstaged_files", [])]
    elif scope == "untracked" and action in {"add_all", "delete_all"}:
        paths = [item["path"] for item in repo_status.get("untracked_list", [])]
    else:
        return {"success": False, "stdout": "", "stderr": "Unsupported bulk action.", "returncode": 1}
    if not paths:
        return {"success": True, "stdout": "", "stderr": "", "returncode": 0}
    results = []
    for chunk in chunked(paths):
        if action in {"stage_all", "add_all"}:
            result = run_git(repo_path, ["add", "--", *chunk])
        elif action == "unstage_all":
            result = run_git(repo_path, ["restore", "--staged", "--", *chunk])
            if not result["success"]:
                result = run_git(repo_path, ["reset", "HEAD", "--", *chunk])
        elif action == "discard_all":
            result = run_git(repo_path, ["restore", "--", *chunk])
            if not result["success"]:
                result = run_git(repo_path, ["checkout", "--", *chunk])
        else:
            for item in chunk:
                item_result = delete_untracked_file(repo_path, item)
                results.append(item_result)
                if not item_result["success"]:
                    return item_result
            continue
        results.append(result)
        if not result["success"]:
            return result
    return {"success": True, "stdout": "\n".join(filter(None, [result["stdout"] for result in results])), "stderr": "\n".join(filter(None, [result["stderr"] for result in results])), "returncode": 0}


def push_origin_main(repo_path: Path) -> dict:
    return run_git(repo_path, ["push", "origin", "main"])
