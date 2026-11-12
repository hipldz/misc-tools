"""Flask application factory and local server entry point."""

import hmac
import threading
import webbrowser
from uuid import uuid4

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from . import __version__
from .runtime import PrefixMiddleware, normalize_base_path, resource_path
from .services import git
from .services.tasks import TaskRunner
from .services.workspace import Workspace, WorkspaceChanged


def create_app(options=None):
    app = Flask(__name__, static_folder=str(resource_path("static")),
                template_folder=str(resource_path("templates")))
    app.config.update(DEFAULT_WORKSPACE="", BASE_PATH="", AUTHORIZATION=None,
                      SYNC_INTERVAL=0, FETCH_WORKERS=3, REMOTE_TTL=300, MAX_CONTENT_LENGTH=256 * 1024 * 1024)
    app.config.update(options or {})
    app.config["INSTANCE_ID"] = uuid4().hex
    workspace = Workspace()
    tasks = TaskRunner(workspace, app.config["FETCH_WORKERS"])
    app.extensions.update(workspace=workspace, tasks=tasks)

    @app.before_request
    def authorize():
        expected = app.config["AUTHORIZATION"]
        if not expected:
            return None
        supplied = request.authorization
        basic = supplied and (supplied.type or "").lower() == "basic"
        username = (supplied.username or "") if basic else ""
        password = (supplied.password or "") if basic else ""
        username_ok = hmac.compare_digest(username.encode("utf-8"), expected[0].encode("utf-8"))
        password_ok = hmac.compare_digest(password.encode("utf-8"), expected[1].encode("utf-8"))
        if username_ok and password_ok:
            return None
        return Response("Authorization required.", 401,
                        {"WWW-Authenticate": 'Basic realm="Git Folder Dashboard", charset="UTF-8"'})

    @app.after_request
    def cache_policy(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(Exception)
    def handle_error(exc):
        if isinstance(exc, HTTPException):
            code, message = exc.code, exc.description
        elif isinstance(exc, WorkspaceChanged):
            code, message = 409, "Workspace changed. Refresh and try again."
        elif isinstance(exc, LookupError):
            code, message = 404, str(exc)
        elif isinstance(exc, (ValueError, OSError)):
            code, message = 400, str(exc)
        else:
            app.logger.exception("Unhandled dashboard error")
            code, message = 500, "An unexpected error occurred. Check the server log."
        return jsonify(success=False, detail=message), code

    from .api import register_routes

    register_routes(app, workspace, tasks, __version__)
    prefix = normalize_base_path(app.config["BASE_PATH"])
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)
    return app


def serve(args):
    git.GIT_PROXY = args.git_proxy.strip()
    app = create_app({"DEFAULT_WORKSPACE": args.default_path.strip(), "BASE_PATH": args.base_path,
                      "AUTHORIZATION": args.authorize, "SYNC_INTERVAL": args.sync_interval,
                      "FETCH_WORKERS": args.fetch_workers})
    tasks = app.extensions["tasks"]
    tasks.start_periodic(args.sync_interval)
    if not args.no_browser:
        host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
        url = "http://{0}:{1}{2}/".format(host, args.port, normalize_base_path(args.base_path))
        timer = threading.Timer(1, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    try:
        app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)
    finally:
        tasks.close()
