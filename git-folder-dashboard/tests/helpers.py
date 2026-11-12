import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def git(path, *args):
    result = subprocess.run(["git", "-c", "core.quotepath=false"] + list(args), cwd=str(path),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def repository(parent, name="project"):
    path = Path(parent) / name
    path.mkdir()
    git(path, "init", "--quiet")
    git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    git(path, "config", "user.name", "Dashboard Test")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "commit.gpgsign", "false")
    git(path, "config", "core.autocrlf", "false")
    git(path, "config", "core.hooksPath", str(path / ".git" / "test-hooks"))
    (path / "app.py").write_text('def hello():\n    return "hello"\n', encoding="utf-8")
    (path / "README.md").write_text("# Example project\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "--quiet", "-m", "Initial commit")
    return path


def wait_tasks(runner, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tasks = runner.snapshot()
        if tasks and all(task["status"] != "running" for task in tasks):
            return tasks
        time.sleep(.025)
    raise AssertionError("Background task did not finish")


def remove_readonly(function, path, exc_info):
    # Git object files on Windows can be read-only.
    os.chmod(path, 0o700)
    function(path)


def cleanup_fixture(path):
    target = Path(path).resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    try:
        relative = target.relative_to(temporary_root)
    except ValueError:
        raise AssertionError("Refusing to remove a fixture outside the temporary directory: " + str(target))
    if not relative.parts or not relative.parts[0].startswith("gfd-"):
        raise AssertionError("Refusing to remove a directory not owned by these fixtures: " + str(target))
    if target.exists():
        shutil.rmtree(str(target), onerror=remove_readonly)
