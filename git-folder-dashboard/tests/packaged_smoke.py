"""Verify the one-file release from a directory without source assets."""

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.helpers import repository, cleanup_fixture


def main():
    executable = ROOT / "dist" / ("git-folder-dashboard.exe" if os.name == "nt" else "git-folder-dashboard")
    if not executable.is_file():
        raise SystemExit("Build the executable first.")
    temporary = tempfile.mkdtemp(prefix="gfd-packaged-")
    process = None
    try:
        repo = repository(temporary)
        (repo / "README.md").write_text("from executable", encoding="utf-8")
        archive = Path(temporary) / "snapshot.zip"
        subprocess.run([str(executable), "--export", str(repo), "--output", str(archive)], cwd=temporary, check=True, timeout=30)
        (repo / "README.md").write_text("different", encoding="utf-8")
        subprocess.run([str(executable), "--import", str(repo), str(archive), "--force"], cwd=temporary, check=True, timeout=30)
        assert (repo / "README.md").read_text(encoding="utf-8") == "from executable"
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = reserved.getsockname()[1]
        process = subprocess.Popen(
            [str(executable), "--port", str(port), "--no-browser", "--base-path", "/git", "--authorize", "test:secret"],
            cwd=temporary, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        base = "http://127.0.0.1:{0}/git".format(port)
        # Local verification must not depend on system proxy/PAC configuration.
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                opener.open(base + "/api/config", timeout=3).close()
            except HTTPError as error:
                assert error.code == 401
                break
            except (URLError, TimeoutError, ConnectionError):
                if process.poll() is not None:
                    raise AssertionError(process.communicate()[0].decode("utf-8", errors="replace"))
                time.sleep(.1)
        else:
            raise AssertionError("Packaged server did not start")
        headers = {"Authorization": "Basic " + base64.b64encode(b"test:secret").decode("ascii")}

        def get(path):
            with opener.open(Request(base + path, headers=headers), timeout=5) as response:
                assert response.status == 200
                return response.read()

        assert b"Git Folder" in get("/")
        assert b".app-shell" in get("/static/css/app.css")
        assert b"async function boot" in get("/static/js/app.js")
        assert b"export function render" in get("/static/js/ui.js")
        assert b"<svg" in get("/static/icons/brand.svg")
        assert json.loads(get("/api/state"))["success"]
        print("Packaged checks passed: CLI snapshot round trip, isolated working directory, Basic Auth, /git hosting, bundled templates/CSS/JS/icons.")
    finally:
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.terminate()
            output = process.communicate(timeout=15)[0]
            if sys.exc_info()[0] is not None:
                print(output.decode("utf-8", errors="replace"), file=sys.stderr)
        elif process:
            process.communicate()
        cleanup_fixture(temporary)


if __name__ == "__main__":
    main()
