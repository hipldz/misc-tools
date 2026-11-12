"""Test, build a one-file executable, and collect release artifacts."""

import argparse
import hashlib
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Skip the backend test suite.")
    parser.add_argument("--install-dependencies", action="store_true", help="Prepare build dependencies using the Tsinghua PyPI mirror.")
    args = parser.parse_args()
    if args.install_dependencies:
        mirror = ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
        subprocess.run([sys.executable, "-m", "pip", "install"] + mirror +
                       ["--upgrade", "pip", "setuptools", "wheel"], cwd=str(ROOT), check=True)
        subprocess.run([sys.executable, "-m", "pip", "install"] + mirror +
                       ["-r", "requirements-build.txt"], cwd=str(ROOT), check=True)
    if not importlib.util.find_spec("PyInstaller"):
        parser.error("Install requirements-build.txt into this Python environment first.")
    if not args.skip_tests:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], cwd=str(ROOT), check=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "pyinstaller"),
        str(ROOT / "packaging" / "git-folder-dashboard.spec"),
    ], cwd=str(ROOT), check=True)
    sys.path.insert(0, str(ROOT))
    from git_dashboard import __version__

    executable = ROOT / "dist" / ("git-folder-dashboard.exe" if sys.platform == "win32" else "git-folder-dashboard")
    release = ROOT / "dist" / "git-folder-dashboard-{0}-{1}-{2}.zip".format(
        __version__, platform.system().lower(), platform.machine().lower())
    with ZipFile(str(release), "w", ZIP_DEFLATED) as archive:
        archive.write(str(executable), executable.name)
        for source in ("README.md", "LICENSE", "docs/README.zh-CN.md"):
            archive.write(str(ROOT / source), source)
    sums = []
    for artifact in (executable, release):
        checksum = hashlib.sha256(artifact.read_bytes()).hexdigest()
        sums.append("{0}  {1}".format(checksum, artifact.name))
        print("Built: {0}".format(artifact))
    (ROOT / "dist" / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
