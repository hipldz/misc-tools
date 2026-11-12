# Development and release checks

## Environments

- Runtime: `requirements.txt` (Flask and Werkzeug).
- Legacy Python 3.6 source runtime: `requirements-legacy.txt`; this environment is not part of the current runtime validation.
- Build: `requirements-build.txt` adds PyInstaller and its hooks. Use a modern Python environment, verified here with Python 3.12.
- Browser development: `requirements-dev.txt` adds Playwright. The browser check uses installed Microsoft Edge, so it does not download a browser.
- Backend checks use standard-library `unittest` and temporary Git repositories. No user repository is modified by tests.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-dev.txt
```

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe tests/browser_smoke.py
node tests/frontend_state.mjs
```

The backend suite covers index-only commits, explicit stage-all commits, unborn repositories, Unicode paths, renames, binary previews, snapshot restore, path boundaries, stable IDs, fetch failure, bounded concurrency, repository locks, workspace changes, authentication, subpath resources, and CLI options.

The browser check creates an offline fixture workspace and verifies initial background loading, external file refresh, retained drafts/focus/diff scrolling, failed hooks, index-only commits, fetch error placement, task details, themes, localization, responsive layout, and `/git` deployment. Screenshots are written to `build/verification/`. The optional Node check covers stale responses, task ordering, preference migration, and server restart boundaries; Node is not required to run or package the app.

## Release

```powershell
.\.venv\Scripts\python.exe scripts/build.py --install-dependencies
.\.venv\Scripts\python.exe tests/packaged_smoke.py
```

`scripts/build.py` runs backend tests by default, invokes the versioned spec, and creates a one-file executable, distributable zip, and SHA-256 checksums. `--install-dependencies` prepares the environment using the Tsinghua mirror. `scripts/build.ps1` is a convenience wrapper using the workspace virtual environment. `--skip-tests` / `-SkipTests` is available when checks have already passed.

The spec includes both `static/` and `templates/`. Runtime resource resolution uses PyInstaller's extraction directory when frozen, and the repository root when running from source. Build outputs resolve against the script location, so commands work independently of the current directory.

Windows folder selection uses the system [Common Item Dialog](https://learn.microsoft.com/en-us/windows/win32/shell/common-file-dialog) through `ctypes`. Windows releases deliberately exclude Tk, so an incomplete local Tcl/Tk installation cannot break the packaged folder picker. A Windows regression test initializes the COM dialog without opening a visible window and verifies cancellation handling.

The packaged smoke check starts the EXE from a temporary directory, verifies authenticated subpath serving and bundled CSS/JS, exercises snapshot export/import through the executable, and shuts down its own process tree. It requires Git on `PATH`.

Only `dist/` contains release artifacts. `build/` contains disposable intermediate outputs; neither directory is committed. The checked-in spec lives under `packaging/`, and the root has no required generated spec or frontend dependencies.
