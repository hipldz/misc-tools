# Git Folder Dashboard

[All tools](../README.md) · English | [中文](doc/README.zh-CN.md)

A local web dashboard for managing several Git repositories. Select a parent directory to scan its first-level subdirectories, inspect repository status and file changes, and perform common Git operations.

![Git Folder Dashboard preview](doc/preview.gif)

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Working-tree snapshots](#working-tree-snapshots)
- [Behavior and limitations](#behavior-and-limitations)
- [Packaging](#packaging)
- [Project structure](#project-structure)
- [API reference](#api-reference)

## Features

- Scan sibling repositories and show branches, ahead/behind counts, and working-tree changes.
- Preview staged and unstaged diffs or untracked file contents.
- Fetch, pull, push, commit, and switch branches.
- Stage, unstage, discard, delete, or locally ignore files, including bulk actions.
- Export and import working-tree changes as ZIP snapshots, including binary files.
- Switch between English/Chinese and light/dark themes.
- Mount under a URL prefix and optionally require HTTP Basic authentication.

For example, scanning `~/Code` discovers `project-a` and `project-b` below and lists `notes` as a non-Git directory:

```text
~/Code/
├── project-a/.git/
├── project-b/.git/
└── notes/
```

## Requirements

- Python 3 and Git available on `PATH`.
- Python dependencies from [requirements.txt](requirements.txt): Flask, Werkzeug, and PyInstaller. PyInstaller is needed for packaging only.
- Optional folder picker: `tkinter` and a graphical desktop on the machine running the backend. On Ubuntu, `tkinter` is supplied by `python3-tk`; paths can also be entered manually.

The code was designed for Python 3.6 / Ubuntu 18.04 compatibility, with Flask 2.0.3 and Werkzeug 2.0.3 as the documented legacy combination. The current requirements file does **not** pin versions; do not assume its latest resolved dependencies support Python 3.6.

## Quick start

From the `misc-tools` root:

```bash
cd git-folder-dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py --default-path ~/Code
```

On Windows, activate with `.venv\Scripts\activate` instead. Subsequent commands in this README run from the `git-folder-dashboard` directory.

Open `http://127.0.0.1:8765/` if the browser does not open automatically. Scan the parent directory, select a repository, and inspect its changes before applying an operation. Paths refer to the backend machine's filesystem.

## Configuration

Configuration uses command-line arguments; no `.env` file is required.

| Argument | Purpose | Default |
| --- | --- | --- |
| `--host` | Bind address | `127.0.0.1` |
| `--port` | Listen port | `8765` |
| `--default-path` | Initial workspace path shown in the UI | Empty |
| `--base-path` | URL prefix, such as `/git` | Domain root |
| `--authorize USERNAME:PASSWORD` | Require HTTP Basic authentication | Disabled |
| `--no-browser [true/false]` | Disable automatic browser opening; a bare flag means `true` | `false` |
| `--export REPO` | Export a working-tree snapshot and exit | Disabled |
| `--import REPO SNAPSHOT` | Import a snapshot and exit; requires `--force` | Disabled |
| `--output FILE`, `-o FILE` | Snapshot export destination | Timestamped ZIP in the current directory |
| `--force` | Allow export overwrite or confirm snapshot import | Disabled |

The historical aliases `--defaut-path` and `--no-brower` remain supported. Use `python app.py --help` for the command-line reference.

```bash
# Custom port, workspace, and no automatic browser opening
python app.py --port 8080 --default-path ~/Code --no-browser

# Serve under /git/ with a login
python app.py --base-path /git --authorize admin:change-me
```

The second example opens at `http://127.0.0.1:8765/git/`. A reverse proxy must preserve the configured prefix when forwarding requests. Add `--host 0.0.0.0` when the backend needs to accept connections from other machines.

Authentication covers pages, static assets, and APIs. Passwords may contain `:`, but usernames may not. Basic authentication does not encrypt credentials, and command-line arguments may be visible to local processes; use HTTPS when exposing the dashboard over a network.

## Working-tree snapshots

Export or import changes without starting the web server:

```bash
python app.py --export /path/to/repo
python app.py --export /path/to/repo --output /tmp/repo-snapshot.zip
python app.py --import /path/to/repo /tmp/repo-snapshot.zip --force
```

The repository argument may be the worktree root or a directory inside it. Non-Git directories and bare repositories are rejected. Existing export files require `--force` to overwrite.

A snapshot contains `manifest.json` plus `files/*` payloads for modified, added, deleted, and untracked files. The manifest records relative paths, change kinds, source scopes, and payload locations. The web interface uses the same archive format.

Import directly writes, creates, and deletes the listed working-tree files. It supports binary and nested files, but does not recreate the exact Git index staging layout. A snapshot stores changes rather than a complete repository backup; it does not contain repository history.

## Behavior and limitations

- Scanning covers only the selected directory's first-level children, not recursive descendants or the selected directory itself.
- Repository IDs and scan results live in memory. Scan again after restarting the backend.
- **Commit runs `git add .` before `git commit`**, so it includes all eligible changes in the repository, not just previously staged files.
- Repository-wide discard runs `git reset --hard HEAD` followed by `git clean -fd`, removing tracked changes and untracked files/directories.
- Ignore actions write to `.git/info/exclude` rather than the shared `.gitignore`.
- Login is optional and disabled by default. The tool has no per-user repository permissions.
- Remote operations use the backend machine's existing Git credentials and configuration.

## Packaging

With the dependencies installed, build a standalone executable from this project directory.

Linux/macOS:

```bash
pyinstaller --onefile --name git-folder-dashboard --add-data "static:static" app.py
```

Windows:

```bat
pyinstaller --onefile --name git-folder-dashboard --add-data "static;static" app.py
```

The output is `dist/git-folder-dashboard` (`.exe` on Windows). Git must still be available on the target machine.

```bash
./dist/git-folder-dashboard --port 8080 --default-path ~/Code --base-path /git --no-browser
```

## Project structure

| Path | Responsibility |
| --- | --- |
| [app.py](app.py) | Thin entry point calling the CLI |
| [scripts/cli.py](scripts/cli.py) | Parse arguments and run web or snapshot commands |
| [scripts/webapp.py](scripts/webapp.py) | Assemble and start the Flask application |
| [scripts/routes.py](scripts/routes.py) | Routes, validation, repository scanning, and response orchestration |
| [scripts/runtime.py](scripts/runtime.py) | Runtime configuration, authentication, URL prefix, and browser opening |
| [scripts/git_service.py](scripts/git_service.py) | Git execution, status parsing, previews, and file operations |
| [scripts/snapshot_service.py](scripts/snapshot_service.py) | Working-tree snapshot export/import |
| [scripts/repo_store.py](scripts/repo_store.py) | In-memory repository IDs, paths, and status |
| [scripts/http_utils.py](scripts/http_utils.py) | JSON request/response and download helpers |
| [static/](static/) | Plain HTML, CSS, and JavaScript UI |

The request flow is `browser → routes → Git/snapshot service → refreshed repository state → JSON → UI`. Read the CLI and routes first, then the service relevant to the operation.

## API reference

The following paths are relative to `--base-path`. Repository IDs come from scan/list responses and change after a new scan.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/config` | Runtime configuration |
| POST | `/api/select-folder` | Open the backend machine's folder picker |
| POST | `/api/scan` | Scan a parent directory |
| GET | `/api/repos` | List scanned repositories |
| POST | `/api/repos/refresh-all` | Refresh all scanned repositories |
| POST | `/api/repos/{id}/refresh` | Refresh one repository |
| POST | `/api/repos/{id}/fetch` | Fetch |
| POST | `/api/repos/{id}/pull` | Pull |
| POST | `/api/repos/{id}/push` | Push |
| POST | `/api/repos/{id}/push-origin-main` | Push the local main branch to origin |
| POST | `/api/repos/{id}/open` | Open the repository folder on the backend machine |
| POST | `/api/repos/{id}/commit` | Stage all eligible changes and commit |
| POST | `/api/repos/{id}/checkout` | Switch branch |
| POST | `/api/repos/{id}/discard` | Discard repository changes |
| POST | `/api/repos/{id}/files/preview` | Preview a diff or file |
| POST | `/api/repos/{id}/files/action` | Apply a file action |
| POST | `/api/repos/{id}/files/bulk-action` | Apply a bulk file action |
| POST | `/api/repos/{id}/export-state` | Download a snapshot ZIP |
| POST | `/api/repos/{id}/import-state` | Upload and apply a snapshot ZIP |

Repository status values are `clean`, `dirty`, `ahead`, `behind`, `diverged`, `no_remote`, and `error`. See [scripts/routes.py](scripts/routes.py) for request bodies and response fields.
