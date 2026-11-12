export function readPreference(key, fallback) {
  try {
    const current = localStorage.getItem(`gfd.${key}`);
    if (current !== null) return JSON.parse(current) ?? fallback;
    // Preserve workspace and appearance preferences from the previous UI.
    if (["workspacePath", "theme", "language"].includes(key))
      return localStorage.getItem(key) || fallback;
    return fallback;
  } catch {
    return fallback;
  }
}
export function savePreference(key, value) {
  try {
    localStorage.setItem(`gfd.${key}`, JSON.stringify(value));
  } catch {
    /* Storage can be unavailable. */
  }
}
export const state = {
  repos: [],
  tasks: [],
  nonGitDirs: [],
  path: "",
  generation: 0,
  instanceId: null,
  activeRepoId: readPreference("activeRepo", null),
  view: "overview",
  filter: "all",
  query: "",
  language: readPreference(
    "language",
    navigator.language.startsWith("zh") ? "zh" : "en",
  ),
  theme: readPreference(
    "theme",
    matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
  ),
  drafts: readPreference("drafts", {}),
  selections: {},
  sections: {},
  busy: {},
  errors: {},
  preview: { token: 0 },
  workspaceBusy: false,
  workspaceError: "",
  connectionError: "",
  tasksOpen: false,
  expanded: false,
  wrap: false,
  config: { remote_ttl: 300, sync_interval: 0 },
};
export const activeRepo = () =>
  state.repos.find((repo) => repo.id === state.activeRepoId);
export const hasError = (repo) =>
  Boolean(
    repo.fetch_error || repo.status === "error" || repo.conflicts?.length,
  );
export function matchesFilter(repo, filter = state.filter) {
  return (
    filter === "all" ||
    (filter === "modified" && repo.dirty) ||
    (filter === "push" && repo.ahead) ||
    (filter === "pull" && repo.behind) ||
    (filter === "sync" && (repo.ahead || repo.behind)) ||
    (filter === "error" && hasError(repo))
  );
}
export const visibleRepos = () =>
  state.repos.filter(
    (repo) =>
      matchesFilter(repo) &&
      `${repo.name} ${repo.path} ${repo.branch || ""}`
        .toLocaleLowerCase()
        .includes(state.query.toLocaleLowerCase()),
  );
export function taskItem(repoId) {
  for (const task of state.tasks) {
    if (task.status !== "running" || task.generation !== state.generation)
      continue;
    const item = task.items.find(
      (item) =>
        item.repo_id === repoId &&
        ["queued", "checking", "fetching"].includes(item.status),
    );
    if (item) return item;
  }
  return null;
}
export function mergeRepo(repo, generation = state.generation) {
  if (!repo || generation !== state.generation) return;
  const index = state.repos.findIndex((item) => item.id === repo.id);
  if (index >= 0 && (repo.revision || 0) >= (state.repos[index].revision || 0))
    state.repos[index] = repo;
}
export function applySnapshot(data) {
  if (
    state.instanceId &&
    data.instance_id &&
    state.instanceId !== data.instance_id
  ) {
    state.generation = 0;
    state.repos = [];
    state.tasks = [];
    state.errors = {};
    state.busy = {};
    state.preview = { token: state.preview.token + 1 };
  }
  state.instanceId = data.instance_id || state.instanceId;
  if (data.generation < state.generation) return false;
  const changed = state.generation !== data.generation;
  state.generation = data.generation;
  state.path = data.path;
  if (changed) state.repos = data.repos;
  else data.repos.forEach((repo) => mergeRepo(repo));
  const tasks = new Map(state.tasks.map((task) => [task.id, task]));
  for (const task of data.tasks || []) {
    if (
      !tasks.has(task.id) ||
      (task.revision || 0) >= (tasks.get(task.id).revision || 0)
    )
      tasks.set(task.id, task);
  }
  state.tasks = [...tasks.values()]
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, 40);
  state.nonGitDirs = data.non_git_dirs || [];
  if (!state.repos.some((repo) => repo.id === state.activeRepoId)) {
    state.activeRepoId = null;
    if (state.view === "repo") state.view = "overview";
  }
  return true;
}
