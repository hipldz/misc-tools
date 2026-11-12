import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from git_dashboard.services.tasks import TaskRunner
from git_dashboard.services.workspace import Workspace, WorkspaceChanged
from tests.helpers import git, repository, cleanup_fixture, wait_tasks


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="gfd-workspace-")
        self.repo = repository(self.temp)
        self.workspace = Workspace()
        self.workspace.select(self.temp)
        self.repo_id = self.workspace.snapshot()["repos"][0]["id"]
        self.runner = TaskRunner(self.workspace, workers=2)

    def tearDown(self):
        self.runner.close()
        cleanup_fixture(self.temp)

    def test_rescan_keeps_identity_and_last_successful_fetch(self):
        self.workspace.refresh(self.repo_id)
        generation = self.workspace.generation
        repo = self.workspace.snapshot()["repos"][0]
        self.workspace.save(repo, generation, fetched_at="2026-01-01T00:00:00+00:00")
        second = self.workspace.select(self.temp)
        self.assertEqual(second["repos"][0]["id"], self.repo_id)
        self.assertEqual(second["repos"][0]["fetched_at"], "2026-01-01T00:00:00+00:00")
        with self.assertRaises(WorkspaceChanged):
            self.workspace.save(repo, generation)

    def test_failed_fetch_keeps_local_changes_and_does_not_claim_remote_freshness(self):
        git(self.repo, "remote", "add", "origin", str(Path(self.temp) / "missing.git"))
        (self.repo / "app.py").write_text("dirty", encoding="utf-8")
        self.runner.start(fetch_remote=True)
        task = wait_tasks(self.runner)[0]
        repo = self.workspace.snapshot()["repos"][0]
        self.assertTrue(repo["dirty"])
        self.assertTrue(repo["fetch_error"])
        self.assertFalse(repo.get("fetched_at"))
        self.assertEqual(task["failed"], 1)
        self.assertEqual(task["completed"], 1)
        self.assertEqual(task["items"][0]["status"], "error")

    def test_fetch_without_remote_is_a_successful_local_check(self):
        self.runner.start(fetch_remote=True)
        self.assertEqual(wait_tasks(self.runner)[0]["failed"], 0)
        repo = self.workspace.snapshot()["repos"][0]
        self.assertFalse(repo["has_remote"])
        self.assertFalse(repo.get("fetched_at"))

    def test_worktree_git_file_is_discovered(self):
        worktree = Path(self.temp) / "linked"
        git(self.repo, "worktree", "add", "-b", "feature", str(worktree))
        self.workspace.select(self.temp)
        self.assertEqual(len(self.workspace.snapshot()["repos"]), 2)

    def test_manual_discovery_preserves_generation_until_membership_changes(self):
        generation = self.workspace.generation
        self.workspace.select(self.temp, preserve_generation=True)
        self.assertEqual(self.workspace.generation, generation)
        repository(self.temp, "new-repo")
        self.workspace.select(self.temp, preserve_generation=True)
        self.assertGreater(self.workspace.generation, generation)

    def test_all_local_checks_finish_before_network_fetch_starts(self):
        checked = []
        calls = []

        def inspect(repo_id, generation=None):
            checked.append(repo_id)
            return {"status": "clean", "has_remote": True}

        def fetch(repo_id, generation, progress, refresh_first=True):
            calls.append(len(checked))
            return {}, {"success": True}

        repository(self.temp, "another")
        self.workspace.select(self.temp)
        with patch.object(self.workspace, "refresh", side_effect=inspect), patch.object(self.workspace, "fetch", side_effect=fetch):
            self.runner.start(fetch_remote=True)
            wait_tasks(self.runner)
        self.assertEqual(calls, [2, 2])

    def test_deleted_repository_is_an_error_instead_of_stuck_pending(self):
        cleanup_fixture(self.repo)
        self.runner.start()
        self.assertEqual(wait_tasks(self.runner)[0]["failed"], 1)
        repo = self.workspace.snapshot()["repos"][0]
        self.assertEqual(repo["status"], "error")
        self.assertFalse(repo["pending"])

    def test_concurrency_is_bounded_and_duplicate_jobs_are_reused(self):
        for index in range(3):
            path = Path(self.temp) / ("repo" + str(index))
            (path / ".git").mkdir(parents=True)
        self.workspace.select(self.temp)
        active = [0, 0]
        gate = threading.Event()
        started = threading.Event()
        lock = threading.Lock()

        def inspect(repo_id, generation=None):
            with lock:
                active[0] += 1
                active[1] = max(active)
                started.set()
            gate.wait(3)
            with lock:
                active[0] -= 1
            return {"status": "clean"}

        with patch.object(self.workspace, "refresh", side_effect=inspect):
            first = self.runner.start()
            self.assertTrue(started.wait(2))
            second = self.runner.start()
            self.assertEqual(first["id"], second["id"])
            gate.set()
            task = wait_tasks(self.runner)[0]
            self.assertEqual(task["completed"], 4)
            self.assertLessEqual(active[1], 2)

    def test_same_repository_mutations_serialize(self):
        active = [0, 0]
        lock = threading.Lock()

        def operation(path):
            with lock:
                active[0] += 1
                active[1] = max(active)
            time.sleep(.04)
            with lock:
                active[0] -= 1
            return {"success": True}

        with patch("git_dashboard.services.workspace.get_repo_status", return_value={"id": self.repo_id, "status": "clean"}):
            workers = [threading.Thread(target=self.workspace.mutate, args=(self.repo_id, operation)) for _ in range(3)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
        self.assertEqual(active[1], 1)

    def test_workspace_switch_rejects_in_flight_result(self):
        entered, gate = threading.Event(), threading.Event()

        def inspect(repo_id, path):
            entered.set()
            gate.wait(3)
            return {"id": repo_id, "status": "clean"}

        with patch("git_dashboard.services.workspace.get_repo_status", side_effect=inspect):
            self.runner.start()
            self.assertTrue(entered.wait(2))
            other = Path(self.temp) / "other"
            other.mkdir()
            self.workspace.select(other)
            gate.set()
            self.assertEqual(wait_tasks(self.runner)[0]["status"], "superseded")
        self.assertEqual(self.workspace.snapshot()["repos"], [])

    def test_periodic_fetch_uses_server_startup_interval(self):
        triggered = threading.Event()
        with patch.object(self.runner, "start", side_effect=lambda **kwargs: triggered.set()):
            self.runner.start_periodic(.025)
            self.assertTrue(triggered.wait(2))
            self.runner.close()

    def test_shutdown_drains_in_flight_check_without_starting_network_work(self):
        started, gate = threading.Event(), threading.Event()

        def inspect(repo_id, generation=None):
            started.set()
            gate.wait(3)
            return {"status": "clean", "has_remote": True}

        with patch.object(self.workspace, "refresh", side_effect=inspect), patch.object(self.workspace, "fetch") as fetch:
            self.runner.start(fetch_remote=True)
            self.assertTrue(started.wait(2))
            closer = threading.Thread(target=self.runner.close)
            closer.start()
            self.assertTrue(self.runner._closed.wait(2))
            gate.set()
            closer.join(5)
            self.assertFalse(closer.is_alive())
            fetch.assert_not_called()
        self.assertEqual(self.runner.snapshot()[0]["completed"], 1)
