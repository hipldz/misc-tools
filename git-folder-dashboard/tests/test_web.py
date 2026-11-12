import base64
import tempfile
import unittest
from pathlib import Path

from git_dashboard.web import create_app
from tests.helpers import git, repository, cleanup_fixture, wait_tasks


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="gfd-web-")
        self.repo = repository(self.temp)
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["tasks"].close()
        cleanup_fixture(self.temp)

    def select(self):
        response = self.client.post("/api/workspace", json={"path": self.temp, "fetch_remote": False})
        self.assertEqual(response.status_code, 202)
        repo_id = response.get_json()["repos"][0]["id"]
        wait_tasks(self.app.extensions["tasks"])
        return repo_id

    def test_workspace_validation_and_incremental_state(self):
        response = self.client.post("/api/workspace", json={"path": ""})
        self.assertEqual(response.status_code, 400)
        repo_id = self.select()
        state = self.client.get("/api/state")
        self.assertEqual(state.headers["Cache-Control"], "no-store")
        self.assertEqual(state.get_json()["repos"][0]["id"], repo_id)
        self.assertTrue(state.get_json()["instance_id"])
        self.assertFalse(state.get_json()["repos"][0]["pending"])

    def test_api_commit_obeys_index_and_returns_failure_state(self):
        repo_id = self.select()
        (self.repo / "app.py").write_text("working tree", encoding="utf-8")
        response = self.client.post("/api/repos/{0}/commit".format(repo_id), json={"message": "No index"})
        self.assertFalse(response.get_json()["success"])
        self.assertTrue(response.get_json()["repo"]["dirty"])
        self.client.post("/api/repos/{0}/files/action".format(repo_id), json={"path": "app.py", "action": "stage"})
        (self.repo / "README.md").write_text("do not commit", encoding="utf-8")
        response = self.client.post("/api/repos/{0}/commit".format(repo_id), json={"message": "Only staged"})
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(git(self.repo, "show", "HEAD:README.md"), "# Example project\n")

    def test_errors_are_json_and_missing_repo_is_not_silently_accepted(self):
        self.assertEqual(self.client.post("/api/repos/missing/refresh").status_code, 404)
        self.assertEqual(self.client.post("/api/repos/missing/fetch").status_code, 404)
        self.assertEqual(self.client.get("/api/does-not-exist").status_code, 404)

    def test_subpath_templates_modules_authentication_and_redirect(self):
        self.app.extensions["tasks"].close()
        self.app = create_app({"TESTING": True, "BASE_PATH": "/git", "AUTHORIZATION": ("user", "secret:password")})
        client = self.app.test_client()
        self.assertEqual(client.get("/git/api/state").status_code, 401)
        headers = {"Authorization": "Basic " + base64.b64encode(b"user:secret:password").decode("ascii")}
        page = client.get("/git/", headers=headers)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'/git/static/js/app.js', page.data)
        with client.get("/git/static/js/ui.js", headers=headers) as resource:
            self.assertEqual(resource.status_code, 200)
        redirect = client.get("/git?test=1", headers=headers)
        self.assertEqual(redirect.headers["Location"], "/git/?test=1")
        self.assertEqual(client.get("/", headers=headers).status_code, 404)

    def test_snapshot_download_and_import(self):
        repo_id = self.select()
        (self.repo / "README.md").write_text("snapshot", encoding="utf-8")
        archive = self.client.post("/api/repos/{0}/export-state".format(repo_id))
        self.assertEqual(archive.status_code, 200)
        self.assertIn("attachment", archive.headers["Content-Disposition"])

    def test_page_has_offline_assets_and_no_embedded_workspace_script(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'type="module"', response.data)
        with self.client.get("/static/css/app.css") as resource:
            self.assertEqual(resource.status_code, 200)
