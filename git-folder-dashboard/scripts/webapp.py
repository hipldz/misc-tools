from typing import Optional

from flask import Flask

from .routes import app as flask_app, register_routes
from .runtime import apply_runtime_config, open_browser


app = flask_app
register_routes(app)


def serve(args):
    apply_runtime_config(args, app)
    if not args.no_browser:
        import threading

        threading.Thread(target=open_browser, daemon=True).start()
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


def main(args: Optional[object] = None):
    if args is None:
        from .cli import parse_args

        args = parse_args()
    serve(args)
