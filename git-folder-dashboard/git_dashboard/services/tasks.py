"""Bounded background refresh jobs with incremental, pollable results."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

from .git import timestamp
from .workspace import WorkspaceChanged


class TaskRunner:
    def __init__(self, workspace, workers=3):
        self.workspace = workspace
        self._lock = threading.RLock()
        self._tasks = {}
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._closed = threading.Event()
        self._coordinators = []

    def snapshot(self):
        with self._lock:
            history = list(self._tasks.values())[::-1]
            return copy.deepcopy([task for task in history if task["status"] == "running"] +
                                 [task for task in history if task["status"] != "running"][:20])

    def start(self, fetch_remote=False, repo_ids=None):
        snapshot = self.workspace.snapshot()
        generation = snapshot["generation"]
        repos = snapshot["repos"]
        ids = set(repo_ids) if repo_ids is not None else {repo["id"] for repo in repos}
        available = {repo["id"] for repo in repos}
        if not ids.issubset(available):
            raise LookupError("Repository is no longer in this workspace.")
        with self._lock:
            if self._closed.is_set():
                raise WorkspaceChanged()
            for task in self._tasks.values():
                if (task["status"] == "running" and task["generation"] == generation
                        and (task["fetch_remote"] or not fetch_remote)
                        and ids.issubset(set(task["repo_ids"]))
                        and not any(item["repo_id"] in ids and item["status"] == "error" for item in task["items"])):
                    return copy.deepcopy(task)
            task_id = uuid4().hex
            task = {"id": task_id, "generation": generation, "status": "running", "revision": 0,
                    "fetch_remote": fetch_remote, "total": len(ids), "completed": 0, "failed": 0,
                    "started_at": timestamp(), "finished_at": None, "repo_ids": sorted(ids),
                    "items": [{"repo_id": repo["id"], "name": repo["name"], "status": "queued", "error": ""}
                              for repo in repos if repo["id"] in ids]}
            self._tasks[task_id] = task
            # Keep running jobs and a bounded history.
            for old_id in list(self._tasks)[:-20]:
                if self._tasks[old_id]["status"] != "running":
                    del self._tasks[old_id]
            coordinator = threading.Thread(target=self._run, args=(task_id,), daemon=True)
            self._coordinators = [thread for thread in self._coordinators if thread.is_alive()] + [coordinator]
            coordinator.start()
            return copy.deepcopy(task)

    def _item(self, task_id, repo_id, **updates):
        with self._lock:
            for item in self._tasks[task_id]["items"]:
                if item["repo_id"] == repo_id:
                    item.update(updates)
                    self._tasks[task_id]["revision"] += 1
                    return

    def _local(self, task_id, repo_id, generation, fetch_remote):
        if self._closed.is_set():
            raise WorkspaceChanged()
        self._item(task_id, repo_id, status="checking")
        repo = self.workspace.refresh(repo_id, generation)
        error = repo.get("message", "") if repo.get("status") == "error" else ""
        if not error and fetch_remote and repo.get("has_remote"):
            self._item(task_id, repo_id, status="queued")
            return True
        self._finish(task_id, repo_id, error)
        return False

    def _fetch(self, task_id, repo_id, generation):
        if self._closed.is_set():
            raise WorkspaceChanged()
        repo, result = self.workspace.fetch(
            repo_id, generation, lambda status: self._item(task_id, repo_id, status=status), refresh_first=False)
        error = "" if result["success"] else result.get("stderr") or "Fetch failed."
        self._finish(task_id, repo_id, error)

    def _finish(self, task_id, repo_id, error="", superseded=False):
        self._item(task_id, repo_id, status="superseded" if superseded else "error" if error else "success", error=error)
        with self._lock:
            self._tasks[task_id]["completed"] += 1
            self._tasks[task_id]["failed"] += int(bool(error))
            self._tasks[task_id]["revision"] += 1

    def _collect(self, task, futures, fetch_ids=None):
        for future in as_completed(futures):
            repo_id = futures[future]
            try:
                if future.result() and fetch_ids is not None:
                    fetch_ids.append(repo_id)
            except WorkspaceChanged:
                self._finish(task["id"], repo_id, superseded=True)
            except Exception as exc:
                self.workspace.record_error(repo_id, task["generation"], str(exc))
                self._finish(task["id"], repo_id, str(exc))

    def _run(self, task_id):
        with self._lock:
            task = copy.deepcopy(self._tasks[task_id])
        try:
            # Finish local inspection before spending workers on network I/O.
            futures = {}
            for repo_id in task["repo_ids"]:
                future = self._executor.submit(self._local, task_id, repo_id, task["generation"], task["fetch_remote"])
                futures[future] = repo_id
            fetch_ids = []
            self._collect(task, futures, fetch_ids)
            futures = {self._executor.submit(self._fetch, task_id, repo_id, task["generation"]): repo_id
                       for repo_id in fetch_ids}
            self._collect(task, futures)
        finally:
            with self._lock:
                self._tasks[task_id].update(
                    status="completed" if task["generation"] == self.workspace.generation else "superseded",
                    finished_at=timestamp())
                self._tasks[task_id]["revision"] += 1

    def start_periodic(self, interval):
        if not interval:
            return

        def loop():
            while not self._closed.wait(interval):
                if self.workspace.path:
                    try:
                        self.start(fetch_remote=True)
                    except WorkspaceChanged:
                        return

        threading.Thread(target=loop, daemon=True).start()

    def close(self):
        with self._lock:
            self._closed.set()
            coordinators = list(self._coordinators)
        for coordinator in coordinators:
            coordinator.join()
        self._executor.shutdown(wait=True)
