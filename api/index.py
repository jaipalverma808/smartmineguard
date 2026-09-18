import sys
from pathlib import Path
from flask import Flask

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

app = Flask(__name__)

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def handle_all(path):
    try:
        import app as full_app
        # Forward request to real app
        with full_app.app.test_client() as client:
            resp = client.get(f"/{path}")
            return (resp.get_data(), resp.status_code, resp.headers.items())
    except Exception as e:
        import traceback
        return f"CRASH DIAGNOSTIC TRACEBACK:\n\n{traceback.format_exc()}", 500, {"Content-Type": "text/plain"}
