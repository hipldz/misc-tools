"""Thread-safe workspace data and per-repository operation locks."""

import copy
import hashlib
import os
import threading
from pathlib import Path

from .git import get_repo_status, run_git, timestamp


class WorkspaceChanged(Exception):
    pass


class Workspace:
    def __init__(self):
        self._lock = threading.RLock()
        self._repo_locks = {}
        self._repos = {}
        self.path = ""
        self.generation = 0
        self.non_git_dirs = []

    def select(self, value, preserve_generation=False):
        if not str(value).strip():
            raise ValueError("Workspace path is required.")
        parent = Path(value).expanduser().resolve()
        if not parent.is_dir():
            raise ValueError("Path does not exist or is not a directory.")
        children = sorted(parent.iterdir(), key=lambda item: item.name.casefold())
        with self._lock:
            repos, non_git = {}, []
            for child in children:
                if child.name == ".git" or not child.is_dir():
                    continue
                if not (child / ".git").exists():
                    non_git.append({"name": child.name, "path": str(child)})
                    continue
                identity = os.path.normcase(str(child.resolve()))
                repo_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
                previous = self._repos.get(repo_id, {})
                repos[repo_id] = dict(previous, id=repo_id, name=child.name, path=str(child),
                                      pending=not bool(previous.get("checked_at")))
                self._repo_locks.setdefault(repo_id, threading.RLock())
            if not preserve_generation or self.path != str(parent) or set(repos) != set(self._repos):
                self.generation += 1
            self.path = str(parent)
            self._repos = repos
            self.non_git_dirs = non_git
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return copy.deepcopy({"path": self.path, "generation": self.generation,
                                  "repos": list(self._repos.values()), "non_git_dirs": self.non_git_dirs})

    def require(self, repo_id, generation=None):
        with self._lock:
            if generation is not None and generation != self.generation:
                raise WorkspaceChanged()
            if repo_id not in self._repos:
                raise LookupError("Repository is no longer in this workspace. Scan again.")
            path = Path(self._repos[repo_id]["path"])
        if not path.is_dir():
            raise LookupError("Repository folder no longer exists.")
        return path

    def repo_lock(self, repo_id):
        with self._lock:
            if repo_id not in self._repos:
                raise LookupError("Repository is no longer in this workspace. Scan again.")
            return self._repo_locks[repo_id]

    def save(self, repo, generation, **metadata):
        with self._lock:
            if generation != self.generation or repo["id"] not in self._repos:
                raise WorkspaceChanged()
            previous = self._repos[repo["id"]]
            merged = dict(previous, **repo)
            merged.update(metadata)
            merged["revision"] = previous.get("revision", 0) + 1
            merged["pending"] = False
            self._repos[repo["id"]] = merged
            return copy.deepcopy(merged)

    def record_error(self, repo_id, generation, message):
        with self._lock:
            if generation == self.generation and repo_id in self._repos:
                self.save(dict(self._repos[repo_id], status="error", message=message), generation)

    def refresh(self, repo_id, generation=None):
        with self.repo_lock(repo_id):
            generation = self.generation if generation is None else generation
            path = self.require(repo_id, generation)
            return self.save(get_repo_status(repo_id, path), generation)

    def fetch(self, repo_id, generation, progress=None, refresh_first=True):
        with self.repo_lock(repo_id):
            if refresh_first:
                repo = self.refresh(repo_id, generation)
            else:
                self.require(repo_id, generation)
                with self._lock:
                    repo = copy.deepcopy(self._repos[repo_id])
            if repo["status"] == "error":
                return repo, {"success": False, "stderr": repo["message"]}
            if not repo["has_remote"]:
                return repo, {"success": True, "stderr": "", "skipped": True}
            if progress:
                progress("fetching")
            result = run_git(self.require(repo_id, generation), ["fetch", "--all", "--prune"])
            metadata = {"fetch_error": "" if result["success"] else result["stderr"] or result["stdout"],
                        "fetch_attempted_at": timestamp()}
            if result["success"]:
                metadata["fetched_at"] = timestamp()
            latest = get_repo_status(repo_id, self.require(repo_id, generation))
            return self.save(latest, generation, **metadata), result

    def mutate(self, repo_id, operation):
        with self.repo_lock(repo_id):
            generation = self.generation
            result = operation(self.require(repo_id, generation))
            repo = self.refresh(repo_id, generation)
            return result, repo
