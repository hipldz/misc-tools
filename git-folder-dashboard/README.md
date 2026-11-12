# Git Folder Dashboard

English | [中文](docs/README.zh-CN.md)

A local workspace for managing multiple Git repositories. See local changes and remote differences independently, stage exactly what you intend to commit, and follow background fetch progress without blocking the interface.

- Workspace overview, searchable repository list, changes, and file diffs
- Local checks when opening a repository, returning to the window, and every 10 seconds while viewing it
- Initial local checks followed by bounded background fetches, with per-repository progress and retry
- Independent local and remote timestamps; failed fetches preserve previous results and display an error
- Commits respect the index; **Stage all and commit** is a separate, explicit operation
- Inline errors, persistent commit drafts, light/dark themes, English/Chinese, and responsive layouts
- Working-tree snapshot export/import through the UI or CLI
- Optional Basic Auth, URL subpath hosting, periodic workspace fetch, and a Git HTTP proxy
- All interface resources are local; no CDN or frontend compilation is required

## Run from source

Git must be installed and available on `PATH`. A modern Python environment is recommended; development and Windows packaging are verified with Python 3.12. Runtime code retains Python 3.6 syntax. The old Python 3.6 / Flask 2.0.3 combination is available through [legacy requirements](requirements-legacy.txt), but was not runtime-tested in this revision.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
.\.venv\Scripts\python.exe app.py --default-path D:\Workspace\Git
```

On Linux/macOS use `.venv/bin/python` instead. Default address: `http://127.0.0.1:8765`.

```powershell
# Fetch all repositories every five minutes; optional local proxy
python app.py --default-path D:\Workspace\Git --sync-interval 300 --git-proxy http://127.0.0.1:7890

# Subpath hosting and HTTP Basic authentication
python app.py --base-path /git --authorize admin:change-me --no-browser
```

| Option | Default | Purpose |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Listen port |
| `--default-path` | empty | Initial parent directory |
| `--sync-interval` | `0` | Periodic workspace fetch in seconds; `0` disables it |
| `--fetch-workers` | `3` | Concurrent local checks/fetches, from 1 to 8 |
| `--git-proxy` | empty | HTTP proxy used by Git |
| `--base-path` | empty | URL prefix such as `/git` |
| `--authorize` | disabled | Basic Auth as `username:password` |
| `--no-browser` | `false` | Do not open the browser; accepts optional `true/false` |

The old `--defaut-path` and `--no-brower` aliases remain supported. Periodic synchronization is configured at startup, not through UI settings. Initial workspace loading and manual **Fetch remotes** work independently of the periodic interval. Fetch updates remote references; it does not pull, commit, or alter working-tree files. Pull uses `--ff-only`.

The folder picker opens on the machine running the server. Windows uses the native Common Item Dialog and does not need Tk; Linux/macOS use Tk. On a headless/remote server, paste the server-side path instead. Linux folder selection may require `python3-tk`. Git is required separately by the executable too. For external access, place Basic Auth behind HTTPS; the default listener is local.

## Windows one-file release

```powershell
.\.venv\Scripts\python.exe scripts/build.py --install-dependencies
```

With dependencies already installed:

```powershell
.\.venv\Scripts\python.exe scripts/build.py
# Cross-platform entry point, using the current Python environment:
python scripts/build.py
```

The build runs the backend regression suite, packages `static/` and `templates/`, and writes:

```text
dist/
  git-folder-dashboard.exe
  git-folder-dashboard-2.0.0-windows-amd64.zip
  SHA256SUMS.txt
```

`build/` holds temporary PyInstaller files and verification screenshots. The executable runs from any directory; it does not need source files beside it. Packaging needs a modern Python/PyInstaller environment. An optional PowerShell wrapper is available at `scripts/build.ps1`. See [development and release checks](docs/development.md).

## Snapshots

```powershell
python app.py --export ./ --output ./changes.zip
python app.py --import ./ ./changes.zip --force
```

A snapshot contains **changed working-tree files**, including new files, binary contents, and deletions. It is not a full repository backup and does not reconstruct index staging. Import applies only recorded entries and requires explicit confirmation. Export refuses to overwrite an existing archive without `--force`.

## Repository structure

```text
app.py                         Source and executable entry point
git_dashboard/
  cli.py                       Server and snapshot command-line options
  runtime.py                   Resource paths and URL-prefix middleware
  web.py                       Application factory, authentication, server lifecycle
  api.py                       HTTP validation and orchestration
  http.py                      JSON/download helpers
  services/
    git.py                     Git commands, index semantics, file operations
    folders.py                 Native Windows / Tk folder selection
    snapshots.py               Working-tree snapshot format
    workspace.py               Stable identities, state, repository locks
    tasks.py                   Bounded jobs, progress, periodic fetch
templates/index.html           Application shell and dialogs
static/
  css/app.css                  Themes, layouts, components, responsive rules
  js/                          Requests, state, localization, rendering, interactions
  icons/brand.svg              Local branding asset
scripts/                       Build commands only
packaging/                     Versioned PyInstaller configuration
tests/                         Isolated Git, HTTP, CLI, concurrency, browser checks
docs/                          Chinese guide and engineering documentation
build/                         Ignored temporary build/verification output
dist/                          Ignored release artifacts
```

[Architecture and API](docs/architecture.md) · [Development and packaging](docs/development.md)

The workspace contains first-level repository subfolders, including worktrees with a `.git` file. Workspace/task data is held in server memory; browser preferences and commit drafts are stored locally. Restarting the server re-discovers repositories. One server instance shares one workspace across connected browser clients.
