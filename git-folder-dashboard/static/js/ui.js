import {
  state,
  activeRepo,
  visibleRepos,
  taskItem,
  hasError,
} from "./state.js";
import { t, relativeTime } from "./i18n.js";

export const $ = (id) => document.getElementById(id);
export const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
export const icon = (name, extra = "") =>
  `<svg class="icon ${extra}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const htmlCache = new WeakMap();
function patch(id, html) {
  const node = $(id);
  if (htmlCache.get(node) === html) return;
  // Scroll positions and open command-output details survive incremental updates.
  const scroll = [node.scrollTop, node.scrollLeft];
  const openDetails = [...node.querySelectorAll("details")].map(
    (item) => item.open,
  );
  node.innerHTML = html;
  node.scrollTop = scroll[0];
  node.scrollLeft = scroll[1];
  node.querySelectorAll("details").forEach((item, index) => {
    item.open = openDetails[index] || false;
  });
  htmlCache.set(node, html);
}
function title(node, value) {
  node.title = value;
  node.setAttribute("aria-label", value);
}
const countChanges = (repo) =>
  (repo.changed_files || 0) + (repo.untracked_files || 0);
const badge = (text, kind = "neutral") =>
  `<span class="badge ${kind}">${text}</span>`;
const empty = (name, heading, hint = "") =>
  `<div class="empty-state">${icon(name)}<h3>${escape(heading)}</h3>${hint ? `<p>${escape(hint)}</p>` : ""}</div>`;
function iconButton(action, name, label, attributes = "", disabled = false) {
  return `<button type="button" class="icon-button small" data-action="${action}" title="${escape(label)}" aria-label="${escape(label)}" ${attributes} ${disabled ? "disabled" : ""}>${icon(name)}</button>`;
}
function localLabel(repo) {
  if (repo.pending) return `<span class="muted">${t("pending")}</span>`;
  if (repo.status === "error") return badge(escape(t("error")), "danger");
  return repo.dirty
    ? badge(escape(t("files", { count: countChanges(repo) })), "warning")
    : `<span class="clean-label">${icon("check")}${t("clean")}</span>`;
}
export function remoteStale(repo) {
  return (
    !repo.fetched_at ||
    Date.now() - Date.parse(repo.fetched_at) > state.config.remote_ttl * 1000
  );
}
function remoteLabel(repo) {
  if (repo.pending) return "<span class=muted>—</span>";
  const counts = `${repo.ahead ? badge(`↑ ${repo.ahead}`, "accent") : ""}${repo.behind ? badge(`↓ ${repo.behind}`, "warning") : ""}`;
  if (repo.fetch_error)
    return `${counts}${badge(`${icon("alert")}${t("fetchFailed")}`, "danger")}`;
  if (!repo.has_remote) return `<span class="muted">${t("noRemote")}</span>`;
  if (!repo.has_upstream)
    return `<span class="muted">${t("noUpstream")}</span>`;
  return (
    counts ||
    `<span class="muted">${repo.fetched_at ? t("remoteCurrent") : t("remoteUnknown")}</span>`
  );
}
function notice(label, detail, retryAction, attributes = "") {
  return `<div class="notice-title">${icon("alert")}<strong>${escape(label)}</strong>${retryAction ? `<button class="text-button" data-action="${retryAction}" ${attributes}>${t("retry")}</button>` : ""}</div>${detail ? `<details class="error-details"><summary>${t("details")}</summary><pre>${escape(detail)}</pre></details>` : ""}`;
}

function renderChrome() {
  document.documentElement.dataset.theme = state.theme;
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
  $("workspaceName").textContent = state.path
    ? state.path.split(/[\\/]/).filter(Boolean).pop()
    : t("selectWorkspace");
  $("workspacePath").textContent = state.path || "";
  title($("workspaceButton"), state.path || t("selectWorkspace"));
  patch("refreshAll", `${icon("refresh")}<span>${t("refreshAll")}</span>`);
  patch("fetchAll", `${icon("down")}<span>${t("fetchAll")}</span>`);
  title($("refreshAll"), t("refreshAll"));
  title($("fetchAll"), t("fetchAll"));
  $("refreshAll").disabled = !state.path || state.workspaceBusy;
  $("fetchAll").disabled = !state.path || state.workspaceBusy;
  const running = state.tasks.filter(
    (task) => task.status === "running" && task.generation === state.generation,
  );
  patch(
    "tasksButton",
    `${icon("activity", running.length ? "pulse" : "")}${running.length ? '<span class="task-dot"></span>' : ""}`,
  );
  title($("tasksButton"), t("tasks"));
  $("tasksButton").setAttribute("aria-expanded", String(state.tasksOpen));
  patch("themeButton", icon(state.theme === "dark" ? "sun" : "moon"));
  title($("themeButton"), t("theme"));
  $("languageButton").textContent = state.language === "zh" ? "EN" : "中";
  title($("languageButton"), t("language"));
  patch(
    "overviewButton",
    `${icon("grid")}<span>${t("overview")}</span>${icon("chevron")}`,
  );
  $("overviewButton").classList.toggle("active", state.view === "overview");
  $("reposLabel").textContent = t("repositories");
  $("repoCount").textContent = state.repos.length;
  patch("changeWorkspace", icon("plus"));
  title($("changeWorkspace"), t("changeWorkspace"));
  $("searchInput").placeholder = t("search");
  title($("searchInput"), t("search"));
  patch(
    "repoFilters",
    ["all", "modified", "sync", "error"]
      .map(
        (filter) =>
          `<button data-action="filter" data-filter="${filter}" class="${state.filter === filter || (filter === "sync" && ["push", "pull"].includes(state.filter)) ? "active" : ""}" aria-pressed="${state.filter === filter}">${t(filter)}</button>`,
      )
      .join(""),
  );
  patch(
    "foldersButton",
    `${icon("folder")}<span>${t("folders")}</span><span class="count">${state.nonGitDirs.length}</span>`,
  );
  $("foldersButton").classList.toggle("active", state.view === "folders");
  patch(
    "syncPolicy",
    `${icon("clock")}<span>${state.config.sync_interval ? t("fetchPolicy", { seconds: state.config.sync_interval }) : t("manualPolicy")}</span>`,
  );
  $("overviewView").hidden = state.view !== "overview";
  $("repositoryView").hidden = state.view !== "repo";
  $("foldersView").hidden = state.view !== "folders";
  $("taskDrawer").hidden = !state.tasksOpen;
  $("tasksTitle").textContent = t("tasks");
  patch("closeTasks", icon("close"));
  title($("closeTasks"), t("close"));
  $("connectionNotice").hidden = !state.connectionError;
  if (state.connectionError)
    patch(
      "connectionNotice",
      `<div class="notice-title">${icon("alert")}<span>${t("connection")}</span><button class="text-button" data-action="reconnect">${t("connectionRetry")}</button></div>`,
    );
  $("statusLeft").textContent = state.path
    ? t("reposCount", { count: state.repos.length })
    : t("ready");
  const last =
    running[0] ||
    state.tasks.find((task) => task.generation === state.generation);
  patch(
    "statusRight",
    last
      ? `${icon(last.status === "running" ? "refresh" : last.failed ? "alert" : "check", last.status === "running" ? "spin" : "")}<span>${t(last.fetch_remote ? "taskFetch" : "taskRefresh")} · ${t("taskProgress", { done: last.completed, total: last.total })}${last.failed ? ` · ${t("failures", { count: last.failed })}` : ""}</span>`
      : `${icon("check")}<span>${t("ready")}</span>`,
  );
  $("taskProgress").hidden = !running.length;
  $("taskProgress").style.width = last?.total
    ? `${Math.max(3, (last.completed / last.total) * 100)}%`
    : "3%";
  $("workspaceTitle").textContent = t("selectWorkspace");
  $("workspaceDescription").textContent = t("workspaceDescription");
  $("pathLabel").textContent = t("path");
  $("pathInput").placeholder = t("pathPlaceholder");
  $("browseButton").textContent = t("browse");
  $("workspaceCancel").textContent = t("cancel");
  $("scanButton").textContent = state.workspaceBusy ? t("checking") : t("scan");
  $("scanButton").disabled = state.workspaceBusy;
  $("browseButton").disabled = state.workspaceBusy || state.selectingFolder;
  $("workspaceError").hidden = !state.workspaceError;
  $("workspaceError").textContent = state.workspaceError;
}

function renderSidebar() {
  const repos = visibleRepos();
  patch(
    "repoList",
    repos.length
      ? repos
          .map((repo) => {
            const item = taskItem(repo.id);
            const dot = item
              ? "busy"
              : hasError(repo)
                ? "error"
                : repo.dirty
                  ? "modified"
                  : "clean";
            return `<button class="repo-item ${state.view === "repo" && repo.id === state.activeRepoId ? "active" : ""}" data-action="select-repo" data-id="${repo.id}" title="${escape(repo.path)}"><span class="repo-icon ${dot}">${icon("branch")}</span><span class="repo-item-copy"><strong>${escape(repo.name)}</strong><small>${item ? t(item.status) : escape(repo.branch || "—")}</small></span><span class="repo-indicators">${repo.ahead ? `<span class="up">↑${repo.ahead}</span>` : ""}${repo.behind ? `<span class="down">↓${repo.behind}</span>` : ""}${repo.dirty ? `<span class="modified-number">${countChanges(repo)}</span>` : ""}${hasError(repo) ? icon("alert") : ""}</span></button>`;
          })
          .join("")
      : `<div class="sidebar-empty">${escape(state.path ? t("noMatches") : t("selectWorkspace"))}</div>`,
  );
}

function renderOverview() {
  if (!state.path) {
    patch(
      "overviewView",
      `<div class="welcome"><span class="welcome-icon">${icon("branch")}</span><span class="eyebrow">GIT FOLDER DASHBOARD</span><h1>${t("welcome")}</h1><p>${t("welcomeHint")}</p><button class="button primary" data-action="workspace">${icon("folder")}${t("selectWorkspace")}</button><span class="welcome-note">LOCAL FIRST · GIT POWERED</span></div>`,
    );
    return;
  }
  const stats = [
    ["all", "grid", "totalRepos", state.repos.length],
    [
      "modified",
      "file",
      "modifiedRepos",
      state.repos.filter((repo) => repo.dirty).length,
    ],
    [
      "push",
      "up",
      "pushRepos",
      state.repos.filter((repo) => repo.ahead).length,
    ],
    [
      "pull",
      "down",
      "pullRepos",
      state.repos.filter((repo) => repo.behind).length,
    ],
  ];
  const repos = visibleRepos();
  patch(
    "overviewView",
    `<div class="page-heading"><div><div class="eyebrow">${t("workspace")} / ${t("all")}</div><h1>${t("overview")}</h1><p>${t("overviewHint")}</p></div><span class="workspace-tag">${icon("folder")}${escape(state.path.split(/[\\/]/).pop())}</span></div><div class="stats-grid">${stats.map(([filter, glyph, label, count]) => `<button class="stat-card ${state.filter === filter ? "selected" : ""}" data-action="filter" data-filter="${filter}"><span class="stat-label">${t(label)}${icon(glyph)}</span><strong>${filter !== "all" && state.repos.some((repo) => repo.pending) ? "—" : count}<span>${t("repositories")}</span></strong></button>`).join("")}</div><div class="overview-table-card"><div class="section-heading"><h2>${t("repositories")}<span class="count">${repos.length}</span></h2><span class="muted">${t(state.filter === "push" ? "pushRepos" : state.filter === "pull" ? "pullRepos" : state.filter)}</span></div>${repos.length ? `<div class="table-scroll"><table class="repo-table"><thead><tr><th>${t("repository")}</th><th>${t("branch")}</th><th>${t("workingTree")}</th><th>${t("remote")}</th><th>${t("lastChecked")}</th><th></th></tr></thead><tbody>${repos.map((repo) => `<tr data-action="select-repo" data-id="${repo.id}" tabindex="0"><td><span class="table-repo-icon">${icon("branch")}</span><strong>${escape(repo.name)}</strong></td><td><span class="branch-name">${escape(repo.branch || "—")}</span></td><td>${localLabel(repo)}</td><td><div class="badge-group">${taskItem(repo.id) ? `<span class="task-label">${icon("refresh", "spin")}${t(taskItem(repo.id).status)}</span>` : remoteLabel(repo)}</div></td><td class="muted timestamp">${escape(relativeTime(repo.checked_at))}</td><td>${icon("chevron")}</td></tr>`).join("")}</tbody></table></div>` : empty("search", t(state.repos.length ? "noMatches" : "noRepos"), t(state.repos.length ? "noMatchesHint" : "noReposHint"))}</div>`,
  );
}

function renderRepo() {
  const repo = activeRepo();
  if (!repo) return;
  const busy = Boolean(state.busy[repo.id]);
  const job = taskItem(repo.id);
  const locked = busy || Boolean(job);
  const error = state.errors[repo.id];
  const fetched = repo.fetched_at
    ? t("remoteChecked", { time: relativeTime(repo.fetched_at) })
    : t("remoteUnknown");
  patch(
    "repoHeader",
    `<div class="repo-breadcrumb"><button data-action="overview">${t("workspace")}</button>${icon("chevron")}<span>${escape(repo.name)}</span></div><div class="repo-title-row"><div><h1>${escape(repo.name)}</h1><p class="repo-path" title="${escape(repo.path)}">${escape(repo.path)}</p></div><div class="repo-status-badges">${localLabel(repo)}${remoteLabel(repo)}</div></div><div class="freshness"><span>${icon("clock")}${t("localTime", { time: relativeTime(repo.checked_at) })}</span><span class="${repo.fetch_error ? "text-danger" : repo.has_remote && remoteStale(repo) ? "text-warning" : ""}">${icon("down")}${repo.has_remote ? (repo.fetch_error ? t("fetchFailed") : fetched) : t("noRemote")}${repo.has_remote && remoteStale(repo) && !repo.fetch_error ? ` · ${t("remoteStale")}` : ""}</span>${busy || job ? `<span class="task-label">${icon("refresh", "spin")}${busy ? t("processing", { action: t(state.busy[repo.id] === "commit" ? "commitAction" : state.busy[repo.id]) }) : t(job.status)}</span>` : ""}</div>`,
  );
  const repoError = error?.scope !== "commit" ? error : null;
  $("repoNotice").hidden = !(
    repoError ||
    repo.fetch_error ||
    repo.conflicts?.length ||
    repo.status === "error"
  );
  if (!$("repoNotice").hidden)
    patch(
      "repoNotice",
      repoError
        ? notice(
            t("operationFailed", { action: t(repoError.action) }),
            repoError.message,
            "retry-action",
          )
        : repo.fetch_error
          ? notice(t("fetchFailed"), repo.fetch_error, "fetch")
          : notice(
              repo.conflicts?.length ? t("conflicts") : t("error"),
              repo.message,
              "refresh",
            ),
    );
  const branches = `<optgroup label="${t("localBranches")}">${[
    ...new Set([repo.branch, ...(repo.local_branches || [])]),
  ]
    .filter(Boolean)
    .map(
      (branch) =>
        `<option value="${escape(branch)}" ${branch === repo.branch ? "selected" : ""}>${escape(branch)}</option>`,
    )
    .join(
      "",
    )}</optgroup><optgroup label="${t("remoteBranches")}">${(repo.remote_branches || []).map((branch) => `<option value="${escape(branch)}">${escape(branch)}</option>`).join("")}</optgroup>`;
  patch(
    "repoToolbar",
    `<label class="branch-select">${icon("branch")}<select id="branchSelect" aria-label="${t("branch")}" ${locked || repo.pending ? "disabled" : ""}>${branches}</select></label>${repo.upstream ? `<span class="tracking-label">→ ${escape(repo.upstream)}</span>` : ""}<div class="repo-toolbar-actions"><button class="button subtle" data-action="refresh" ${locked ? "disabled" : ""}>${icon("refresh")}${t("refresh")}</button><button class="button" data-action="fetch" ${locked || !repo.has_remote ? "disabled" : ""} title="${!repo.has_remote ? t("noRemote") : t("fetch")}">${icon("down")}${t("fetch")}</button><button class="button" data-action="pull" ${locked || !repo.has_upstream ? "disabled" : ""} title="${!repo.has_upstream ? t("noUpstreamHint") : t("pull")}">${icon("down")}${t("pull")}${repo.behind ? `<span class="button-count">${repo.behind}</span>` : ""}</button><button class="button primary" data-action="push" ${locked || !repo.has_upstream ? "disabled" : ""} title="${!repo.has_upstream ? t("noUpstreamHint") : `${t("push")} → ${escape(repo.upstream)}`}">${icon("up")}${t("push")}${repo.ahead ? `<span class="button-count">${repo.ahead}</span>` : ""}</button><details class="menu"><summary class="icon-button" aria-label="${t("more")}" title="${t("more")}">${icon("more")}</summary><div class="menu-popover"><button data-action="open" ${busy ? "disabled" : ""}>${icon("folder")}${t("openFolder")}</button><button data-action="export" ${locked ? "disabled" : ""}>${icon("up")}${t("export")}</button><button data-action="import" ${locked ? "disabled" : ""}>${icon("down")}${t("import")}</button></div></details></div>`,
  );
  if ($("branchSelect")) $("branchSelect").value = repo.branch || "";
  patch(
    "changesHeading",
    `<h2>${t("changes")}<span class="count">${countChanges(repo)}</span></h2>`,
  );
  const selection = state.selections[repo.id];
  patch(
    "changesList",
    repo.pending
      ? '<div class="skeleton-list"><i></i><i></i><i></i><i></i></div>'
      : !repo.dirty
        ? empty("check", t("noChanges"), t("noChangesHint"))
        : ["staged", "unstaged", "untracked"]
            .map((scope) => fileGroup(repo, scope, selection, locked))
            .join(""),
  );
  $("commitLabel").textContent = t("commitMessage");
  $("commitMessage").placeholder = t("commitPlaceholder");
  const textarea = $("commitMessage");
  if (textarea.dataset.repoId !== repo.id) {
    textarea.value = state.drafts[repo.id] || "";
    textarea.dataset.repoId = repo.id;
  }
  textarea.disabled = busy && state.busy[repo.id] === "commit";
  patch(
    "commitButton",
    `${icon("check")}<span>${busy && state.busy[repo.id] === "commit" ? t("processing", { action: t("commitAction") }) : t("commit", { count: repo.staged_files?.length || 0 })}</span>`,
  );
  $("commitButton").disabled =
    locked || !repo.staged_files?.length || Boolean(repo.conflicts?.length);
  $("commitButton").title = repo.conflicts?.length
    ? t("conflicts")
    : !repo.staged_files?.length
      ? t("noStaged")
      : "";
  patch("commitMore", icon("more"));
  title($("commitMore"), t("more"));
  $("commitAllButton").textContent = t("commitAll");
  $("commitAllButton").disabled =
    locked || !repo.dirty || Boolean(repo.conflicts?.length);
  $("commitHint").textContent = t("commitHint");
  $("commitError").hidden = error?.scope !== "commit";
  if (error?.scope === "commit")
    patch(
      "commitError",
      error.validation
        ? escape(error.message)
        : notice(t("commitFailed"), error.message, "retry-action"),
    );
  $("repositoryView").classList.toggle("diff-expanded", state.expanded);
  renderDiff(repo);
}

function fileGroup(repo, scope, selection, locked) {
  const files =
    repo[
      {
        staged: "staged_files",
        unstaged: "unstaged_files",
        untracked: "untracked_list",
      }[scope]
    ] || [];
  if (!files.length) return "";
  const opened = state.sections[`${repo.id}.${scope}`] !== false;
  const bulk =
    scope === "staged"
      ? ["unstage_all", "minus", "unstageAll"]
      : scope === "unstaged"
        ? ["stage_all", "plus", "stageAll"]
        : ["add_all", "plus", "stageAll"];
  const attributes = `data-scope="${scope}"`;
  let directory = null;
  return `<section class="file-group"><div class="file-group-heading"><button class="section-toggle" data-action="toggle-section" ${attributes} aria-expanded="${opened}">${icon("chevron", opened ? "rotate" : "")}<span>${t(scope)}</span><span class="count">${files.length}</span></button>${iconButton("bulk", bulk[1], t(bulk[2]), `${attributes} data-kind="${bulk[0]}"`, locked)}${scope !== "staged" ? iconButton("bulk", "trash", t(scope === "unstaged" ? "discardAll" : "deleteAll"), `${attributes} data-kind="${scope === "unstaged" ? "discard_all" : "delete_all"}"`, locked) : ""}</div>${
    opened
      ? `<div class="file-group-items">${[...files]
          .sort((a, b) => a.path.localeCompare(b.path))
          .map((file) => {
            const parent = file.path.includes("/")
              ? file.path.slice(0, file.path.lastIndexOf("/"))
              : "";
            const heading =
              parent !== directory && parent
                ? `<div class="file-directory">${icon("folder")}<span>${escape(parent)}</span></div>`
                : "";
            directory = parent;
            const selected =
              selection?.path === file.path && selection?.scope === scope;
            const attrs = `${attributes} data-path="${escape(file.path)}"`;
            return `${heading}<div class="file-row ${selected ? "selected" : ""}"><button class="file-name" data-action="preview" ${attrs} title="${escape(file.path)}"><span class="file-status status-${file.status === "?" ? "new" : file.status}">${escape(file.status)}</span><span>${escape(file.name)}</span></button><div class="file-actions">${iconButton("file", scope === "staged" ? "minus" : "plus", t(scope === "staged" ? "unstage" : "stage"), `${attrs} data-kind="${scope === "staged" ? "unstage" : "stage"}"`, locked)}${scope !== "staged" ? iconButton("file", "trash", t(scope === "unstaged" ? "discard" : "delete"), `${attrs} data-kind="${scope === "unstaged" ? "discard" : "delete"}"`, locked) : ""}${scope === "untracked" ? iconButton("file", "close", t("ignore"), `${attrs} data-kind="ignore"`, locked) : ""}</div></div>`;
          })
          .join("")}</div>`
      : ""
  }</section>`;
}

function renderDiff(repo) {
  const selection = state.selections[repo.id];
  const preview = state.preview.repoId === repo.id ? state.preview : {};
  patch(
    "diffToolbar",
    selection
      ? `<div class="diff-title">${icon("file")}<strong title="${escape(selection.path)}">${escape(selection.path)}</strong>${badge(t(selection.scope))}</div><div class="diff-tools">${iconButton("wrap", "code", t("wrap"))}${iconButton("expand", "expand", t(state.expanded ? "collapse" : "expand"))}</div>`
      : `<span class="muted">${t("selectFile")}</span>`,
  );
  $("diffContent").classList.toggle("wrap", state.wrap);
  if (!selection) {
    patch("diffContent", empty("code", t("selectFile"), t("selectFileHint")));
    return;
  }
  if (preview.loading) {
    patch(
      "diffContent",
      `<div class="preview-loading">${icon("refresh", "spin")}${t("checking")}</div>`,
    );
    return;
  }
  if (preview.error) {
    patch(
      "diffContent",
      `<div class="preview-error">${notice(t("previewFailed"), preview.error, "preview-retry")}</div>`,
    );
    return;
  }
  if (!preview.data) return;
  const data = preview.data;
  if (data.mode === "binary") {
    patch("diffContent", empty("file", t("binary")));
    return;
  }
  if (!data.content) {
    patch("diffContent", empty("check", t("emptyDiff")));
    return;
  }
  let oldLine = 0,
    newLine = 0;
  const lines = data.content.split("\n");
  const rows = lines
    .slice(0, 5000)
    .map((line, index) => {
      let kind = "context",
        old = "",
        next = "";
      if (data.mode === "text") next = index + 1;
      else if (line.startsWith("@@")) {
        kind = "hunk";
        const match = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)/);
        if (match) {
          oldLine = Number(match[1]);
          newLine = Number(match[2]);
        }
      } else if (
        line.startsWith("+++") ||
        line.startsWith("---") ||
        line.startsWith("diff ") ||
        line.startsWith("index ") ||
        line.startsWith("\\") ||
        (!oldLine && !newLine)
      )
        kind = "meta";
      else if (line.startsWith("+")) {
        kind = "added";
        next = newLine++;
      } else if (line.startsWith("-")) {
        kind = "removed";
        old = oldLine++;
      } else {
        old = oldLine++;
        next = newLine++;
      }
      return `<div class="diff-line ${kind}"><span class="line-number">${old}</span><span class="line-number">${next}</span><code>${escape(line) || " "}</code></div>`;
    })
    .join("");
  patch(
    "diffContent",
    `<div class="diff-lines">${rows}</div>${data.truncated || lines.length > 5000 ? `<p class="preview-truncated">${t("truncated")}</p>` : ""}`,
  );
}

function renderTasks() {
  if (!state.tasksOpen) return;
  patch(
    "taskList",
    `<p class="drawer-description">${t("taskHint")}</p>${state.tasks.length ? state.tasks.map((task) => `<section class="task-card"><div class="task-card-heading"><strong>${icon(task.fetch_remote ? "down" : "refresh")}${t(task.fetch_remote ? "taskFetch" : "taskRefresh")}</strong>${badge(t(task.status), task.status === "running" ? "accent" : "neutral")}</div><div class="task-summary"><span>${t("taskProgress", { done: task.completed, total: task.total })}</span>${task.failed ? `<span class="text-danger">${t("failures", { count: task.failed })}</span>` : ""}<span>${escape(relativeTime(task.started_at))}</span></div><div class="progress-track"><i style="width:${task.total ? (task.completed / task.total) * 100 : 100}%"></i></div>${task.items.map((item) => `<div class="task-item"><span class="task-item-icon ${item.status === "error" ? "text-danger" : ""}">${icon(item.status === "success" ? "check" : item.status === "error" ? "alert" : "refresh", ["checking", "fetching"].includes(item.status) ? "spin" : "")}</span><span><strong>${escape(item.name)}</strong><small>${t(item.status)}</small></span>${item.status === "error" && task.generation === state.generation ? `<button class="text-button" data-action="retry-task" data-id="${item.repo_id}" data-fetch="${task.fetch_remote}">${t("retry")}</button>` : ""}</div>${item.error ? `<details class="error-details task-error"><summary>${t("details")}</summary><pre>${escape(item.error)}</pre></details>` : ""}`).join("")}</section>`).join("") : empty("check", t("taskEmpty"))}`,
  );
}

export function render() {
  renderChrome();
  renderSidebar();
  if (state.view === "overview") renderOverview();
  if (state.view === "repo") renderRepo();
  if (state.view === "folders")
    patch(
      "foldersView",
      `<div class="page-heading"><div><div class="eyebrow">${t("workspace")}</div><h1>${t("folders")}</h1><p>${t("foldersHint")}</p></div></div><div class="folder-list">${state.nonGitDirs.length ? state.nonGitDirs.map((folder) => `<div class="folder-card">${icon("folder")}<div><strong>${escape(folder.name)}</strong><p>${escape(folder.path)}</p></div></div>`).join("") : empty("folder", t("noFolders"))}</div>`,
    );
  renderTasks();
}

let toastTimer;
export function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 3500);
}

export function confirmAction(titleText, text, accept = t("confirm")) {
  $("confirmTitle").textContent = titleText;
  $("confirmText").textContent = text;
  $("confirmAccept").textContent = accept;
  $("confirmCancel").textContent = t("cancel");
  const dialog = $("confirmDialog");
  return new Promise((resolve) => {
    const finish = (value) => {
      dialog.close();
      dialog.oncancel = null;
      $("confirmAccept").onclick = null;
      $("confirmCancel").onclick = null;
      resolve(value);
    };
    $("confirmAccept").onclick = () => finish(true);
    $("confirmCancel").onclick = () => finish(false);
    dialog.oncancel = (event) => {
      event.preventDefault();
      finish(false);
    };
    dialog.showModal();
    $("confirmCancel").focus();
  });
}
