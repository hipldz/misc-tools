const STORAGE_KEYS = {
  theme: "theme",
  language: "language",
  workspacePath: "workspacePath",
  activeTab: "activeTab",
  activeRepoId: "activeRepoId",
  workingTreeSections: "workingTreeSections",
};

const DEFAULT_LANGUAGE = "en";
const APP_BASE_PATH = window.__APP_BASE_PATH__ || "";

let appConfig = {
  default_workspace: "",
};

const state = {
  repos: [],
  nonGitDirs: [],
  busy: false,
  selecting: false,
  snapshotTransfer: {
    repoId: null,
    action: "",
  },
  language: localStorage.getItem(STORAGE_KEYS.language) || DEFAULT_LANGUAGE,
  activeRepoId: localStorage.getItem(STORAGE_KEYS.activeRepoId) || null,
  activeTab: localStorage.getItem(STORAGE_KEYS.activeTab) || "dashboard",
  filter: "",
  theme: localStorage.getItem(STORAGE_KEYS.theme) || "light",
  preview: {
    repoId: null,
    path: "",
    scope: "",
    mode: "diff",
    panelMode: "hidden",
    content: "",
    loading: false,
    error: "",
  },
  workingTreeSections: loadWorkingTreeSections(),
  autoRefreshTimerId: null,
};

const pathInput = document.getElementById("pathInput");
const filterInput = document.getElementById("filterInput");
const selectButton = document.getElementById("selectButton");
const scanButton = document.getElementById("scanButton");
const addRepositoryButton = document.getElementById("addRepositoryButton");
const sidebarRepoList = document.getElementById("sidebarRepoList");
const repoDetail = document.getElementById("repoDetail");
const nonGitList = document.getElementById("nonGitList");
const errorBox = document.getElementById("errorBox");
const globalLoading = document.getElementById("globalLoading");
const globalLoadingText = document.getElementById("globalLoadingText");
const themeButton = document.getElementById("themeButton");
const languageButton = document.getElementById("languageButton");
const importSnapshotInput = document.getElementById("importSnapshotInput");
const tabs = document.querySelectorAll(".rail-button[data-tab]");
const panels = document.querySelectorAll("[data-panel]");

function t(key, vars = {}) {
  const catalog = MESSAGES[state.language] || MESSAGES[DEFAULT_LANGUAGE];
  const fallbackCatalog = MESSAGES[DEFAULT_LANGUAGE];
  const template = catalog[key] || fallbackCatalog[key] || key;
  return Object.entries(vars).reduce(
    (result, [name, value]) => result.replaceAll(`{${name}}`, String(value)),
    template
  );
}

function labelFor(prefix, value) {
  const key = `${prefix}.${value}`;
  const catalog = MESSAGES[state.language] || MESSAGES[DEFAULT_LANGUAGE];
  const fallbackCatalog = MESSAGES[DEFAULT_LANGUAGE];
  return catalog[key] || fallbackCatalog[key] || value;
}

function applyStaticTranslations() {
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    node.setAttribute("title", t(node.dataset.i18nTitle));
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-tip]").forEach((node) => {
    node.dataset.tip = t(node.dataset.i18nTip);
  });
  document.title = t("app.title");
}

function setBusy(isBusy, repoId = null) {
  state.busy = isBusy;
  state.activeRepoId = repoId || state.activeRepoId;
  render();
}

function setSelecting(isSelecting) {
  state.selecting = isSelecting;
  render();
}

function setSnapshotTransfer(repoId = null, action = "") {
  state.snapshotTransfer = {
    repoId,
    action,
  };
  render();
}

function resetPreview(repoId = null) {
  state.preview = {
    repoId,
    path: "",
    scope: "",
    mode: "diff",
    panelMode: "hidden",
    content: "",
    loading: false,
    error: "",
  };
}

function setPreviewPanelMode(mode) {
  state.preview.panelMode = mode;
}

function loadWorkingTreeSections() {
  const fallback = {
    staged: false,
    unstaged: false,
    untracked: false,
  };
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.workingTreeSections);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw);
    return {
      staged: Boolean(parsed.staged),
      unstaged: Boolean(parsed.unstaged),
      untracked: Boolean(parsed.untracked),
    };
  } catch {
    return fallback;
  }
}

function persistWorkspacePath(path) {
  if (path) {
    localStorage.setItem(STORAGE_KEYS.workspacePath, path);
  } else {
    localStorage.removeItem(STORAGE_KEYS.workspacePath);
  }
}

function persistActiveRepoId(repoId) {
  if (repoId) {
    localStorage.setItem(STORAGE_KEYS.activeRepoId, repoId);
  } else {
    localStorage.removeItem(STORAGE_KEYS.activeRepoId);
  }
}

function persistWorkingTreeSections() {
  localStorage.setItem(
    STORAGE_KEYS.workingTreeSections,
    JSON.stringify(state.workingTreeSections)
  );
}

function persistUiState() {
  localStorage.setItem(STORAGE_KEYS.activeTab, state.activeTab);
  persistActiveRepoId(state.activeRepoId);
  persistWorkingTreeSections();
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

function withBasePath(path) {
  if (!APP_BASE_PATH) {
    return path;
  }
  if (!path.startsWith("/")) {
    return `${APP_BASE_PATH}/${path}`;
  }
  return `${APP_BASE_PATH}${path}`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(withBasePath(url), {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || t("error.requestFailed"));
  }
  return data;
}

async function downloadFile(url, filename) {
  const response = await fetch(withBasePath(url), { method: "POST" });
  if (!response.ok) {
    let detail = "";
    try {
      const data = await response.json();
      detail = data.detail || data.message || "";
    } catch {}
    throw new Error(detail || t("error.requestFailed"));
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function loadConfig() {
  try {
    const data = await requestJson("/api/config");
    appConfig = {
      default_workspace: (data.default_workspace || "").trim(),
    };
  } catch {
    appConfig = { default_workspace: "" };
  }
}

function scheduleAutoRefresh() {
  if (state.autoRefreshTimerId) {
    window.clearInterval(state.autoRefreshTimerId);
    state.autoRefreshTimerId = null;
  }

  return;
}

function updateRepo(repo) {
  state.repos = state.repos.map((item) => (item.id === repo.id ? repo : item));
}

function normalizeFileEntries(entries = [], fallbackScope = "unstaged") {
  return entries.map((entry) => {
    if (typeof entry === "string") {
      return {
        path: entry,
        name: entry.split("/").pop() || entry,
        status: fallbackScope === "untracked" ? "U" : "M",
      };
    }
    return {
      path: entry.path,
      name: entry.name || entry.path.split("/").pop() || entry.path,
      status: entry.status || (fallbackScope === "untracked" ? "U" : "M"),
    };
  });
}

async function scan() {
  const path = pathInput.value.trim();
  if (!path) {
    showError(t("error.enterWorkspacePath"));
    return;
  }

  showError("");
  setBusy(true);
  try {
    const data = await requestJson("/api/scan", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    persistWorkspacePath(path);
    state.repos = data.repos || [];
    state.nonGitDirs = data.non_git_dirs || [];
    const visible = getVisibleRepos();
    const nextRepoId =
      visible.find((repo) => repo.id === state.activeRepoId)?.id ||
      state.repos.find((repo) => repo.id === state.activeRepoId)?.id ||
      visible[0]?.id ||
      state.repos[0]?.id ||
      null;
    state.activeRepoId = nextRepoId;
    persistUiState();
    resetPreview(state.activeRepoId);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function scanWorkspaceWithSync(fetchRemote = false) {
  const path = pathInput.value.trim();
  if (!path) {
    showError(t("error.enterWorkspacePath"));
    return;
  }

  showError("");
  setBusy(true);
  try {
    const data = await requestJson("/api/scan", {
      method: "POST",
      body: JSON.stringify({ path, fetch_remote: fetchRemote }),
    });
    persistWorkspacePath(path);
    state.repos = data.repos || [];
    state.nonGitDirs = data.non_git_dirs || [];
    const visible = getVisibleRepos();
    const nextRepoId =
      visible.find((repo) => repo.id === state.activeRepoId)?.id ||
      state.repos.find((repo) => repo.id === state.activeRepoId)?.id ||
      visible[0]?.id ||
      state.repos[0]?.id ||
      null;
    state.activeRepoId = nextRepoId;
    persistUiState();
    resetPreview(state.activeRepoId);
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function selectFolder() {
  showError("");
  setSelecting(true);
  try {
    const data = await requestJson("/api/select-folder", { method: "POST" });
    if (data.path) {
      pathInput.value = data.path;
      await scan();
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setSelecting(false);
  }
}

async function runRepoAction(repoId, action) {
  showError("");
  setBusy(true, repoId);
  try {
    const data = await requestJson(`/api/repos/${repoId}/${action}`, {
      method: "POST",
    });
    if (data.repo) {
      updateRepo(data.repo);
    }
    if (!data.success) {
      const result = data.result || {};
      showError(
        result.stderr || result.stdout || t("error.runActionFailed", { action })
      );
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false, repoId);
  }
}

async function pushOriginMain(repoId) {
  showError("");
  setBusy(true, repoId);
  try {
    const data = await requestJson(`/api/repos/${repoId}/push-origin-main`, {
      method: "POST",
    });
    if (data.repo) {
      updateRepo(data.repo);
    }
    if (!data.success) {
      const result = data.result || {};
      showError(result.stderr || result.stdout || t("error.runActionFailed", { action: "push origin main" }));
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false, repoId);
  }
}

async function refreshAllRepos(fetchRemote = false) {
  await scanWorkspaceWithSync(fetchRemote);
}

async function openRepo(repoId) {
  showError("");
  try {
    await requestJson(`/api/repos/${repoId}/open`, { method: "POST" });
  } catch (error) {
    showError(error.message);
  }
}

async function checkoutRepo(repoId, branch) {
  const repo = state.repos.find((item) => item.id === repoId);
  if (!branch || !repo || branch === repo.branch) {
    return;
  }

  if (
    repo.dirty &&
    !window.confirm(t("confirm.checkoutDirty", { repo: repo.name, branch }))
  ) {
    return;
  }

  showError("");
  setBusy(true, repoId);
  try {
    const data = await requestJson(`/api/repos/${repoId}/checkout`, {
      method: "POST",
      body: JSON.stringify({ branch }),
    });
    if (data.repo) {
      updateRepo(data.repo);
    }
    if (!data.success) {
      const result = data.result || {};
      showError(result.stderr || result.stdout || t("error.checkoutFailed"));
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false, repoId);
  }
}

async function commitRepo(repoId) {
  const input = document.querySelector(`[data-commit-input="${repoId}"]`);
  const message = input?.value.trim() || "";
  if (!message) {
    showError(t("error.commitMessageRequired"));
    return;
  }

  showError("");
  setBusy(true, repoId);
  try {
    const data = await requestJson(`/api/repos/${repoId}/commit`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    if (data.repo) {
      updateRepo(data.repo);
    }
    if (data.success && input) {
      input.value = "";
    } else if (!data.success) {
      const result = data.result || {};
      showError(result.stderr || result.stdout || t("error.commitFailed"));
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false, repoId);
  }
}

async function previewFile(repoId, path, scope) {
  state.preview = {
    repoId,
    path,
    scope,
    mode: "diff",
    panelMode: state.preview.panelMode === "full" ? "full" : "split",
    content: "",
    loading: true,
    error: "",
  };
  render();

  try {
    const data = await requestJson(`/api/repos/${repoId}/files/preview`, {
      method: "POST",
      body: JSON.stringify({ path, scope }),
    });
    state.preview = {
      repoId,
      path,
      scope,
      mode: data.mode || "diff",
      panelMode: state.preview.panelMode === "full" ? "full" : "split",
      content: data.content || "",
      loading: false,
      error: data.success ? "" : data.stderr || t("error.previewFailed"),
    };
  } catch (error) {
    state.preview = {
      repoId,
      path,
      scope,
      mode: "diff",
      panelMode: state.preview.panelMode === "full" ? "full" : "split",
      content: "",
      loading: false,
      error: error.message,
    };
    showError(error.message);
  }

  render();
}

async function runFileAction(repoId, path, action, scope = "") {
  showError("");
  setBusy(true, repoId);
  try {
    const data = await requestJson(`/api/repos/${repoId}/files/action`, {
      method: "POST",
      body: JSON.stringify({ path, action }),
    });
    if (data.repo) {
      updateRepo(data.repo);
    }
    if (!data.success) {
      const result = data.result || {};
      showError(
        result.stderr || result.stdout || t("error.runActionFailed", { action })
      );
    } else if (action !== "open") {
      resetPreview(repoId);
      if (scope && path) {
        const next = findFileScope(data.repo, path);
        if (next) {
          await previewFile(repoId, path, next);
          return;
        }
      }
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false, repoId);
  }
}

async function runBulkFileAction(repoId, scope, action) {
  showError("");
  setBusy(true, repoId);
  try {
    const data = await requestJson(`/api/repos/${repoId}/files/bulk-action`, {
      method: "POST",
      body: JSON.stringify({ scope, action }),
    });
    if (data.repo) {
      updateRepo(data.repo);
    }
    if (!data.success) {
      const result = data.result || {};
      showError(
        result.stderr || result.stdout || t("error.runActionFailed", { action })
      );
    } else {
      resetPreview(repoId);
    }
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false, repoId);
  }
}

async function exportRepoState(repoId) {
  const repo = state.repos.find((item) => item.id === repoId);
  if (!repo) {
    return;
  }

  showError("");
  setSnapshotTransfer(repoId, "export");
  try {
    await downloadFile(
      `/api/repos/${repoId}/export-state`,
      `${repo.name}-working-tree-snapshot.zip`
    );
  } catch (error) {
    showError(error.message);
  } finally {
    setSnapshotTransfer();
  }
}

function chooseSnapshotFile(repoId) {
  if (!importSnapshotInput) {
    showError(t("error.importFileRequired"));
    return;
  }
  importSnapshotInput.value = "";
  importSnapshotInput.dataset.repoId = repoId;
  importSnapshotInput.click();
}

async function importRepoState(repoId, file) {
  if (!file) {
    showError(t("error.importFileRequired"));
    return;
  }

  if (!window.confirm(t("confirm.importState"))) {
    return;
  }

  const formData = new FormData();
  formData.append("snapshot", file);

  showError("");
  setSnapshotTransfer(repoId, "import");
  try {
    const response = await fetch(withBasePath(`/api/repos/${repoId}/import-state`), {
      method: "POST",
      body: formData,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.message || t("error.requestFailed"));
    }
    if (data.repo) {
      updateRepo(data.repo);
    }
    resetPreview(repoId);
  } catch (error) {
    showError(error.message);
  } finally {
    setSnapshotTransfer();
  }
}

function render() {
  const locked = state.busy || state.selecting;
  selectButton.disabled = locked;
  scanButton.disabled = locked;
  addRepositoryButton.disabled = locked;
  applyStaticTranslations();
  selectButton.textContent = state.selecting
    ? t("workspace.selecting")
    : t("workspace.select");
  scanButton.textContent =
    state.busy && !state.activeRepoId
      ? t("workspace.scanning")
      : t("workspace.scan");
  document.documentElement.dataset.theme = state.theme;
  themeButton.classList.toggle("theme-dark", state.theme === "dark");
  themeButton.classList.toggle("theme-light", state.theme !== "dark");
  languageButton.textContent = t("language.buttonLabel");
  languageButton.setAttribute(
    "aria-label",
    state.language === "zh"
      ? t("language.switchToEn")
      : t("language.switchToZh")
  );
  languageButton.setAttribute(
    "title",
    state.language === "zh"
      ? t("language.switchToEn")
      : t("language.switchToZh")
  );
  languageButton.dataset.tip =
    state.language === "zh"
      ? t("language.switchToEn")
      : t("language.switchToZh");
  themeButton.setAttribute(
    "aria-label",
    state.theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark")
  );
  themeButton.setAttribute("title", t("theme.switch"));
  themeButton.dataset.tip =
    state.theme === "dark" ? t("theme.switchToLight") : t("theme.switchToDark");
  themeButton.setAttribute(
    "aria-pressed",
    state.theme === "dark" ? "true" : "false"
  );
  if (globalLoading && globalLoadingText) {
    const visible = Boolean(state.snapshotTransfer.action);
    globalLoading.hidden = !visible;
    globalLoadingText.textContent =
      state.snapshotTransfer.action === "import"
        ? t("loading.importState")
        : t("loading.exportState");
  }

  renderTabs();
  renderSidebar();
  renderRepoDetail();
  renderNonGit();
}

function renderTabs() {
  tabs.forEach((tab) => {
    const isActive = tab.dataset.tab === state.activeTab;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-current", isActive ? "page" : "false");
  });

  panels.forEach((panel) => {
    const visibleTabs = panel.dataset.panel.split(" ");
    panel.hidden = !visibleTabs.includes(state.activeTab);
  });
}

function renderSidebar() {
  const visibleRepos = getFilteredRepos(getVisibleRepos());
  if (
    visibleRepos.length &&
    !visibleRepos.some((repo) => repo.id === state.activeRepoId)
  ) {
    state.activeRepoId = visibleRepos[0].id;
    persistActiveRepoId(state.activeRepoId);
  }

  if (visibleRepos.length === 0) {
    sidebarRepoList.className = "sidebar-repo-list empty";
    sidebarRepoList.textContent = state.repos.length
      ? t("state.noMatchingRepos")
      : t("state.notScanned");
    return;
  }

  sidebarRepoList.className = "sidebar-repo-list";
  sidebarRepoList.innerHTML = visibleRepos
    .map((repo) => {
      const localBranches = repo.local_branches || [];
      const remoteBranches = repo.remote_branches || [];
      const attentionCount =
        Number(repo.ahead || 0) +
        Number(repo.behind || 0) +
        Number(repo.changed_files || 0) +
        Number(repo.untracked_files || 0);
      const badge =
        repo.status === "clean"
          ? ""
          : `<span class="repo-badge">${attentionCount || 1}</span>`;
      return `
        <button class="sidebar-repo ${
          repo.id === state.activeRepoId ? "active" : ""
        }" type="button" data-repo-id="${repo.id}">
          <span class="repo-dot dot-${escapeHtml(repo.status)}"></span>
          <span class="sidebar-repo-copy">
            <strong>${escapeHtml(repo.name)}</strong>
            <small>${escapeHtml(repo.branch || "-")} · ${
        localBranches.length
      }/${remoteBranches.length}</small>
          </span>
          ${badge}
          <span class="chevron">›</span>
        </button>
      `;
    })
    .join("");
}

function renderRepoDetail() {
  const repo = getActiveRepo();
  if (!repo) {
    repoDetail.innerHTML = `<div class="empty-state">${escapeHtml(
      t("state.noRepoSelected")
    )}</div>`;
    return;
  }

  const isBusy = state.busy && state.activeRepoId === repo.id;
  const isSnapshotBusy = state.snapshotTransfer.repoId === repo.id;
  const snapshotAction = state.snapshotTransfer.action;
  const anyBusy = state.busy || state.selecting;
  const repoBusy = anyBusy || isSnapshotBusy;
  const localBranches = repo.local_branches || [];
  const remoteBranches = repo.remote_branches || [];
  const stagedFiles = normalizeFileEntries(repo.staged_files, "staged");
  const unstagedFiles = normalizeFileEntries(repo.unstaged_files, "unstaged");
  const untrackedFiles = normalizeFileEntries(repo.untracked_list, "untracked");

  const hasPreview =
    state.preview.repoId === repo.id &&
    Boolean(state.preview.path) &&
    state.preview.panelMode !== "hidden";
  const previewMode = hasPreview ? state.preview.panelMode : "hidden";

  repoDetail.innerHTML = `
    <section class="panel action-panel">
      <div class="panel-header action-header">
        <div>
          <h2>${escapeHtml(repo.name)}</h2>
          <p>${escapeHtml(repo.path)}</p>
        </div>
        <span class="status-pill status-${escapeHtml(
          repo.status
        )}">${escapeHtml(labelFor("status", repo.status))}</span>
      </div>
      <div class="actions">
        <div class="action-row action-row-commit">
        <input data-commit-input="${
          repo.id
        }" type="text" placeholder="${escapeHtml(
    t("repo.commitPlaceholder")
  )}" ${repoBusy ? "disabled" : ""}>
          <button class="primary" type="button" data-action="commit" data-repo-id="${
            repo.id
          }" ${repoBusy ? "disabled" : ""}>${escapeHtml(t("repo.commit"))}</button>
        </div>
        <div class="action-row action-row-secondary">
          <div class="action-group">
            <button type="button" data-action="push" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.push"))}</button>
            <button type="button" data-action="push-origin-main" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.pushOriginMain"))}</button>
            <button type="button" data-action="pull" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.pull"))}</button>
            <button type="button" data-action="fetch" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.fetch"))}</button>
            <button type="button" data-action="open" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.open"))}</button>
            <button type="button" data-action="refresh" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.refresh"))}</button>
          </div>
          <div class="action-group action-group-snapshot">
            <button type="button" data-action="export-state" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.exportState"))}</button>
            <button type="button" data-action="import-state" data-repo-id="${repo.id}" ${
    repoBusy ? "disabled" : ""
  }>${escapeHtml(t("repo.importState"))}</button>
          </div>
        </div>
      </div>
      ${
        isSnapshotBusy
          ? `<p class="repo-message">${escapeHtml(
              snapshotAction === "import"
                ? t("repo.importingState")
                : t("repo.exportingState")
            )}</p>`
          : isBusy
          ? `<p class="repo-message">${escapeHtml(t("repo.processing"))}</p>`
          : `<p class="repo-message">${escapeHtml(repo.message || "")}</p>`
      }
    </section>

    <section class="panel changes-panel">
      <h2>${escapeHtml(t("repo.branches"))}</h2>
      <div class="branch-grid">
        ${branchBlock(
          t("branch.local"),
          localBranches,
          repo.branch,
          repo.id,
          repoBusy
        )}
        ${branchBlock(
          t("branch.remote"),
          remoteBranches,
          repo.branch,
          repo.id,
          repoBusy
        )}
      </div>
    </section>

    <section class="panel status-panel">
      <div class="panel-header">
        <div>
          <h2>${escapeHtml(t("repo.workingTree"))}</h2>
          <p>${escapeHtml(t("repo.clickToPreview"))}</p>
        </div>
      </div>
      <div class="working-tree-layout mode-${previewMode}">
        <div class="working-tree-sidebar">
          ${fileListCard({
            title: t("scope.staged"),
            scope: "staged",
            files: stagedFiles,
            anyBusy: repoBusy,
            headerActions: [
              {
                label: t("files.unstageAll"),
                action: "unstage_all",
                danger: false,
              },
            ],
            itemActions: ["view", "unstage"],
          })}
          ${fileListCard({
            title: t("scope.unstaged"),
            scope: "unstaged",
            files: unstagedFiles,
            anyBusy: repoBusy,
            headerActions: [
              {
                label: t("files.stageAll"),
                action: "stage_all",
                danger: false,
              },
              {
                label: t("files.discardAll"),
                action: "discard_all",
                danger: true,
              },
            ],
            itemActions: ["view", "stage", "discard"],
          })}
          ${fileListCard({
            title: t("scope.untracked"),
            scope: "untracked",
            files: untrackedFiles,
            anyBusy: repoBusy,
            headerActions: [
              { label: t("files.addAll"), action: "add_all", danger: false },
              {
                label: t("files.deleteAll"),
                action: "delete_all",
                danger: true,
              },
            ],
            itemActions: ["view", "add", "delete", "ignore"],
          })}
        </div>
        ${hasPreview ? previewPanel(repo.id) : ""}
      </div>
    </section>
  `;
}

function renderNonGit() {
  if (state.nonGitDirs.length === 0) {
    nonGitList.className = "non-git-list empty";
    nonGitList.textContent = t("state.none");
    return;
  }

  nonGitList.className = "non-git-list";
  nonGitList.innerHTML = state.nonGitDirs
    .map(
      (item) => `
        <div class="non-git-item">
          <p class="non-git-name">${escapeHtml(item.name)}</p>
          <p class="non-git-path">${escapeHtml(item.path)}</p>
        </div>
      `
    )
    .join("");
}

function getActiveRepo() {
  return state.repos.find((repo) => repo.id === state.activeRepoId) || null;
}

function getVisibleRepos() {
  if (state.activeTab === "branches") {
    return state.repos.filter((repo) => {
      const localBranches = repo.local_branches || [];
      const remoteBranches = repo.remote_branches || [];
      return localBranches.length > 1 || remoteBranches.length > 1;
    });
  }
  if (state.activeTab === "repositories") {
    return state.repos.filter((repo) => repo.dirty || repo.untracked);
  }
  if (state.activeTab === "sync") {
    return state.repos.filter((repo) => repo.status !== "clean");
  }
  return state.repos;
}

function getFilteredRepos(repos) {
  const query = state.filter.trim().toLowerCase();
  if (!query) {
    return repos;
  }
  return repos.filter((repo) =>
    `${repo.name} ${repo.path} ${repo.branch}`.toLowerCase().includes(query)
  );
}

function fileListCard({
  title,
  scope,
  files,
  anyBusy,
  headerActions,
  itemActions,
}) {
  const isExpanded = Boolean(state.workingTreeSections[scope]);
  const headerButtons = headerActions
    .map(
      (item) => `
      <button
        class="${item.danger ? "danger" : ""}"
        type="button"
        data-bulk-action="${item.action}"
        data-scope="${scope}"
        ${anyBusy || files.length === 0 ? "disabled" : ""}>
        ${escapeHtml(item.label)}
      </button>
    `
    )
    .join("");

  const content = files.length
    ? buildFileTreeRows(files, scope, itemActions, anyBusy)
    : `<div class="file-list-empty-card">${escapeHtml(
        t("state.emptyNow")
      )}</div>`;

  return `
    <section class="file-card ${isExpanded ? "expanded" : "collapsed"}">
      <div class="file-card-header">
        <button
          class="file-card-toggle-hit"
          type="button"
          data-section-toggle="${scope}"
          aria-expanded="${isExpanded ? "true" : "false"}"
        >
          <div class="file-card-summary">
          <span class="file-card-label">${escapeHtml(title)}</span>
          <strong class="file-card-count">${files.length}</strong>
          </div>
          <span class="file-card-toggle">${isExpanded ? "▾" : "▸"}</span>
        </button>
        <div class="file-card-header-right">
          <div class="file-card-actions">${headerButtons}</div>
        </div>
      </div>
      ${isExpanded ? `<div class="file-row-list">${content}</div>` : ""}
    </section>
  `;
}

function buildFileTreeRows(files, scope, itemActions, anyBusy) {
  const root = new Map();

  files.forEach((file) => {
    const parts = file.path.split("/").filter(Boolean);
    let cursor = root;

    parts.forEach((part, index) => {
      const isLeaf = index === parts.length - 1;
      if (!cursor.has(part)) {
        cursor.set(part, {
          type: isLeaf ? "file" : "dir",
          name: part,
          file: isLeaf ? file : null,
          children: isLeaf ? null : new Map(),
        });
      }
      const node = cursor.get(part);
      if (isLeaf) {
        node.file = file;
      } else {
        cursor = node.children;
      }
    });
  });

  return renderTreeNodes(
    Array.from(root.values()),
    scope,
    itemActions,
    anyBusy,
    0
  );
}

function renderTreeNodes(nodes, scope, itemActions, anyBusy, depth) {
  return nodes
    .sort((left, right) => {
      if (left.type !== right.type) {
        return left.type === "dir" ? -1 : 1;
      }
      return left.name.localeCompare(right.name);
    })
    .map((node) => {
      if (node.type === "dir") {
        const children = renderTreeNodes(
          Array.from(node.children.values()),
          scope,
          itemActions,
          anyBusy,
          depth + 1
        );
        return `
          <div class="tree-node">
            <div class="tree-row tree-dir-row" style="--depth:${depth}">
              <span class="tree-caret">▾</span>
              <span class="tree-folder">▸</span>
              <span class="tree-label">${escapeHtml(node.name)}</span>
            </div>
            ${children}
          </div>
        `;
      }
      return fileRow(node.file, scope, itemActions, anyBusy, depth);
    })
    .join("");
}

function fileRow(file, scope, itemActions, anyBusy, depth = 0) {
  const isActivePreview =
    state.preview.repoId === state.activeRepoId &&
    state.preview.path === file.path &&
    state.preview.scope === scope;
  const actions = itemActions
    .map((action) => fileActionButton(action, file, scope, anyBusy))
    .join("");

  return `
    <div class="file-row ${
      isActivePreview ? "active" : ""
    }" data-path="${escapeHtml(
    file.path
  )}" data-scope="${scope}" style="--depth:${depth}">
      <button
        class="file-main"
        type="button"
        data-preview-path="${escapeHtml(file.path)}"
        data-preview-scope="${scope}"
        title="${escapeHtml(file.path)}">
        <span class="tree-spacer"></span>
        <span class="file-main-status">${escapeHtml(file.status)}</span>
        <span class="file-main-copy">
          <span class="file-main-name">${escapeHtml(file.name)}</span>
        </span>
      </button>
      <div class="file-row-actions">${actions}</div>
    </div>
  `;
}

function fileActionButton(action, file, scope, anyBusy) {
  const config = {
    view: { label: t("files.view"), action: "", className: "wt-view" },
    stage: { label: t("files.stage"), action: "stage", className: "wt-stage" },
    discard: {
      label: t("files.discard"),
      action: "discard",
      className: "danger-text wt-discard",
    },
    unstage: {
      label: t("files.unstage"),
      action: "unstage",
      className: "wt-unstage",
    },
    add: { label: t("files.add"), action: "add", className: "wt-add" },
    delete: {
      label: t("files.delete"),
      action: "delete",
      className: "danger-text wt-delete",
    },
    ignore: {
      label: t("files.ignore"),
      action: "ignore",
      className: "wt-ignore",
    },
  }[action];

  if (!config) {
    return "";
  }

  if (action === "view") {
    return `
      <button
        class="file-action-button ${config.className}"
        type="button"
        data-preview-path="${escapeHtml(file.path)}"
        data-preview-scope="${scope}"
        title="${config.label}"
        aria-label="${config.label}">
        <span class="action-icon action-${action}" aria-hidden="true"></span>
      </button>
    `;
  }

  return `
    <button
      class="file-action-button ${config.className}"
      type="button"
      data-file-action="${config.action}"
      data-file-path="${escapeHtml(file.path)}"
      data-file-scope="${scope}"
      title="${config.label}"
      aria-label="${config.label}"
      ${anyBusy ? "disabled" : ""}>
      <span class="action-icon action-${action}" aria-hidden="true"></span>
    </button>
  `;
}

function previewPanel(repoId) {
  const title = `${state.preview.path} · ${labelFor(
    "scope",
    state.preview.scope
  )}`;
  let body = "";

  if (state.preview.loading) {
    body = `<div class="preview-body empty-state">${escapeHtml(
      t("preview.loading")
    )}</div>`;
  } else if (state.preview.error) {
    body = `<div class="preview-body preview-error">${escapeHtml(
      state.preview.error
    )}</div>`;
  } else {
    body = `<div class="preview-body">${renderPreviewContent(
      state.preview
    )}</div>`;
  }

  return `
    <aside class="preview-panel">
      <div class="preview-header">
        <h3>${escapeHtml(title)}</h3>
        <div class="preview-toolbar">
          <button class="preview-toggle ${
            state.preview.panelMode === "split" ? "active" : ""
          }" type="button" data-preview-mode="split">${escapeHtml(
    t("preview.split")
  )}</button>
          <button class="preview-toggle ${
            state.preview.panelMode === "full" ? "active" : ""
          }" type="button" data-preview-mode="full">${escapeHtml(
    t("preview.full")
  )}</button>
          <button class="preview-toggle" type="button" data-preview-mode="hidden">${escapeHtml(
            t("preview.hide")
          )}</button>
        </div>
      </div>
      ${body}
    </aside>
  `;
}

function renderPreviewContent(preview) {
  const lines = (preview.content || "").split("\n");
  if (!preview.content) {
    return `<div class="empty-state">${escapeHtml(t("preview.empty"))}</div>`;
  }

  const rows = lines
    .map((line) => {
      let className = "preview-line";
      if (preview.mode === "diff") {
        if (line.startsWith("+") && !line.startsWith("+++")) {
          className += " added";
        } else if (line.startsWith("-") && !line.startsWith("---")) {
          className += " removed";
        } else if (
          line.startsWith("@@") ||
          line.startsWith("diff --git") ||
          line.startsWith("index ") ||
          line.startsWith("---") ||
          line.startsWith("+++")
        ) {
          className += " meta";
        }
      }
      return `<div class="${className}">${escapeHtml(line) || "&nbsp;"}</div>`;
    })
    .join("");

  return `<div class="preview-code">${rows}</div>`;
}

function branchBlock(label, branches, currentBranch, repoId, disabled) {
  const content = branches.length
    ? branches
        .map((branch) => {
          const isCurrent =
            branch === currentBranch || branch.endsWith(`/${currentBranch}`);
          return `
            <button
              class="branch-chip ${isCurrent ? "active" : ""}"
              type="button"
              data-action="checkout"
              data-repo-id="${repoId}"
              data-branch="${escapeHtml(branch)}"
              ${disabled || isCurrent ? "disabled" : ""}>
              ${escapeHtml(branch)}
            </button>
          `;
        })
        .join("")
    : `<span class="branch-empty">${escapeHtml(t("branch.empty"))}</span>`;

  return `
    <div class="branch-block">
      <span class="branch-label">${escapeHtml(label)}</span>
      <div class="branch-list">${content}</div>
    </div>
  `;
}

function findFileScope(repo, path) {
  if (!repo || !path) {
    return "";
  }
  const staged = normalizeFileEntries(repo.staged_files, "staged");
  if (staged.some((item) => item.path === path)) {
    return "staged";
  }
  const unstaged = normalizeFileEntries(repo.unstaged_files, "unstaged");
  if (unstaged.some((item) => item.path === path)) {
    return "unstaged";
  }
  const untracked = normalizeFileEntries(repo.untracked_list, "untracked");
  if (untracked.some((item) => item.path === path)) {
    return "untracked";
  }
  return "";
}

function getDangerPrompt(action, scope, count, filePath = "") {
  if (action === "discard") {
    return t("confirm.discardFile", { file: filePath });
  }
  if (action === "delete") {
    return t("confirm.deleteFile", { file: filePath });
  }
  if (action === "discard_all") {
    return t("confirm.discardAll", { count });
  }
  if (action === "delete_all") {
    return t("confirm.deleteAll", { count });
  }
  return "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

selectButton.addEventListener("click", selectFolder);
scanButton.addEventListener("click", scan);
addRepositoryButton.addEventListener("click", selectFolder);
themeButton.addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem(STORAGE_KEYS.theme, state.theme);
  render();
});
languageButton.addEventListener("click", () => {
  state.language = state.language === "zh" ? "en" : "zh";
  localStorage.setItem(STORAGE_KEYS.language, state.language);
  render();
});
importSnapshotInput.addEventListener("change", async () => {
  const repoId = importSnapshotInput.dataset.repoId;
  const file = importSnapshotInput.files?.[0] || null;
  if (!repoId) {
    return;
  }
  await importRepoState(repoId, file);
  importSnapshotInput.value = "";
});
filterInput.addEventListener("input", () => {
  state.filter = filterInput.value;
  render();
});
tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    state.activeTab = tab.dataset.tab;
    persistUiState();
    render();
  });
});
pathInput.addEventListener("input", () => {
  persistWorkspacePath(pathInput.value.trim());
});
pathInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    scan();
  }
});

sidebarRepoList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-repo-id]");
  if (!button) {
    return;
  }
  state.activeRepoId = button.dataset.repoId;
  persistActiveRepoId(state.activeRepoId);
  resetPreview(state.activeRepoId);
  render();
});

repoDetail.addEventListener("dblclick", (event) => {
  const row = event.target.closest(".file-row");
  if (!row) {
    return;
  }
  const repo = getActiveRepo();
  if (!repo) {
    return;
  }
  runFileAction(repo.id, row.dataset.path, "open");
});

document.querySelector(".detail").addEventListener("click", async (event) => {
  const repo = getActiveRepo();
  if (!repo) {
    return;
  }

  const previewClose = event.target.closest("[data-preview-close]");
  if (previewClose) {
    resetPreview(repo.id);
    render();
    return;
  }

  const previewModeTarget = event.target.closest("[data-preview-mode]");
  if (previewModeTarget) {
    const nextMode = previewModeTarget.dataset.previewMode;
    if (nextMode === "hidden") {
      setPreviewPanelMode("hidden");
    } else if (state.preview.path) {
      setPreviewPanelMode(nextMode);
    }
    render();
    return;
  }

  const sectionToggle = event.target.closest("[data-section-toggle]");
  if (sectionToggle) {
    const scope = sectionToggle.dataset.sectionToggle;
    state.workingTreeSections[scope] = !state.workingTreeSections[scope];
    persistWorkingTreeSections();
    render();
    return;
  }

  const previewTarget = event.target.closest("[data-preview-path]");
  if (previewTarget) {
    const nextPath = previewTarget.dataset.previewPath;
    const nextScope = previewTarget.dataset.previewScope;
    const isSamePreview =
      state.preview.repoId === repo.id &&
      state.preview.path === nextPath &&
      state.preview.scope === nextScope &&
      !state.preview.loading;
    if (isSamePreview) {
      setPreviewPanelMode(
        state.preview.panelMode === "hidden" ? "split" : "hidden"
      );
      render();
      return;
    }
    await previewFile(repo.id, nextPath, nextScope);
    return;
  }

  const bulkTarget = event.target.closest("[data-bulk-action]");
  if (bulkTarget) {
    const scope = bulkTarget.dataset.scope;
    const action = bulkTarget.dataset.bulkAction;
    const files =
      scope === "staged"
        ? normalizeFileEntries(repo.staged_files, "staged")
        : scope === "unstaged"
        ? normalizeFileEntries(repo.unstaged_files, "unstaged")
        : normalizeFileEntries(repo.untracked_list, "untracked");
    const prompt = getDangerPrompt(action, scope, files.length);
    if (prompt && !window.confirm(prompt)) {
      return;
    }
    await runBulkFileAction(repo.id, scope, action);
    return;
  }

  const fileActionTarget = event.target.closest("[data-file-action]");
  if (fileActionTarget) {
    const action = fileActionTarget.dataset.fileAction;
    const path = fileActionTarget.dataset.filePath;
    const scope = fileActionTarget.dataset.fileScope;
    const prompt = getDangerPrompt(action, scope, 1, path);
    if (prompt && !window.confirm(prompt)) {
      return;
    }
    await runFileAction(repo.id, path, action, scope);
    return;
  }

  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const repoId = button.dataset.repoId;
  const action = button.dataset.action;
  if (action === "checkout") {
    checkoutRepo(repoId, button.dataset.branch);
  } else if (action === "open") {
    openRepo(repoId);
  } else if (action === "export-state") {
    exportRepoState(repoId);
  } else if (action === "import-state") {
    chooseSnapshotFile(repoId);
  } else if (action === "commit") {
    commitRepo(repoId);
  } else if (action === "push-origin-main") {
    pushOriginMain(repoId);
  } else {
    runRepoAction(repoId, action);
  }
});

async function restoreWorkspace() {
  await loadConfig();
  const savedPath =
    localStorage.getItem(STORAGE_KEYS.workspacePath)?.trim() || "";
  const initialPath = savedPath || appConfig.default_workspace;
  if (!initialPath) {
    render();
    return;
  }
  pathInput.value = initialPath;
  await scan();
}

restoreWorkspace();
