import os
import sys
from pathlib import Path

# Ensure the root project directory is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    from app import app
except Exception as e:
    import traceback
    err_tb = traceback.format_exc()
    from flask import Flask, Response
    app = Flask(__name__)
    
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def catch_all(path):
        return Response(f"Serverless Application Startup Error:\n\n{err_tb}", mimetype="text/plain", status=500)
