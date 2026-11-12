import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from git_dashboard.cli import main, parse_args
from tests.helpers import repository, cleanup_fixture


class CliTests(unittest.TestCase):
    def test_startup_sync_options_and_legacy_aliases(self):
        args = parse_args(["--sync-interval", "300", "--git-proxy", "http://127.0.0.1:7890", "--fetch-workers", "2", "--no-brower", "--defaut-path", "."])
        self.assertEqual(args.sync_interval, 300)
        self.assertEqual(args.fetch_workers, 2)
        self.assertTrue(args.no_browser)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["--fetch-workers", "0"])

    def test_snapshot_cli_round_trip_requires_explicit_import_force(self):
        temporary = tempfile.mkdtemp(prefix="gfd-cli-")
        try:
            repo = repository(temporary)
            file = repo / "README.md"
            file.write_text("snapshot contents", encoding="utf-8")
            archive = Path(temporary) / "snapshot.zip"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--export", str(repo), "--output", str(archive)]), 0)
                self.assertEqual(main(["--export", str(repo), "--output", str(archive)]), 2)
                file.write_text("different", encoding="utf-8")
                self.assertEqual(main(["--import", str(repo), str(archive)]), 2)
                self.assertEqual(main(["--import", str(repo), str(archive), "--force"]), 0)
            self.assertEqual(file.read_text(encoding="utf-8"), "snapshot contents")
        finally:
            cleanup_fixture(temporary)
