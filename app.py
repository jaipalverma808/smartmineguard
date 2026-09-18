from flask import Flask, jsonify, request
import sys
import os
import platform
import traceback

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "status": "ONLINE",
        "system": "SmartMineGuard Serverless Core",
        "python": sys.version,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "files_in_cwd": os.listdir(".")[:20],
        "diagnostics_url": "/load-app"
    })

@app.route("/ping")
def ping():
    return "PONG: SmartMineGuard is live!\n", 200, {"Content-Type": "text/plain"}

@app.route("/load-app")
def load_app():
    report = {}
    
    # 1. Test Config
    try:
        from config import Config
        report["config"] = {
            "is_serverless": Config.IS_SERVERLESS,
            "sqlite_path": str(Config.SQLITE_PATH),
            "reports_dir": str(Config.REPORTS_DIR)
        }
    except Exception:
        report["config_error"] = traceback.format_exc()

    # 2. Test DB Initialization
    try:
        from services.db import db
        conn = db.get_connection()
        conn.close()
        mine_count = db.query("SELECT COUNT(*) as c FROM mines", one=True)
        report["db"] = {
            "status": "OK",
            "mine_count": mine_count
        }
    except Exception:
        report["db_error"] = traceback.format_exc()

    # 3. Test Full App Loading
    try:
        import app_full
        report["app_full"] = {
            "status": "OK",
            "routes_count": len(list(app_full.app.url_map.iter_rules()))
        }
    except Exception:
        report["app_full_error"] = traceback.format_exc()

    return jsonify(report)
