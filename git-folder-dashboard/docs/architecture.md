# Architecture

The source entry point and the packaged executable use the same CLI and application factory. Runtime source does not import build or browser-test dependencies.

```text
app.py → git_dashboard.cli
  ├─ snapshot export/import → services.snapshots → services.git
  └─ server → web.create_app → api → services.workspace / services.tasks

templates/index.html
  └─ static/js/app.js (interactions)
       ├─ api.js   (timeouts, HTTP errors, cancellation)
       ├─ state.js (repository revisions, preferences, drafts)
       ├─ ui.js    (incremental regions, errors, diff rendering)
       └─ i18n.js  (Chinese / English)
```

## Workspace lifecycle

1. Validate and discover immediate child directories. Accept `.git` directories and worktree `.git` files.
2. Derive repository IDs from normalized absolute paths. Re-scans retain identities and known fetch metadata.
3. Increment the workspace generation. Responses from an earlier generation cannot replace the current workspace.
4. Start a bounded background task. Inspect all local repositories first, publishing results as they complete.
5. Fetch configured remotes with the same worker limit. A failed remote contributes an individual failure and does not discard local data.
6. Poll `/api/state` for incremental repositories and task history. The browser polls frequently while jobs are active and less frequently when idle/hidden.

Each repository has a reentrant lock. Local checks and mutations serialize with fetches for that repository; different repositories run concurrently. Read-only diff previews remain available during fetch. Server state is protected separately and contains plain JSON data. Request handlers never use shell command interpolation.

`checked_at` records a local check. `fetched_at` records only successful fetches; `fetch_attempted_at` and `fetch_error` record the most recent attempt. Dirty state, conflicts, ahead, behind, upstream, and remotes are independent fields. Local status alone never proves that remote information is current.

Repository revisions increase when state is saved. The browser rejects earlier revisions and uses cancellation plus selection tokens for file previews. Refreshes preserve drafts, selected files, and existing diff scroll positions. A successful commit clears only the draft submitted by that operation. Failed writes are not automatically retried.

Periodic workspace fetch runs on the server and is configured with `--sync-interval`. Selecting a stale repository can trigger an individual fetch, and opening a workspace initiates a fetch after local inspection. Fetch never pulls or stages files. Pull is fast-forward only.

## Error placement

| Scope | Location | Recovery |
| --- | --- | --- |
| Workspace path / picker | Workspace dialog | Correct path and retry |
| Commit validation / Git hook | Commit panel | Retain draft and index; retry explicitly |
| Fetch / pull / push / branch / snapshot | Repository header | Detailed Git output and scoped retry |
| Workspace batch | Task drawer | Per-repository status and retry |
| Diff | Diff pane | Retry the current selection |
| Server unavailable | Main connection notice | Preserve existing content and reconnect |

## HTTP API

All API responses use JSON and `Cache-Control: no-store`, except snapshot downloads. Git command failures return `success: false` with the refreshed repository; validation uses 400, missing repositories use 404, and superseded workspace operations use 409.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/api/config` | Startup settings and version |
| GET | `/api/state` | Workspace, repository snapshots, recent tasks |
| POST | `/api/workspace` | Select/discover a workspace and start checks/fetch |
| POST | `/api/workspace/refresh` | Start a local or remote batch check |
| POST | `/api/select-folder` | Open the server-side folder picker |
| POST | `/api/repos/{id}/refresh` | Read local status |
| POST | `/api/repos/{id}/fetch` | Start/reuse a background fetch task |
| POST | `/api/repos/{id}/pull` | Fast-forward pull |
| POST | `/api/repos/{id}/push` | Push the current branch using Git configuration |
| POST | `/api/repos/{id}/commit` | Commit the index; `stage_all: true` is explicit |
| POST | `/api/repos/{id}/checkout` | Switch to a named local or tracking branch |
| POST | `/api/repos/{id}/open` | Open the repository folder |
| POST | `/api/repos/{id}/files/preview` | Staged/unstaged diff or untracked text preview |
| POST | `/api/repos/{id}/files/action` | Stage, unstage, discard, delete, ignore, open |
| POST | `/api/repos/{id}/files/bulk-action` | Apply an action to the current scope |
| POST | `/api/repos/{id}/export-state` | Download a working-tree changes zip |
| POST | `/api/repos/{id}/import-state` | Apply a multipart snapshot |

## Boundaries

One process has one shared workspace. State and task history are in memory; the browser stores drafts/preferences locally. Git itself and credentials must be installed/configured on the server. There is no automatic merge, force-push, recursive repository discovery, or persistent job database. Snapshot imports restore working-tree entries, not the exact index layout. The v2 workspace endpoints replace the old scan/store API.
