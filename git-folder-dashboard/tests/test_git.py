import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from git_dashboard.services.git import (apply_bulk_file_action, apply_file_action, commit_repo, get_repo_status,
                                        preview_repo_file, resolve_repo_file)
from git_dashboard.services.snapshots import export_working_tree_snapshot, import_working_tree_snapshot
from tests.helpers import git, repository, cleanup_fixture


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="gfd-git-")
        self.repo = repository(self.temp)

    def tearDown(self):
        cleanup_fixture(self.temp)

    def test_commit_preserves_unstaged_contents_and_untracked_files(self):
        file = self.repo / "app.py"
        file.write_text("staged version\n", encoding="utf-8")
        git(self.repo, "add", "app.py")
        file.write_text("newer working tree\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("not staged", encoding="utf-8")
        result = commit_repo(self.repo, "Commit only selected contents")
        self.assertTrue(result["success"], result)
        self.assertEqual(git(self.repo, "show", "HEAD:app.py"), "staged version\n")
        self.assertEqual(file.read_text(encoding="utf-8"), "newer working tree\n")
        status = get_repo_status("repo", self.repo)
        self.assertEqual(status["unstaged_files"][0]["path"], "app.py")
        self.assertEqual(status["untracked_list"][0]["path"], "new.txt")

    def test_no_staged_changes_does_not_create_commit(self):
        head = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "app.py").write_text("modified", encoding="utf-8")
        self.assertFalse(commit_repo(self.repo, "Should fail")["success"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)

    def test_explicit_stage_all_commit(self):
        (self.repo / "new.txt").write_text("new", encoding="utf-8")
        self.assertTrue(commit_repo(self.repo, "All", stage_all=True)["success"])
        self.assertEqual(git(self.repo, "show", "HEAD:new.txt"), "new")

    def test_bulk_stage_and_discard_keep_scopes_separate(self):
        (self.repo / "app.py").write_text("modified", encoding="utf-8")
        (self.repo / "untracked.txt").write_text("new", encoding="utf-8")
        status = get_repo_status("id", self.repo)
        self.assertTrue(apply_bulk_file_action(self.repo, "unstaged", "stage_all", status)["success"])
        status = get_repo_status("id", self.repo)
        self.assertEqual([entry["path"] for entry in status["staged_files"]], ["app.py"])
        self.assertEqual([entry["path"] for entry in status["untracked_list"]], ["untracked.txt"])
        (self.repo / "app.py").write_text("newer worktree", encoding="utf-8")
        status = get_repo_status("id", self.repo)
        self.assertTrue(apply_bulk_file_action(self.repo, "unstaged", "discard_all", status)["success"])
        self.assertEqual((self.repo / "app.py").read_text(encoding="utf-8"), "modified")

    def test_unicode_spaces_and_rename_paths_are_not_git_quoted(self):
        name = "中文 notes.txt"
        (self.repo / name).write_text("content", encoding="utf-8")
        status = get_repo_status("id", self.repo)
        self.assertIn(name, [file["path"] for file in status["untracked_list"]])
        git(self.repo, "mv", "README.md", "renamed notes.md")
        status = get_repo_status("id", self.repo)
        entry = next(file for file in status["staged_files"] if file["status"] == "R")
        self.assertEqual(entry["path"], "renamed notes.md")
        self.assertEqual(entry["original_path"], "README.md")

    def test_snapshot_round_trip_with_unicode_binary_and_deletion(self):
        (self.repo / "中文 notes.txt").write_bytes(b"\x00\x01payload")
        (self.repo / "README.md").unlink()
        snapshot = export_working_tree_snapshot(self.repo)
        (self.repo / "中文 notes.txt").write_bytes(b"changed")
        (self.repo / "README.md").write_text("recreated", encoding="utf-8")
        import_working_tree_snapshot(self.repo, snapshot)
        self.assertEqual((self.repo / "中文 notes.txt").read_bytes(), b"\x00\x01payload")
        self.assertFalse((self.repo / "README.md").exists())

    def test_cannot_overwrite_git_metadata_or_remove_tracked_file(self):
        for path in (".", "../outside", ".git/config"):
            with self.assertRaises(ValueError):
                resolve_repo_file(self.repo, path)
        self.assertFalse(apply_file_action(self.repo, "delete", "app.py")["success"])
        archive = io.BytesIO()
        with ZipFile(archive, "w") as zipfile:
            zipfile.writestr("manifest.json", json.dumps({"version": 1, "entries": [{"path": ".git/config", "kind": "deleted"}]}))
        with self.assertRaises(ValueError):
            import_working_tree_snapshot(self.repo, archive.getvalue())

    def test_unstage_before_first_commit(self):
        empty = Path(self.temp) / "empty"
        empty.mkdir()
        git(empty, "init", "--quiet")
        (empty / "one.txt").write_text("new", encoding="utf-8")
        git(empty, "add", ".")
        (empty / "one.txt").write_text("newer worktree", encoding="utf-8")
        self.assertTrue(apply_file_action(empty, "unstage", "one.txt")["success"])
        self.assertTrue((empty / "one.txt").exists())
        self.assertEqual((empty / "one.txt").read_text(encoding="utf-8"), "newer worktree")

    def test_snapshot_preserves_a_rename_as_a_working_tree_change(self):
        git(self.repo, "mv", "README.md", "renamed.md")
        snapshot = export_working_tree_snapshot(self.repo)
        git(self.repo, "reset", "--hard", "HEAD")
        import_working_tree_snapshot(self.repo, snapshot)
        self.assertFalse((self.repo / "README.md").exists())
        self.assertEqual((self.repo / "renamed.md").read_text(encoding="utf-8"), "# Example project\n")

    def test_binary_preview(self):
        (self.repo / "binary.bin").write_bytes(b"\x00binary")
        self.assertEqual(preview_repo_file(self.repo, "binary.bin", "untracked")["mode"], "binary")

    def test_snapshot_rename_with_recreated_source(self):
        git(self.repo, "mv", "README.md", "renamed.md")
        (self.repo / "README.md").write_text("recreated source", encoding="utf-8")
        snapshot = export_working_tree_snapshot(self.repo)
        git(self.repo, "reset", "--hard", "HEAD")
        import_working_tree_snapshot(self.repo, snapshot)
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "recreated source")
        self.assertEqual((self.repo / "renamed.md").read_text(encoding="utf-8"), "# Example project\n")

    def test_dirty_and_remote_counts_are_independent(self):
        remote = Path(self.temp) / "remote.git"
        remote.mkdir()
        git(remote, "init", "--bare", "--quiet")
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-u", "origin", "main")
        (self.repo / "README.md").write_text("new commit", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "--quiet", "-m", "Ahead")
        (self.repo / "app.py").write_text("dirty", encoding="utf-8")
        status = get_repo_status("id", self.repo)
        self.assertTrue(status["dirty"])
        self.assertEqual(status["ahead"], 1)
        self.assertTrue(status["has_upstream"])
