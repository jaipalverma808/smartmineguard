import sys
import os
import traceback

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from app import app
    try:
        @app.route("/api/ping")
        def ping():
            return "PONG: SmartMineGuard Operational\n"
    except Exception:
        pass
except Exception:
    err_trace = traceback.format_exc()
    from flask import Flask, Response
    app = Flask(__name__)
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    def error_page(path):
        return Response(
            f"SmartMineGuard Startup Error:\n\n{err_trace}\n",
            status=500,
            mimetype="text/plain; charset=utf-8"
        )
