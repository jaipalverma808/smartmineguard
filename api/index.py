from flask import Flask, jsonify
import sys
import os
import traceback

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

app = Flask(__name__)

@app.route("/ping")
def ping():
    return "PONG: SmartMineGuard Vercel Runtime Active\n"

@app.route("/")
def home():
    return (
        "<!DOCTYPE html><html><head><title>SmartMineGuard Status</title></head>"
        "<body style='font-family:sans-serif;padding:40px;background:#0f172a;color:#f8fafc;'>"
        "<h1>SmartMineGuard Serverless Online</h1>"
        "<p>Vercel AWS Lambda container is running successfully.</p>"
        "<p><a href='/diag' style='color:#38bdf8;font-size:18px;'>Click here to run System Diagnostics</a></p>"
        "</body></html>"
    )

@app.route("/diag")
def diag():
    results = {}
    results["python_version"] = sys.version
    results["cwd"] = os.getcwd()
    results["sys_path"] = sys.path[:5]

    # Test 1: Config
    try:
        from config import Config
        results["config"] = {
            "status": "OK",
            "is_serverless": Config.IS_SERVERLESS,
            "sqlite_path": str(Config.SQLITE_PATH),
            "reports_dir": str(Config.REPORTS_DIR)
        }
    except Exception:
        results["config_error"] = traceback.format_exc()

    # Test 2: Database
    try:
        from services.db import db
        conn = db.get_connection()
        conn.close()
        mine_count = db.query("SELECT COUNT(*) as c FROM mines", one=True)
        results["db"] = {
            "status": "OK",
            "mine_count": mine_count
        }
    except Exception:
        results["db_error"] = traceback.format_exc()

    # Test 3: Services
    services_to_test = ["detection", "risk_engine", "gps_simulator", "material_service", "report_generator"]
    results["services"] = {}
    for s in services_to_test:
        try:
            __import__(f"services.{s}")
            results["services"][s] = "OK"
        except Exception:
            results["services"][s] = traceback.format_exc()

    # Test 4: Main app import
    try:
        import app as main_app_module
        results["app_module"] = "OK"
        results["routes_count"] = len(list(main_app_module.app.url_map.iter_rules()))
    except Exception:
        results["app_module_error"] = traceback.format_exc()

    return jsonify(results)
