// Run with Node 22+: node tests/frontend_state.mjs
// These checks exercise ordering and restart boundaries, without a DOM shim.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const preferences = new Map([["workspacePath", "D:/OldWorkspace"]]);
globalThis.localStorage = {
  getItem: (key) => preferences.get(key) ?? null,
  setItem: (key, value) => preferences.set(key, value),
};
globalThis.matchMedia = () => ({ matches: false });
const source = await readFile(
  new URL("../static/js/state.js", import.meta.url),
  "utf8",
);
const { state, applySnapshot, mergeRepo, readPreference } = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);
const snapshot = (instance, generation, repos = [], tasks = []) => ({
  instance_id: instance,
  generation,
  repos,
  tasks,
  path: "workspace",
  non_git_dirs: [],
});

assert.equal(readPreference("workspacePath", ""), "D:/OldWorkspace");
applySnapshot(snapshot("first", 5, [{ id: "repo", revision: 2, dirty: true }]));
mergeRepo({ id: "repo", revision: 1, dirty: false }, 5);
assert.equal(
  state.repos[0].dirty,
  true,
  "An old request overwrote newer repository state",
);
applySnapshot(snapshot("first", 4, []));
assert.equal(
  state.repos.length,
  1,
  "An old workspace response replaced current data",
);
applySnapshot(
  snapshot(
    "first",
    5,
    [],
    [
      {
        id: "task",
        revision: 10,
        started_at: "2026-01-01",
        status: "completed",
      },
    ],
  ),
);
applySnapshot(
  snapshot(
    "first",
    5,
    [],
    [{ id: "task", revision: 3, started_at: "2026-01-01", status: "running" }],
  ),
);
assert.equal(
  state.tasks[0].status,
  "completed",
  "An old poll reverted a completed task",
);
state.drafts.repo = "Keep draft through server restarts";
applySnapshot(snapshot("restarted", 0));
assert.equal(state.instanceId, "restarted");
assert.equal(
  state.generation,
  0,
  "A server restart was rejected as an older generation",
);
assert.equal(state.repos.length, 0);
assert.equal(state.tasks.length, 0);
assert.equal(state.drafts.repo, "Keep draft through server restarts");
console.log(
  "Frontend state checks passed: legacy preferences, repository revisions, workspace generations, task ordering, server restart, draft retention.",
);
