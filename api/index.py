import os
import sys
from pathlib import Path

# Add project root to sys.path so app, config, and services are importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app import app
except Exception as _init_err:
    import traceback
    _init_tb = traceback.format_exc()

    def app(environ, start_response):
        status = "500 Internal Server Error"
        headers = [("Content-Type", "text/plain; charset=utf-8")]
        start_response(status, headers)
        return [f"SmartMineGuard Vercel Cold-Start Exception:\n\n{_init_tb}".encode("utf-8")]

# Expose both app and handler for Vercel serverless conventions
handler = app
