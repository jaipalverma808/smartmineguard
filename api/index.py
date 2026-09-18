import sys
import os

# Add root project directory to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from app import app
except Exception as e:
    import traceback
    err_trace = traceback.format_exc()
    from flask import Flask, Response
    app = Flask(__name__)
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        return Response(
            f"SmartMineGuard Startup Error:\n\n{err_trace}",
            status=500,
            mimetype="text/plain; charset=utf-8"
        )
