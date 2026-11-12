import { request, post } from "./api.js";
import {
  state,
  activeRepo,
  taskItem,
  applySnapshot,
  mergeRepo,
  savePreference,
  readPreference,
} from "./state.js";
import { t } from "./i18n.js";
import { $, render, toast, confirmAction, remoteStale } from "./ui.js";

let workspaceEpoch = 0;
let pollTimer;
let polling = false;
let previewController;
const checkedAt = {};

function rememberDrafts() {
  savePreference("drafts", state.drafts);
}
function addTask(task) {
  state.tasks = [task, ...state.tasks.filter((item) => item.id !== task.id)];
}

function reconcileSelection(repo) {
  const selected = state.selections[repo.id];
  if (!selected) return;
  const groups = {
    staged: repo.staged_files,
    unstaged: repo.unstaged_files,
    untracked: repo.untracked_list,
  };
  if (groups[selected.scope]?.some((file) => file.path === selected.path))
    return;
  const next = Object.keys(groups).find((scope) =>
    groups[scope]?.some((file) => file.path === selected.path),
  );
  if (next) state.selections[repo.id] = { path: selected.path, scope: next };
  else delete state.selections[repo.id];
}

async function loadPreview(repoId, selection, quiet = false) {
  if (!selection || state.activeRepoId !== repoId || state.view !== "repo")
    return;
  previewController?.abort();
  previewController = new AbortController();
  const controller = previewController;
  const token = state.preview.token + 1;
  const generation = state.generation;
  const same =
    state.preview.repoId === repoId &&
    state.preview.path === selection.path &&
    state.preview.scope === selection.scope;
  state.preview = {
    repoId,
    ...selection,
    token,
    loading: !(quiet && same && state.preview.data),
    data: quiet && same ? state.preview.data : null,
  };
  if (!quiet || !same) {
    $("diffContent").scrollTop = 0;
    $("diffContent").scrollLeft = 0;
  }
  render();
  try {
    const data = await request(`/api/repos/${repoId}/files/preview`, {
      method: "POST",
      body: selection,
      signal: controller.signal,
    });
    if (
      state.preview.token !== token ||
      state.activeRepoId !== repoId ||
      state.generation !== generation
    )
      return;
    state.preview = { repoId, ...selection, token, loading: false, data };
  } catch (error) {
    if (
      controller.signal.aborted ||
      state.preview.token !== token ||
      state.generation !== generation
    )
      return;
    state.preview = {
      repoId,
      ...selection,
      token,
      loading: false,
      error: error.message,
    };
  }
  render();
}

async function poll() {
  clearTimeout(pollTimer);
  if (polling) return;
  polling = true;
  const epoch = workspaceEpoch;
  const previousRepo = activeRepo();
  const previousPath = state.path;
  const previousInstance = state.instanceId;
  const previousView = state.view;
  const previousRevision = previousRepo?.revision;
  try {
    const data = await request("/api/state", { timeout: 10000 });
    if (epoch !== workspaceEpoch) return;
    applySnapshot(data);
    state.connectionError = "";
    if (
      previousInstance &&
      data.instance_id !== previousInstance &&
      !data.path &&
      previousPath
    ) {
      await openWorkspace(previousPath);
      if (
        previousView === "repo" &&
        state.repos.some((repo) => repo.id === previousRepo?.id)
      )
        await selectRepo(previousRepo.id);
      return;
    }
    const repo = activeRepo();
    if (repo) reconcileSelection(repo);
    render();
    if (
      repo?.id === previousRepo?.id &&
      repo?.revision !== previousRevision &&
      !state.busy[repo.id]
    ) {
      loadPreview(repo.id, state.selections[repo.id], true);
    }
  } catch (error) {
    if (epoch === workspaceEpoch) {
      state.connectionError = error.message;
      render();
    }
  } finally {
    polling = false;
    const running = state.tasks.some(
      (task) =>
        task.status === "running" && task.generation === state.generation,
    );
    pollTimer = setTimeout(
      poll,
      document.hidden
        ? 15000
        : state.connectionError
          ? 5000
          : running
            ? 700
            : 4000,
    );
  }
}

async function refreshRepo(
  repoId,
  { fetchIfStale = false, quiet = false } = {},
) {
  const repo = state.repos.find((repo) => repo.id === repoId);
  if (!repo || state.busy[repoId] || taskItem(repoId)) return;
  const generation = state.generation;
  if (quiet && Date.now() - (checkedAt[repoId] || 0) < 1500) return;
  checkedAt[repoId] = Date.now();
  state.busy[repoId] = "refresh";
  render();
  try {
    const data = await post(`/api/repos/${repoId}/refresh`);
    mergeRepo(data.repo, generation);
    if (state.generation !== generation) return;
    reconcileSelection(data.repo);
    if (state.errors[repoId]?.action === "refresh") delete state.errors[repoId];
    loadPreview(repoId, state.selections[repoId], true);
    if (fetchIfStale && data.repo.has_remote && remoteStale(data.repo))
      await fetchRepo(repoId);
  } catch (error) {
    if (state.generation === generation)
      state.errors[repoId] = {
        scope: "repo",
        action: "refresh",
        message: error.message,
        retry: () => refreshRepo(repoId),
      };
  } finally {
    delete state.busy[repoId];
    render();
  }
}

async function fetchRepo(repoId) {
  const generation = state.generation;
  try {
    const data = await post(`/api/repos/${repoId}/fetch`);
    if (state.generation !== generation) return;
    addTask(data.task);
    if (state.errors[repoId]?.action === "fetch") delete state.errors[repoId];
    render();
    poll();
  } catch (error) {
    if (state.generation === generation)
      state.errors[repoId] = {
        scope: "repo",
        action: "fetch",
        message: error.message,
        retry: () => fetchRepo(repoId),
      };
    render();
  }
}

async function selectRepo(repoId) {
  if (!state.repos.some((repo) => repo.id === repoId)) return;
  state.activeRepoId = repoId;
  state.view = "repo";
  state.expanded = false;
  savePreference("activeRepo", repoId);
  render();
  loadPreview(repoId, state.selections[repoId]);
  await refreshRepo(repoId, { fetchIfStale: true });
}

async function perform(
  repoId,
  action,
  execute,
  { scope = "repo", after, retry } = {},
) {
  if (state.busy[repoId] || taskItem(repoId)) return;
  const generation = state.generation;
  state.busy[repoId] = action;
  delete state.errors[repoId];
  render();
  try {
    const data = await execute();
    mergeRepo(data?.repo, generation);
    if (state.generation !== generation) return;
    if (after) after(data);
    const repo = state.repos.find((repo) => repo.id === repoId);
    if (repo) reconcileSelection(repo);
    toast(
      t(action === "commit" ? "commitSuccess" : "operationSuccess", {
        action: t(action),
      }),
    );
    loadPreview(repoId, state.selections[repoId], true);
  } catch (error) {
    mergeRepo(error.data?.repo, generation);
    if (state.generation === generation)
      state.errors[repoId] = {
        action,
        scope,
        message: error.message,
        retry:
          retry || (() => perform(repoId, action, execute, { scope, after })),
      };
  } finally {
    delete state.busy[repoId];
    render();
  }
}

async function commit(repoId, stageAll = false) {
  const message = (state.drafts[repoId] || "").trim();
  if (!message) {
    state.errors[repoId] = {
      scope: "commit",
      action: "commit",
      validation: true,
      message: t("commitRequired"),
      retry: () => commit(repoId, stageAll),
    };
    render();
    $("commitMessage").focus();
    return;
  }
  if (
    stageAll &&
    !(await confirmAction(
      t("confirmCommitAll"),
      t("commitAllText"),
      t("commitAll"),
    ))
  )
    return;
  await perform(
    repoId,
    "commit",
    () => post(`/api/repos/${repoId}/commit`, { message, stage_all: stageAll }),
    {
      scope: "commit",
      retry: () => commit(repoId, stageAll),
      after: () => {
        if ((state.drafts[repoId] || "").trim() === message) {
          delete state.drafts[repoId];
          rememberDrafts();
          if ($("commitMessage").dataset.repoId === repoId)
            $("commitMessage").value = "";
        }
      },
    },
  );
}

async function fileAction(repo, dataset, bulk = false) {
  const { path, scope, kind } = dataset;
  const target = bulk
    ? t("files", {
        count: (
          repo[
            {
              staged: "staged_files",
              unstaged: "unstaged_files",
              untracked: "untracked_list",
            }[scope]
          ] || []
        ).length,
      })
    : path;
  const discard = kind.startsWith("discard");
  const remove = kind.startsWith("delete");
  if (
    (discard || remove) &&
    !(await confirmAction(
      t(discard ? "confirmDiscard" : "confirmDelete"),
      t(discard ? "discardText" : "deleteText", { target }),
      t(discard ? "discard" : "delete"),
    ))
  )
    return;
  await perform(repo.id, kind.split("_")[0], () =>
    post(
      `/api/repos/${repo.id}/files/${bulk ? "bulk-action" : "action"}`,
      bulk ? { scope, action: kind } : { path, action: kind },
    ),
  );
}

function showWorkspace() {
  state.workspaceError = "";
  $("pathInput").value = state.path || readPreference("workspacePath", "");
  render();
  $("workspaceDialog").showModal();
  $("pathInput").focus();
}

async function openWorkspace(path) {
  if (state.workspaceBusy) return;
  const epoch = ++workspaceEpoch;
  const previousId = state.activeRepoId;
  state.workspaceBusy = true;
  state.workspaceError = "";
  render();
  try {
    const data = await post("/api/workspace", { path, fetch_remote: true });
    if (epoch !== workspaceEpoch) return;
    applySnapshot(data);
    if (state.repos.some((repo) => repo.id === previousId))
      state.activeRepoId = previousId;
    state.view = "overview";
    state.errors = {};
    state.preview = { token: state.preview.token + 1 };
    state.connectionError = "";
    state.query = "";
    state.filter = "all";
    $("searchInput").value = "";
    savePreference("workspacePath", state.path);
    $("workspaceDialog").close();
    poll();
  } catch (error) {
    state.workspaceError = error.message;
    if (!$("workspaceDialog").open) {
      $("pathInput").value = path;
      $("workspaceDialog").showModal();
    }
  } finally {
    state.workspaceBusy = false;
    render();
  }
}

async function refreshWorkspace(fetchRemote) {
  try {
    const data = await post("/api/workspace/refresh", {
      fetch_remote: fetchRemote,
    });
    if (data.repos) applySnapshot(data);
    addTask(data.task);
    render();
    poll();
  } catch (error) {
    state.connectionError = error.message;
    render();
  }
}

async function exportSnapshot(repoId) {
  const repo = state.repos.find((repo) => repo.id === repoId);
  await perform(repoId, "export", async () => {
    const blob = await request(`/api/repos/${repoId}/export-state`, {
      method: "POST",
      raw: true,
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${repo.name}-working-tree-snapshot.zip`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

async function handleAction(button) {
  const { action, id } = button.dataset;
  const repo = activeRepo();
  if (button.disabled) return;
  if (action !== "more")
    button.closest("details.menu")?.removeAttribute("open");
  switch (action) {
    case "workspace":
      showWorkspace();
      break;
    case "close-workspace":
      if (!state.workspaceBusy) $("workspaceDialog").close();
      break;
    case "browse":
      if (state.selectingFolder) break;
      state.selectingFolder = true;
      state.workspaceError = "";
      render();
      try {
        // A user-controlled native dialog can legitimately stay open for minutes.
        const data = await request("/api/select-folder", {
          method: "POST",
          timeout: 0,
        });
        if (data.path) $("pathInput").value = data.path;
      } catch (error) {
        state.workspaceError = error.message;
      } finally {
        state.selectingFolder = false;
        render();
      }
      break;
    case "overview":
      state.view = "overview";
      render();
      break;
    case "folders":
      state.view = "folders";
      render();
      break;
    case "filter":
      state.filter = button.dataset.filter;
      render();
      break;
    case "select-repo":
      await selectRepo(id);
      break;
    case "refresh-all":
      await refreshWorkspace(false);
      break;
    case "fetch-all":
      await refreshWorkspace(true);
      break;
    case "tasks":
      state.tasksOpen = !state.tasksOpen;
      render();
      break;
    case "theme":
      state.theme = state.theme === "light" ? "dark" : "light";
      savePreference("theme", state.theme);
      render();
      break;
    case "language":
      state.language = state.language === "zh" ? "en" : "zh";
      savePreference("language", state.language);
      render();
      break;
    case "reconnect":
      await poll();
      if (activeRepo()) await refreshRepo(activeRepo().id);
      break;
    case "retry-task":
      if (button.dataset.fetch === "true") await fetchRepo(id);
      else await refreshRepo(id);
      break;
    case "refresh":
      if (repo) await refreshRepo(repo.id);
      break;
    case "fetch":
      if (repo) await fetchRepo(repo.id);
      break;
    case "pull":
    case "push":
    case "open":
      if (repo)
        await perform(repo.id, action, () =>
          post(`/api/repos/${repo.id}/${action}`),
        );
      break;
    case "retry-action":
      state.errors[repo?.id]?.retry?.();
      break;
    case "commit-all":
      if (repo) await commit(repo.id, true);
      break;
    case "preview":
      if (repo) {
        state.selections[repo.id] = {
          path: button.dataset.path,
          scope: button.dataset.scope,
        };
        await loadPreview(repo.id, state.selections[repo.id]);
      }
      break;
    case "preview-retry":
      if (repo) await loadPreview(repo.id, state.selections[repo.id]);
      break;
    case "file":
    case "bulk":
      if (repo) await fileAction(repo, button.dataset, action === "bulk");
      break;
    case "toggle-section":
      if (repo) {
        const key = `${repo.id}.${button.dataset.scope}`;
        state.sections[key] = state.sections[key] === false;
        render();
      }
      break;
    case "wrap":
      state.wrap = !state.wrap;
      render();
      break;
    case "expand":
      state.expanded = !state.expanded;
      render();
      break;
    case "export":
      if (repo) await exportSnapshot(repo.id);
      break;
    case "import":
      if (repo) {
        $("snapshotInput").dataset.repoId = repo.id;
        $("snapshotInput").value = "";
        $("snapshotInput").click();
      }
      break;
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (button)
    handleAction(button).catch((error) => {
      state.connectionError = error.message;
      render();
    });
});
document.addEventListener("keydown", (event) => {
  if (
    (event.key === "Enter" || event.key === " ") &&
    event.target.matches("tr[data-action]")
  ) {
    event.preventDefault();
    handleAction(event.target);
  }
  if (event.key === "Escape" && state.tasksOpen) {
    state.tasksOpen = false;
    render();
  }
});
$("workspaceForm").addEventListener("submit", (event) => {
  event.preventDefault();
  openWorkspace($("pathInput").value.trim());
});
$("workspaceDialog").addEventListener("cancel", (event) => {
  if (state.workspaceBusy) event.preventDefault();
});
$("searchInput").addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});
$("commitMessage").addEventListener("input", (event) => {
  if (state.activeRepoId) {
    state.drafts[state.activeRepoId] = event.target.value;
    rememberDrafts();
  }
});
$("commitMessage").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    $("commitForm").requestSubmit();
  }
});
$("commitForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (activeRepo() && !$("commitButton").disabled) commit(activeRepo().id);
});
$("repoToolbar").addEventListener("change", async (event) => {
  if (event.target.id !== "branchSelect") return;
  const repo = activeRepo();
  const branch = event.target.value;
  if (!repo || branch === repo.branch) return;
  if (
    repo.dirty &&
    !(await confirmAction(t("confirmCheckout"), t("checkoutText", { branch })))
  ) {
    render();
    return;
  }
  await perform(repo.id, "branch", () =>
    post(`/api/repos/${repo.id}/checkout`, { branch }),
  );
});
$("snapshotInput").addEventListener("change", async (event) => {
  const repoId = event.target.dataset.repoId;
  const file = event.target.files[0];
  if (
    !file ||
    !(await confirmAction(t("confirmImport"), t("importText"), t("import")))
  )
    return;
  const form = new FormData();
  form.append("snapshot", file);
  await perform(repoId, "import", () =>
    request(`/api/repos/${repoId}/import-state`, {
      method: "POST",
      body: form,
    }),
  );
});
document.addEventListener("dblclick", (event) => {
  const button = event.target.closest("button.file-name");
  const repo = activeRepo();
  if (button && repo)
    perform(repo.id, "open", () =>
      post(`/api/repos/${repo.id}/files/action`, {
        action: "open",
        path: button.dataset.path,
      }),
    );
});
function refreshOnReturn() {
  if (!document.hidden && state.view === "repo" && activeRepo())
    refreshRepo(activeRepo().id, { quiet: true });
  poll();
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshOnReturn();
});
window.addEventListener("focus", refreshOnReturn);
setInterval(() => {
  if (!document.hidden && state.view === "repo" && activeRepo())
    refreshRepo(activeRepo().id, { quiet: true });
}, 10000);

async function boot() {
  render();
  try {
    const config = await request("/api/config");
    state.config = { ...state.config, ...config };
    const data = await request("/api/state");
    applySnapshot(data);
    const path =
      state.path ||
      readPreference("workspacePath", "") ||
      config.default_workspace;
    render();
    if (path && !state.path) await openWorkspace(path);
  } catch (error) {
    state.connectionError = error.message;
    render();
  }
  poll();
}
boot();
