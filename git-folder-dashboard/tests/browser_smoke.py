"""Real browser regression checks with offline, disposable Git repositories.

Run: python tests/browser_smoke.py
Screenshots: build/verification/
"""

import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server, WSGIRequestHandler

from git_dashboard.web import create_app
from tests.helpers import git, repository, cleanup_fixture


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        pass


def fixture(parent):
    primary = repository(parent, "git-folder-dashboard")
    (primary / "app.py").write_text('from git_dashboard.cli import main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n' + "".join("# Workspace check {0}\n".format(index) for index in range(80)), encoding="utf-8")
    (primary / "README.md").write_text("# Git Folder Dashboard\n\nA clear view of every repository.\n", encoding="utf-8")
    git(primary, "add", "README.md")
    (primary / "src").mkdir()
    (primary / "src" / "workspace.py").write_text("# Stable repository identities\n", encoding="utf-8")
    design = repository(parent, "design-system")
    remote = Path(parent).parent / (Path(parent).name + "-remote.git")
    remote.mkdir()
    git(remote, "init", "--bare", "--quiet")
    git(design, "remote", "add", "origin", str(remote))
    git(design, "push", "-u", "origin", "main")
    (design / "README.md").write_text("# New tokens\n", encoding="utf-8")
    git(design, "add", ".")
    git(design, "commit", "--quiet", "-m", "Update tokens")
    broken = repository(parent, "api-gateway")
    git(broken, "remote", "add", "origin", str(Path(parent).parent / "nonexistent-dashboard-test-remote.git"))
    repository(parent, "website")
    docs = repository(parent, "product-docs")
    (docs / "README.md").write_text("# Documentation updates\n", encoding="utf-8")
    (Path(parent) / "assets").mkdir()
    return primary, remote


def main():
    temporary = tempfile.mkdtemp(prefix="gfd-browser-")
    remote = None
    app = None
    server = None
    errors = []
    output = ROOT / "build" / "verification"
    output.mkdir(parents=True, exist_ok=True)
    try:
        primary, remote = fixture(temporary)
        app = create_app({"DEFAULT_WORKSPACE": temporary, "BASE_PATH": "/git"})
        server = make_server("127.0.0.1", 0, app, threaded=True, request_handler=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:{0}/git/".format(server.server_port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            context.add_init_script("localStorage.setItem('gfd.language', '\"zh\"'); localStorage.setItem('gfd.theme', '\"light\"');")
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url)
            expect(page.locator(".repo-table tbody tr")).to_have_count(5, timeout=20000)
            page.wait_for_function("async () => { const data = await (await fetch('/git/api/state')).json(); return data.tasks.length && data.tasks.every(task => task.status !== 'running'); }", timeout=20000)
            expect(page.locator(".repo-table tbody tr").filter(has_text="git-folder-dashboard")).to_contain_text("3 个文件", timeout=10000)
            expect(page.locator("#statusRight")).to_contain_text("完成 5/5", timeout=10000)
            expect(page.locator("#repoList")).to_contain_text("api-gateway")
            page.screenshot(path=str(output / "overview.png"), full_page=True)

            page.locator('#repoList button[data-action="select-repo"]').filter(has_text="git-folder-dashboard").click()
            expect(page.locator("#repoHeader h1")).to_have_text("git-folder-dashboard")
            page.wait_for_function("!document.querySelector('#commitButton').disabled")
            page.locator("#commitMessage").fill("Keep this draft while refreshing")
            page.locator('#changesList [data-action="preview"][data-path="app.py"]').click()
            expect(page.locator("#diffContent")).to_contain_text("git_dashboard.cli")
            page.locator("#themeButton").click()
            expect(page.locator("#commitMessage")).to_have_value("Keep this draft while refreshing")
            page.screenshot(path=str(output / "repository-dark.png"), full_page=True)
            page.locator("#themeButton").click()

            page.locator("#diffContent").evaluate("node => { node.scrollTop = 300; }")
            page.locator("#commitMessage").evaluate("node => { node.focus(); node.setSelectionRange(3, 7); }")
            (primary / "src" / "external-change.py").write_text("# Modified in an editor\n", encoding="utf-8")
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.locator('#changesList [data-path="src/external-change.py"][data-action="preview"]')).to_be_visible(timeout=15000)
            expect(page.locator("#commitMessage")).to_have_value("Keep this draft while refreshing")
            assert page.evaluate("document.activeElement.id === 'commitMessage' && document.activeElement.selectionStart === 3")
            assert page.locator("#diffContent").evaluate("node => node.scrollTop >= 250"), "Diff scroll was lost during refresh"
            page.locator("#diffContent").evaluate("node => { node.scrollTop = 0; }")
            page.screenshot(path=str(output / "repository.png"), full_page=True)

            # A slow response for an older selection cannot replace the new preview.
            page.evaluate("""() => {
                window.originalFetch = window.fetch;
                window.fetch = async (...args) => {
                    const response = await window.originalFetch(...args);
                    let body;
                    try { body = JSON.parse(args[1]?.body || '{}'); } catch {}
                    if (String(args[0]).endsWith('/files/preview') && body?.path === 'app.py') {
                        const contents = await response.text();
                        await new Promise(resolve => setTimeout(resolve, 700));
                        return new Response(contents, {status: response.status, headers: response.headers});
                    }
                    return response;
                };
            }""")
            page.locator('#changesList [data-action="preview"][data-path="app.py"]').click()
            page.wait_for_timeout(150)
            page.locator('#changesList [data-action="preview"][data-path="src/workspace.py"]').click()
            expect(page.locator("#diffContent")).to_contain_text("Stable repository identities")
            page.wait_for_timeout(800)
            expect(page.locator("#diffToolbar")).to_contain_text("src/workspace.py")
            expect(page.locator("#diffContent")).to_contain_text("Stable repository identities")
            page.evaluate("window.fetch = window.originalFetch")

            page.route("**/api/state", lambda route: route.abort())
            page.evaluate("window.dispatchEvent(new Event('focus'))")
            expect(page.locator("#connectionNotice")).to_be_visible(timeout=15000)
            expect(page.locator("#commitMessage")).to_have_value("Keep this draft while refreshing")
            page.unroute("**/api/state")
            page.locator('[data-action="reconnect"]').click()
            expect(page.locator("#connectionNotice")).to_be_hidden(timeout=15000)

            hook = primary / ".git" / "test-hooks" / "pre-commit"
            hook.parent.mkdir()
            hook.write_text("#!/bin/sh\necho 'Test hook: rejected commit' >&2\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)
            page.locator("#commitButton").click()
            expect(page.locator("#commitError")).to_be_visible(timeout=15000)
            expect(page.locator("#commitError")).to_contain_text("Test hook: rejected commit")
            expect(page.locator("#commitMessage")).to_have_value("Keep this draft while refreshing")
            expect(page.locator("#repoNotice")).to_be_hidden()
            hook.unlink()
            page.locator("#commitMessage").fill("Updated message after failure")
            page.locator('#commitError [data-action="retry-action"]').click()
            expect(page.locator("#commitMessage")).to_have_value("", timeout=15000)
            assert git(primary, "log", "-1", "--format=%s").strip() == "Updated message after failure"
            assert git(primary, "show", "HEAD:app.py").startswith("def hello")
            expect(page.locator('#changesList [data-action="preview"][data-path="app.py"]')).to_be_visible()

            page.locator('#repoList button[data-action="select-repo"]').filter(has_text="api-gateway").click()
            expect(page.locator("#repoNotice")).to_be_visible(timeout=15000)
            expect(page.locator("#repoNotice")).to_contain_text("远端抓取失败")
            page.locator("#tasksButton").click()
            expect(page.locator("#taskDrawer")).to_be_visible()
            expect(page.locator("#taskList")).to_contain_text("api-gateway")
            page.screenshot(path=str(output / "tasks.png"), full_page=True)
            page.locator("#closeTasks").click()

            page.locator('#repoList button[data-action="select-repo"]').filter(has_text="git-folder-dashboard").click()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(output / "mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile page overflows horizontally"
            page.locator("#languageButton").click()
            expect(page.locator("#changesHeading")).to_contain_text("Changes")
            assert not errors, errors
            browser.close()
        print("Browser checks passed: workspace progress, external refresh, drafts/focus/scroll, stale-preview cancellation, connection recovery, scoped errors, staged commit, tasks, themes, mobile, localization, subpath assets.")
        print("Screenshots: {0}".format(output))
    finally:
        if server:
            server.shutdown()
        if app:
            app.extensions["tasks"].close()
        cleanup_fixture(temporary)
        if remote:
            cleanup_fixture(remote)


if __name__ == "__main__":
    main()
