import sys
import os
import traceback
from flask import Flask, Response

# Add project root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

_main_app = None
_import_error = None

try:
    import app as imported_module
    _main_app = imported_module.app
except Exception:
    _import_error = traceback.format_exc()

if _main_app is not None:
    app = _main_app
    try:
        @app.route("/ping")
        def ping_ok():
            return Response("PONG: SmartMineGuard is operational!\n", mimetype="text/plain")
    except Exception:
        pass
else:
    app = Flask(__name__)

    @app.route("/ping")
    def ping_err():
        return Response("PONG (DEGRADED): Runtime active but app failed to load\n", mimetype="text/plain")

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    def error_handler(path):
        return Response(
            f"SMARTMINEGUARD INITIALIZATION FAILURE:\n\n{_import_error}\n",
            status=500,
            mimetype="text/plain; charset=utf-8"
        )
