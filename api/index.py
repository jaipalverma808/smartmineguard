import sys
import os
import traceback
from pathlib import Path

# Add project root directory to sys.path so modules like config, services, and app are easily found
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app import app
except Exception as e:
    # Diagnostic fallback: If an unexpected error occurs during import, display the exact traceback
    from flask import Flask, Response
    app = Flask(__name__)
    _boot_err = traceback.format_exc()
    
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        return Response(f"SmartMineGuard Serverless Boot Error:\n\n{_boot_err}", mimetype="text/plain", status=500)
