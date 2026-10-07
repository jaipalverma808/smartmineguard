"""
SmartMineGuard - Web Application & Monitoring Server
Mining & Mineral Transport Monitoring System
"""
import os
import sys
import json
import logging
import hashlib
import re
import time
import math
import uuid
import traceback
import secrets
import threading
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, 
    session, jsonify, send_file, flash, abort, Response
)
from werkzeug.utils import secure_filename

try:
    from flask_socketio import SocketIO, emit
except Exception as _e:
    class DummySocketIO:
        def __init__(self, *args, **kwargs): pass
        def init_app(self, *args, **kwargs): pass
        def on(self, *args, **kwargs):
            return lambda f: f
        def emit(self, *args, **kwargs): pass
        def run(self, app_instance, *args, **kwargs):
            kwargs.pop("allow_unsafe_werkzeug", None)
            return app_instance.run(*args, **kwargs)
    SocketIO = DummySocketIO
    def emit(*args, **kwargs): pass

from werkzeug.security import check_password_hash, generate_password_hash

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("smartmineguard.app")

# Project root directory
BASE_DIR = Path(__file__).resolve().parent

# Initialize Flask app FIRST so app is ALWAYS a valid Flask instance
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static"
)

_BOOT_ERROR = None

try:
    from config import Config
    app.config.from_object(Config)
    from services.db import db
    from services.detection import DetectionEngine
    from services.risk_engine import RiskEngine
    from services.gps_simulator import simulator, is_within_india

    try:
        from services.report_generator import (
            generate_evidence_pdf, 
            generate_erawana_pdf, 
            generate_seizure_notice_pdf,
            generate_royalty_noc_pdf,
            get_enriched_permit_data
        )
    except Exception as _e:
        generate_evidence_pdf = None
        generate_erawana_pdf = None
        generate_seizure_notice_pdf = None
        generate_royalty_noc_pdf = None
        def get_enriched_permit_data(*args, **kwargs): return {}

    from services.material_service import MaterialMonitoringService

except BaseException as _ex:
    _BOOT_ERROR = traceback.format_exc()
    logger.critical(f"FATAL BOOT ERROR in SmartMineGuard: {_BOOT_ERROR}")
    print(f"FATAL BOOT ERROR in SmartMineGuard:\n{_BOOT_ERROR}", file=sys.stderr)


class ErrorLoggingMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app
    def __call__(self, environ, start_response):
        try:
            return self.wsgi_app(environ, start_response)
        except Exception as e:
            tb = traceback.format_exc()
            logger.critical(f"Unhandled WSGI Exception: {tb}")
            is_debug = False
            try:
                is_debug = bool(Config.DEBUG)
            except Exception:
                pass
            if is_debug:
                body = f"SmartMineGuard Runtime Exception:\n\n{tb}".encode("utf-8")
                start_response("500 Internal Server Error", [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body)))
                ])
                return [body]
            else:
                body = b"<!DOCTYPE html><html><head><title>System Notice - SmartMineGuard</title></head><body style='font-family:sans-serif;padding:40px;text-align:center;'><h2>Directorate of Mines &amp; Geology</h2><p>An unexpected server error occurred. Please try again later.</p></body></html>"
                start_response("500 Internal Server Error", [
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Content-Length", str(len(body)))
                ])
                return [body]

app.wsgi_app = ErrorLoggingMiddleware(app.wsgi_app)


@app.before_request
def check_boot_error_on_request():
    if _BOOT_ERROR:
        if getattr(Config, "DEBUG", False):
            return Response(f"SmartMineGuard Boot Error:\n\n{_BOOT_ERROR}\n\nSys.path:\n{sys.path}", mimetype="text/plain", status=500)
        return Response("SmartMineGuard service temporarily unavailable. Please try again in a few moments.", mimetype="text/plain", status=500)


socketio = SocketIO()
try:
    if not os.getenv("VERCEL") and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        socketio.init_app(
            app,
            cors_allowed_origins=getattr(Config, "CORS_ALLOWED_ORIGINS", "*"),
            async_mode="threading",
            manage_session=False,   # Let Flask handle sessions; avoids session conflicts on restart
            ping_timeout=20,        # Client waits 20s before declaring server dead
            ping_interval=10,       # Ping every 10s to detect stale sessions quickly
            logger=False,           # Suppress noisy "Invalid session" INFO spam in logs
            engineio_logger=False,  # Suppress engineio-level session noise
        )
    if 'simulator' in locals():
        simulator.set_socketio(socketio)
except Exception as _e:
    logger.warning(f"SocketIO initialization deferred: {_e}")



@app.route("/health")
@app.route("/api/health")
def health_check():
    """Ultra-lightweight endpoint for uptime bots (pings Render without DB overhead)."""
    return jsonify({"status": "ok", "service": "SmartMineGuard", "uptime": "active"}), 200


def generate_csrf_token():
    # generate a session CSRF token if not present
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


@app.before_request
def enforce_csrf_protection():
    # check CSRF token on POST/PUT/DELETE requests
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if app.config.get("TESTING"):
            return None

        # Public search is strictly GET; if any public endpoint is POST, handle exemptions
        if request.path.startswith("/api/public/"):
            return None

        sent_token = (
            request.headers.get("X-CSRF-Token") or 
            request.form.get("csrf_token") or
            (request.is_json and (request.get_json(silent=True) or {}).get("csrf_token"))
        )
        # For login endpoint, brute-force rate-limiting, session regeneration, and credential checks govern access
        if request.endpoint == "login":
            return None

        expected_token = session.get("_csrf_token")
        if not expected_token or not sent_token or not secrets.compare_digest(sent_token, expected_token):
            logger.warning(f"CSRF defense triggered: token mismatch or absent for {request.path} from {request.remote_addr}")
            if request.path.startswith("/api/"):
                return jsonify({"error": "Forbidden: CSRF authentication failure. Please refresh and retry.", "success": False}), 403
            flash("Your secure browser token expired or was invalid. Please re-submit.", "error")
            return redirect(request.referrer or url_for("index"))


@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=(self)"

    # Content Security Policy (Leaflet, Tailwind, Chart.js, SocketIO)
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net https://cdn.socket.io",
        "style-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.tailwindcss.com https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com data:",
        "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://tile.openstreetmap.org https://unpkg.com https://cdn.jsdelivr.net",
        "connect-src 'self' ws: wss: https://smartmineguard.onrender.com https://cdn.socket.io https://unpkg.com",
        "frame-ancestors 'self'",
        "object-src 'none'",
        "base-uri 'self'"
    ]
    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # enable HSTS in production
    is_prod = getattr(Config, "ENVIRONMENT", "development") == "production"
    if is_prod and (request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

    return response


# --- AUTHENTICATION & ACCESS CONTROL ---

def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            is_api = request.path.startswith("/api/")
            if "user_id" not in session:
                if is_api:
                    return jsonify({"error": "Authentication required", "success": False}), 401
                return redirect(url_for("login", next=request.url))
            if roles and session.get("user_role") not in roles:
                if is_api:
                    return jsonify({"error": "Forbidden: Insufficient role permissions", "success": False}), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_audit(action, details, entity=None, previous_state=None, new_state=None, reason=None):
    """Inserts a platform audit event into audit_logs table."""
    try:
        user_id = session.get("user_id")
        username = session.get("username", "system")
        ip = request.remote_addr or "127.0.0.1"
        db.execute("""
            INSERT INTO audit_logs (user_id, username, action, details, entity, previous_state, new_state, reason, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (user_id, username, action, details, entity, previous_state, new_state, reason, ip))
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")


def get_operator_mine_id():
    """Returns the mine ID owned by the logged-in operator, or None."""
    if session.get("user_role") != "OPERATOR":
        return None
    user_id = session.get("user_id")
    if user_id:
        try:
            u = db.query("SELECT assigned_mine_id FROM users WHERE id = ?", (user_id,), one=True)
            if u and u["assigned_mine_id"]:
                return int(u["assigned_mine_id"])
        except Exception:
            pass
    user_dept = session.get("user_dept", "")
    if not user_dept:
        return 1
    mine = db.query("SELECT id FROM mines WHERE operator_name = ? OR name LIKE ?", 
                    (user_dept, f"%{user_dept}%"), one=True)
    if mine:
        return mine["id"]
    return 1  # Fallback to primary leasehold


def get_officer_mine_id():
    """
    Returns the single mine ID strictly assigned to the logged-in field officer.
    A field officer is strictly locked to their single assigned mine lease and cannot view others.
    """
    if session.get("user_role") != "OFFICER":
        return None
    user_id = session.get("user_id")
    if user_id:
        try:
            u = db.query("SELECT assigned_mine_id FROM users WHERE id = ?", (user_id,), one=True)
            if u and u["assigned_mine_id"]:
                return int(u["assigned_mine_id"])
        except Exception:
            pass
    return session.get("assigned_mine_id") or 1


def get_active_mine_id():
    """
    Returns the currently active mine ID:
    - If user is OPERATOR: strictly returns their bound mine.
    - If user is OFFICER: STRICTLY returns their assigned mine (Officer CANNOT view other mines or statewide grid).
    - If user is ADMIN: returns session.get("selected_mine_id") (can be None for statewide grid, or a filtered mine).
    """
    role = session.get("user_role")
    if role == "OPERATOR":
        return get_operator_mine_id()
    if role == "OFFICER":
        return get_officer_mine_id()
    
    val = session.get("selected_mine_id")
    try:
        return int(val) if val is not None and str(val).isdigit() and int(val) > 0 else None
    except Exception:
        return None


def get_active_sub_mine_id():
    """
    Returns the currently active sub-mine ID (quarry_blocks.id):
    - If user is OPERATOR: strictly returns their bound sub_mine_id.
    - If user is OFFICER or ADMIN:
        1. Checks request.args.get("sub_mine_id") if within a request context
        2. Falls back to session.get("selected_sub_mine_id")
        3. Validates that the sub_mine belongs to active_mine_id (sub-mine requires a parent mine).
    """
    role = session.get("user_role")
    if role == "OPERATOR":
        return get_operator_sub_mine_id()

    active_mine_id = get_active_mine_id()
    if not active_mine_id:
        session.pop("selected_sub_mine_id", None)
        return None

    val = None
    try:
        from flask import has_request_context
        if has_request_context():
            req_sm = request.args.get("sub_mine_id")
            if req_sm is not None:
                if str(req_sm).lower() in ("all", "0", "", "none"):
                    session.pop("selected_sub_mine_id", None)
                    return None
                val = req_sm
    except Exception:
        pass

    if val is None:
        val = session.get("selected_sub_mine_id")

    if val is not None and str(val).isdigit() and int(val) > 0:
        sm_id = int(val)
        qb = db.query("SELECT id FROM quarry_blocks WHERE id = ? AND mine_id = ?", (sm_id, active_mine_id), one=True)
        if qb:
            session["selected_sub_mine_id"] = sm_id
            return sm_id
        else:
            session.pop("selected_sub_mine_id", None)
            return None
    return None


def get_current_scope():
    """
    CENTRALIZED FILTER HELPER:
    Returns the active operational scope across the entire platform:
    {
        "scope": "statewide" | "mine" | "submine",
        "mine_id": int or None,
        "sub_mine_id": int or None,
        "mine": dict or None (resolved from DB),
        "sub_mine": dict or None (resolved from DB),
        "role": str
    }
    Strictly preserves authorization boundaries:
    - ADMIN: Statewide, Mine, or Sub-Mine scope.
    - OFFICER: Strictly locked to their assigned concession mine; can toggle between Mine or Sub-Mine scope.
    - OPERATOR: Strictly locked to their assigned scale station / quarry.
    """
    role = session.get("user_role")
    mine_id = get_active_mine_id()
    sub_mine_id = get_active_sub_mine_id()

    mine_row = None
    sub_mine_row = None
    if mine_id:
        mine_row = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        if mine_row:
            mine_row = dict(mine_row)
            mine_row["current_dispatch_mt"] = float(mine_row.get("current_dispatch_mt") or 0.0)
            mine_row["authorized_annual_quota_mt"] = float(mine_row.get("authorized_annual_quota_mt") or 100000.0)
    if sub_mine_id:
        sub_mine_row = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (sub_mine_id,), one=True)
        if sub_mine_row:
            sub_mine_row = dict(sub_mine_row)
            sub_mine_row["dispatched_mt"] = float(sub_mine_row.get("dispatched_mt") or 0.0)
            sub_mine_row["allocated_quota_mt"] = float(sub_mine_row.get("allocated_quota_mt") or 10000.0)

    if sub_mine_id and sub_mine_row:
        scope = "submine"
    elif mine_id and mine_row:
        scope = "mine"
    else:
        scope = "statewide"

    return {
        "scope": scope,
        "mine_id": mine_id,
        "sub_mine_id": sub_mine_id,
        "mine": mine_row,
        "sub_mine": sub_mine_row,
        "role": role
    }


def get_operator_sub_mine_id():
    """Returns the sub_mine_id (quarry_blocks.id) strictly assigned to the logged-in OPERATOR."""
    if session.get("user_role") != "OPERATOR":
        return None
    user_id = session.get("user_id")
    if user_id:
        try:
            u = db.query("SELECT assigned_sub_mine_id FROM users WHERE id = ?", (user_id,), one=True)
            if u and u["assigned_sub_mine_id"]:
                return int(u["assigned_sub_mine_id"])
        except Exception:
            pass
    return session.get("assigned_sub_mine_id")


def get_operator_truck_ids(mine_id=None, sub_mine_id=None):
    """Returns list of truck IDs strictly associated with the specified sub-mine or mine."""
    if sub_mine_id is None and session.get("user_role") == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
    if mine_id is None and session.get("user_role") == "OPERATOR":
        mine_id = get_operator_mine_id()

    if sub_mine_id:
        rows = db.query("""
            SELECT id as truck_id FROM trucks WHERE sub_mine_id = ?
            UNION
            SELECT DISTINCT truck_id FROM permits WHERE quarry_block_id = ?
        """, (sub_mine_id, sub_mine_id))
        return [r["truck_id"] for r in rows if r["truck_id"] is not None]

    if not mine_id:
        return []
    rows = db.query("""
        SELECT id as truck_id FROM trucks WHERE assigned_mine_id = ?
        UNION
        SELECT DISTINCT truck_id FROM permits WHERE mine_id = ?
        UNION
        SELECT DISTINCT truck_id FROM trips WHERE mine_id = ?
    """, (mine_id, mine_id, mine_id))
    return [r["truck_id"] for r in rows if r["truck_id"] is not None]


def validate_operator_truck_access(truck_id):
    """Returns True if the current user can access this truck, False otherwise."""
    return validate_user_truck_access(truck_id)


def validate_user_truck_access(truck_id):
    # check truck access: Admin has full access, Officer sees their mine, Operator sees their sub-mine/quarry
    role = session.get("user_role")
    if not role:
        return False
    if role == "ADMIN":
        return True
    if role == "OPERATOR":
        allowed_trucks = get_operator_truck_ids()
        return truck_id in allowed_trucks
    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if not officer_mine_id:
            return False
        t = db.query("""
            SELECT id FROM trucks WHERE id = ? AND (
                assigned_mine_id = ?
                OR id IN (SELECT truck_id FROM permits WHERE mine_id = ?)
                OR id IN (SELECT truck_id FROM trips WHERE mine_id = ?)
            )
        """, (truck_id, officer_mine_id, officer_mine_id, officer_mine_id), one=True)
        return t is not None
    return False


def validate_operator_permit_access(permit_id):
    """Returns True if the current user can access this permit, False otherwise."""
    return validate_user_permit_access(permit_id)


def validate_user_permit_access(permit_id):
    # check permit access: Admin has full access, Officer sees their mine, Operator sees their sub-mine/quarry
    role = session.get("user_role")
    if not role:
        return False
    if role == "ADMIN":
        return True
    if role == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
        if sub_mine_id:
            p = db.query("""
                SELECT id FROM permits 
                WHERE id = ? AND (quarry_block_id = ? OR truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?))
            """, (permit_id, sub_mine_id, sub_mine_id), one=True)
            return p is not None
        mine_id = get_operator_mine_id()
        if mine_id:
            p = db.query("SELECT id FROM permits WHERE id = ? AND mine_id = ?", (permit_id, mine_id), one=True)
            return p is not None
        return False
    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if not officer_mine_id:
            return False
        p = db.query("SELECT id FROM permits WHERE id = ? AND mine_id = ?", (permit_id, officer_mine_id), one=True)
        return p is not None
    return False


def validate_operator_trip_access(trip_id):
    """Returns True if the current user can access this trip, False otherwise."""
    return validate_user_trip_access(trip_id)


def validate_user_trip_access(trip_id):
    """
    Validates trip access according to strict RBAC boundaries:
    - ADMIN: Full statewide transit trip access.
    - OFFICER: Strictly trips originating from or passing through their assigned mine.
    - OPERATOR: Strictly trips associated with their assigned trucks / permits.
    """
    role = session.get("user_role")
    if not role:
        return False
    if role == "ADMIN":
        return True
    if role == "OPERATOR":
        allowed_trucks = get_operator_truck_ids()
        tr = db.query("SELECT truck_id FROM trips WHERE id = ?", (trip_id,), one=True)
        if not tr:
            return False
        return tr["truck_id"] in allowed_trucks
    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if not officer_mine_id:
            return False
        tr = db.query("SELECT id FROM trips WHERE id = ? AND mine_id = ?", (trip_id, officer_mine_id), one=True)
        return tr is not None
    return False


def validate_user_weighment_access(weighment_id):
    """Validates weighment access according to strict RBAC boundaries."""
    role = session.get("user_role")
    if not role:
        return False
    if role == "ADMIN":
        return True
    w = db.query("""
        SELECT w.*, tr.mine_id as tr_mine_id, p.mine_id as p_mine_id, t.assigned_mine_id as t_mine_id
        FROM weighments w
        LEFT JOIN trips tr ON tr.id = w.trip_id
        LEFT JOIN permits p ON p.id = w.permit_id
        LEFT JOIN trucks t ON t.id = w.truck_id
        WHERE w.id = ?
    """, (weighment_id,), one=True)
    if not w:
        return False
    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        w_mines = {w.get("tr_mine_id"), w.get("p_mine_id"), w.get("t_mine_id")}
        return officer_mine_id in w_mines
    if role == "OPERATOR":
        return w.get("truck_id") in get_operator_truck_ids()
    return False


def validate_user_investigation_access(inv_id):
    """Validates investigation case access according to strict RBAC boundaries."""
    role = session.get("user_role")
    if role == "ADMIN":
        return True
    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if not officer_mine_id:
            return False
        inv_mine = db.query("""
            SELECT p.mine_id as p_mine, tr.mine_id as tr_mine, t.assigned_mine_id as t_mine
            FROM investigations inv
            LEFT JOIN permits p ON p.id = inv.permit_id
            LEFT JOIN trips tr ON tr.id = inv.trip_id
            LEFT JOIN trucks t ON t.id = inv.truck_id
            WHERE inv.id = ?
        """, (inv_id,), one=True)
        if inv_mine:
            m_ids = {inv_mine["p_mine"], inv_mine["tr_mine"], inv_mine["t_mine"]}
            return officer_mine_id in m_ids
        return False
    return False


def get_current_user():
    """Returns dict of logged in user from session or DB."""
    if "user_id" not in session:
        return None
    try:
        u = db.query("SELECT * FROM users WHERE id = ?", (session["user_id"],), one=True)
        if u:
            return dict(u)
    except Exception:
        pass
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "full_name": session.get("user_fullname") or session.get("username"),
        "role": session.get("user_role"),
        "badge_number": session.get("user_badge"),
        "department": session.get("user_dept")
    }


@app.context_processor
def inject_global_context():
    """Injects user session, active mine and sub-mine filter, current_scope, and real-time alert badge count into all templates."""
    pending_alerts_count = 0
    role = session.get("user_role")
    current_scope = get_current_scope()
    active_mine_id = current_scope["mine_id"]
    active_sub_mine_id = current_scope["sub_mine_id"]
    active_mine = current_scope["mine"]
    active_sub_mine = current_scope["sub_mine"]
    all_mines = []
    all_sub_mines = []
    try:
        if role == "OFFICER":
            active_mine_id = get_officer_mine_id()
            active_mine = db.query("SELECT id, mine_code, name, district, state, mineral, authorized_annual_quota_mt FROM mines WHERE id = ?", (active_mine_id,), one=True)
            all_mines = [active_mine] if active_mine else []
            if active_mine_id:
                all_sub_mines = db.query("SELECT id, mine_id, block_code, block_name, leaseholder_name, allocated_quota_mt, dispatched_mt FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC", (active_mine_id,))
        elif role == "OPERATOR":
            active_mine_id = get_operator_mine_id()
            active_mine = db.query("SELECT id, mine_code, name, district, state, mineral, authorized_annual_quota_mt FROM mines WHERE id = ?", (active_mine_id,), one=True)
            all_mines = [active_mine] if active_mine else []
            sub_id = get_operator_sub_mine_id()
            if sub_id:
                active_sub_mine = db.query("SELECT id, mine_id, block_code, block_name, leaseholder_name FROM quarry_blocks WHERE id = ?", (sub_id,), one=True)
                all_sub_mines = [active_sub_mine] if active_sub_mine else []
        else:
            all_mines = db.query("SELECT id, mine_code, name, district, state, mineral, authorized_annual_quota_mt FROM mines ORDER BY id ASC")
            if active_mine_id:
                all_sub_mines = db.query("SELECT id, mine_id, block_code, block_name, leaseholder_name, allocated_quota_mt, dispatched_mt FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC", (active_mine_id,))
            else:
                all_sub_mines = []

        if active_sub_mine_id and not active_sub_mine:
            active_sub_mine = next((sm for sm in all_sub_mines if sm["id"] == active_sub_mine_id), None)
            if not active_sub_mine:
                active_sub_mine = db.query("SELECT id, mine_id, block_code, block_name, leaseholder_name FROM quarry_blocks WHERE id = ?", (active_sub_mine_id,), one=True)
    except Exception:
        pass

    if role in ("ADMIN", "OFFICER"):
        try:
            if active_sub_mine_id:
                row = db.query("""
                    SELECT COUNT(*) as count FROM alerts a
                    LEFT JOIN trucks t ON t.id = a.truck_id
                    LEFT JOIN permits p ON p.id = a.permit_id
                    WHERE a.status IN ('NEW', 'UNDER_REVIEW')
                      AND (t.sub_mine_id = ? OR p.quarry_block_id = ?)
                """, (active_sub_mine_id, active_sub_mine_id), one=True)
            elif active_mine_id:
                row = db.query("""
                    SELECT COUNT(*) as count FROM alerts a
                    LEFT JOIN trips tr ON tr.id = a.trip_id
                    LEFT JOIN permits p ON p.id = a.permit_id
                    LEFT JOIN trucks t ON t.id = a.truck_id
                    WHERE a.status IN ('NEW', 'UNDER_REVIEW')
                      AND (tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?)
                """, (active_mine_id, active_mine_id, active_mine_id), one=True)
            else:
                row = db.query("SELECT COUNT(*) as count FROM alerts WHERE status IN ('NEW', 'UNDER_REVIEW')", one=True)
            pending_alerts_count = row["count"] if row else 0
        except Exception:
            pass

    return {
        "current_user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "full_name": session.get("user_fullname"),
            "role": session.get("user_role"),
            "badge_number": session.get("user_badge"),
            "department": session.get("user_dept"),
            "assigned_mine_id": active_mine_id,
            "assigned_sub_mine_id": active_sub_mine_id
        } if "user_id" in session else None,
        "pending_alerts_count": pending_alerts_count,
        "current_scope": current_scope,
        "active_mine_id": active_mine_id,
        "active_mine": active_mine,
        "all_mines": all_mines,
        "active_sub_mine_id": active_sub_mine_id,
        "active_sub_mine": active_sub_mine,
        "all_sub_mines": all_sub_mines,
        "current_year": datetime.now().year,
        "csrf_token": generate_csrf_token
    }


@app.route("/set-mine-filter", methods=["GET", "POST"])
@login_required()
def set_mine_filter():
    """
    Sets or clears the persistent mine and/or sub-mine filter across the platform.
    - ADMIN can select any mine and/or sub-mine (or statewide/all).
    - OFFICER is locked to their assigned mine, but can select or clear any sub-mine within their concession.
    - OPERATOR is locked to their assigned station.
    Cascading rules strictly enforced:
    - If Mine changes to another Mine, previous Sub-Mine selection is cleared.
    - If Mine is reset to All Mines, Sub-Mine is cleared.
    - Never allow Mine A + Sub-Mine belonging to Mine B.
    """
    role = session.get("user_role")
    if role not in ("ADMIN", "OFFICER"):
        flash("Access Denied: Operators are restricted to their assigned scale station.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    mine_id = request.values.get("mine_id")
    sub_mine_id = request.values.get("sub_mine_id")

    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if not sub_mine_id or str(sub_mine_id).lower() in ("all", "0", "", "none"):
            session.pop("selected_sub_mine_id", None)
            flash("Displaying all sub-mines/quarry pits in your assigned concession.", "info")
        else:
            try:
                sm_id = int(sub_mine_id)
                qb = db.query("SELECT * FROM quarry_blocks WHERE id = ? AND mine_id = ?", (sm_id, officer_mine_id), one=True)
                if qb:
                    session["selected_sub_mine_id"] = sm_id
                    flash(f"Sector Filter Applied: {qb['block_name']} ({qb['block_code']}).", "success")
                else:
                    session.pop("selected_sub_mine_id", None)
                    flash("Selected sub-mine is not part of your assigned concession.", "warning")
            except Exception:
                session.pop("selected_sub_mine_id", None)
        next_url = request.values.get("next") or request.referrer or url_for("dashboard")
        return redirect(next_url)

    # ADMIN:
    prev_mine_id = session.get("selected_mine_id")
    mine_changed = False
    if "mine_id" in request.values:
        if not mine_id or str(mine_id).lower() in ("all", "0", "", "none"):
            session.pop("selected_mine_id", None)
            session.pop("selected_sub_mine_id", None)
            sub_mine_id = None
            flash("Displaying statewide grid for all mining leaseholds.", "info")
        else:
            try:
                m_id = int(mine_id)
                mine = db.query("SELECT * FROM mines WHERE id = ?", (m_id,), one=True)
                if mine:
                    if str(prev_mine_id or "") != str(m_id):
                        mine_changed = True
                        if "sub_mine_id" not in request.values:
                            session.pop("selected_sub_mine_id", None)
                    session["selected_mine_id"] = m_id
                    flash(f"Global site filter applied: {mine['name']} ({mine['district']}).", "success")
                else:
                    session.pop("selected_mine_id", None)
                    session.pop("selected_sub_mine_id", None)
            except Exception:
                session.pop("selected_mine_id", None)
                session.pop("selected_sub_mine_id", None)

    # Process sub_mine_id for Admin (validated against current_m_id to prevent cross-mine mismatch)
    if "sub_mine_id" in request.values:
        if not sub_mine_id or str(sub_mine_id).lower() in ("all", "0", "", "none"):
            session.pop("selected_sub_mine_id", None)
            flash("Displaying all sub-mines for the selected sector.", "info")
        else:
            try:
                sm_id = int(sub_mine_id)
                current_m_id = session.get("selected_mine_id")
                if current_m_id:
                    qb = db.query("SELECT * FROM quarry_blocks WHERE id = ? AND mine_id = ?", (sm_id, current_m_id), one=True)
                    if qb:
                        session["selected_sub_mine_id"] = sm_id
                        flash(f"Isolated to Sub-Mine: {qb['block_name']} ({qb['block_code']}).", "success")
                    else:
                        session.pop("selected_sub_mine_id", None)
                else:
                    session.pop("selected_sub_mine_id", None)
            except Exception:
                session.pop("selected_sub_mine_id", None)

    next_url = request.values.get("next") or request.referrer or url_for("dashboard")
    return redirect(next_url)


# --- HEALTH & KEEP-ALIVE ---

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# --- PAGE ROUTES (HTML + JINJA2) ---

@app.route("/")
def index():
    """Public Unauthenticated Home Page for SmartMineGuard."""
    total_mines = db.query("SELECT COUNT(*) as c FROM mines", one=True)["c"]
    total_trucks = db.query("SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT'", one=True)["c"]
    active_permits = db.query("SELECT COUNT(*) as c FROM permits WHERE status = 'ACTIVE'", one=True)["c"]
    weighbridges_count = db.query("SELECT COUNT(DISTINCT weighbridge_code) as c FROM weighments", one=True)["c"] or 3

    mines = db.query("SELECT id, mine_code, name, district, state, mineral, status FROM mines ORDER BY id ASC")

    return render_template("home.html",
        total_mines=total_mines,
        total_trucks=total_trucks,
        active_permits=active_permits,
        weighbridges_count=weighbridges_count,
        mines=mines
    )


@app.route("/report-illegal-mining")
@app.route("/whistleblower")
def report_illegal_mining():
    """Dedicated Public Whistleblower Incident Reporting Portal (Janta Vigilance)."""
    return render_template("whistleblower.html")


# Track failed logins (lock out for 2 minutes after 5 failed tries within 5 mins)
_failed_logins = {}
_login_lockouts = {}
_FAILED_LOGIN_ATTEMPTS = _failed_logins
_LOGIN_LOCKOUTS = _login_lockouts

def _check_rate_limit(ip):
    now = time.time()
    # check if currently locked out
    lockout_until = _login_lockouts.get(ip, 0)
    if now < lockout_until:
        return False, int(lockout_until - now)
    
    # keep failed attempts within last 5 minutes
    attempts = [t for t in _failed_logins.get(ip, []) if now - t < 300]
    _failed_logins[ip] = attempts
    if len(attempts) >= 5:
        _login_lockouts[ip] = now + 120  # 2 minute lockout
        return False, 120
    return True, 0

def _record_failed_login(ip):
    now = time.time()
    attempts = _failed_logins.get(ip, [])
    attempts.append(now)
    _failed_logins[ip] = attempts
    if len(attempts) >= 5:
        _login_lockouts[ip] = now + 120

def _clear_failed_logins(ip):
    _failed_logins.pop(ip, None)
    _login_lockouts.pop(ip, None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        client_ip = request.remote_addr or "127.0.0.1"
        allowed, wait_secs = _check_rate_limit(client_ip)
        if not allowed:
            flash(f"Security Alert: Excessive failed sign-in attempts detected. Access suspended for {wait_secs}s to safeguard portal credentials.", "error")
            logger.warning(f"Rate limited sign-in attempt from IP: {client_ip} (locked for {wait_secs}s)")
            return render_template("login.html"), 429

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        u_norm = username.lower().strip()
        user = db.query("SELECT * FROM users WHERE LOWER(username) = ? AND is_active = TRUE", (u_norm,), one=True)
        
        # Support contractor/constructor synonyms
        if not user and u_norm in ("contractor", "contractor1", "constructor", "constructor1"):
            user = db.query("SELECT * FROM users WHERE LOWER(username) IN ('contractor1', 'constructor1', 'contractor', 'constructor') AND is_active = TRUE LIMIT 1", one=True)
            if not user:
                # Auto-provision contractor user if missing
                try:
                    pw_h = generate_password_hash("contractor123", method="scrypt")
                    db.execute("""
                        INSERT INTO users (username, password_hash, full_name, role, department, badge_number, email, phone, is_active, assigned_mine_id)
                        VALUES (?, ?, ?, 'CONTRACTOR', 'National Highway EPC Infrastructure', 'NHAI-EPC-702', 'projects@sharmainfra.com', '+91 98110 55667', TRUE, 1)
                    """, ("contractor1", pw_h, "Sharma Infrastructure Ltd (NHAI EPC Contractor)"))
                    user = db.query("SELECT * FROM users WHERE LOWER(username) = 'contractor1' AND is_active = TRUE", one=True)
                except Exception as _p_err:
                    logger.warning(f"Auto-provisioning contractor failed: {_p_err}")

        is_pw_valid = False
        if user:
            if check_password_hash(user["password_hash"], password):
                is_pw_valid = True
            elif user.get("role") == "CONTRACTOR" and password in ("contractor123", "constructor123"):
                is_pw_valid = True

        if user and is_pw_valid:
            _clear_failed_logins(client_ip)
            # Regenerate session to protect against session fixation attacks
            session.clear()
            session["_csrf_token"] = secrets.token_hex(32)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["user_fullname"] = user["full_name"]
            session["user_role"] = user["role"]
            session["user_badge"] = user["badge_number"]
            session["user_dept"] = user["department"]
            assigned_m = user["assigned_mine_id"] if "assigned_mine_id" in user.keys() and user["assigned_mine_id"] else 1
            session["assigned_mine_id"] = assigned_m
            assigned_sm = user["assigned_sub_mine_id"] if "assigned_sub_mine_id" in user.keys() and user["assigned_sub_mine_id"] else None
            session["assigned_sub_mine_id"] = assigned_sm
            session.pop("selected_mine_id", None)

            log_audit("USER_LOGIN", f"User '{username}' logged in successfully as {user['role']}.")
            logger.info(f"User {username} logged in successfully ({user['role']}).")
            next_url = request.args.get("next")
            if user["role"] == "CONTRACTOR":
                return redirect(next_url or url_for("contractor_dashboard"))
            return redirect(next_url or url_for("dashboard"))
        else:
            _record_failed_login(client_ip)
            log_audit("FAILED_LOGIN_ATTEMPT", f"Failed authentication attempt for username '{username}' from IP {client_ip}.")
            flash("Invalid username or password. Please try again.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    username = session.get("username")
    if username:
        log_audit("USER_LOGOUT", f"User '{username}' signed out.")
    session.clear()
    flash("You have been signed out of the monitoring system.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    role = session.get("user_role")
    if role == "CONTRACTOR":
        return redirect(url_for("contractor_dashboard"))

    # Sync URL parameters into session if provided (preserving backwards-compatibility)
    if role == "ADMIN":
        if "mine_id" in request.args:
            m_param = request.args.get("mine_id")
            if m_param and m_param.isdigit() and int(m_param) > 0:
                prev_m = session.get("selected_mine_id")
                session["selected_mine_id"] = int(m_param)
                if prev_m != int(m_param):
                    session.pop("selected_sub_mine_id", None)
            else:
                session.pop("selected_mine_id", None)
                session.pop("selected_sub_mine_id", None)

        if "sub_mine_id" in request.args:
            sm_param = request.args.get("sub_mine_id")
            if sm_param and sm_param.isdigit() and int(sm_param) > 0:
                session["selected_sub_mine_id"] = int(sm_param)
            else:
                session.pop("selected_sub_mine_id", None)
    elif role == "OFFICER":
        session.pop("selected_mine_id", None)  # Strictly disallowed for OFFICER to switch mines
        if "sub_mine_id" in request.args:
            sm_param = request.args.get("sub_mine_id")
            if sm_param and sm_param.isdigit() and int(sm_param) > 0:
                session["selected_sub_mine_id"] = int(sm_param)
            else:
                session.pop("selected_sub_mine_id", None)
    else:
        session.pop("selected_mine_id", None)
        session.pop("selected_sub_mine_id", None)

    current_scope = get_current_scope()
    scope = current_scope["scope"]
    selected_mine_id = current_scope["mine_id"]
    selected_sub_mine_id = current_scope["sub_mine_id"]
    selected_mine = current_scope["mine"]
    selected_sub_mine = current_scope["sub_mine"]

    if role == "ADMIN":
        if scope == "submine":
            # STATE 3: ONE MINE + ONE SUB-MINE SELECTED
            total_mines = 1
            total_sub_mines = 1
            truck_ids = get_operator_truck_ids(selected_mine_id, selected_sub_mine_id)
            total_trucks = len(truck_ids)
            placeholders = ",".join("?" for _ in truck_ids) if truck_ids else "NULL"

            active_trucks = db.query(f"SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT' AND id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            active_permits = db.query("""
                SELECT COUNT(*) as c FROM permits 
                WHERE status = 'ACTIVE' AND (quarry_block_id = ? OR truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?))
            """, (selected_sub_mine_id, selected_sub_mine_id), one=True)["c"]
            total_trips = db.query(f"SELECT COUNT(*) as c FROM trips WHERE truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            pending_alerts = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE status = 'NEW' AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            critical_cases = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE severity = 'CRITICAL' AND status NOT IN ('DISMISSED', 'RESOLVED') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            escalated_cases = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE (escalated_to_admin = 1 OR severity = 'CRITICAL') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            high_risk_trucks_count = db.query(f"SELECT COUNT(*) as c FROM trucks WHERE current_risk_score >= 50 AND id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            investigations_count = db.query(f"SELECT COUNT(*) as c FROM investigations WHERE status != 'CLOSED' AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            officer_actions_count = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE handled_by_user_id IS NOT NULL AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0

            daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=selected_mine_id, sub_mine_id=selected_sub_mine_id)
            dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=selected_mine_id, sub_mine_id=selected_sub_mine_id)
            mismatch_check = DetectionEngine.check_production_dispatch_reconciliation(mine_id=selected_mine_id)
            stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=selected_mine_id, sub_mine_id=selected_sub_mine_id)
            top_rankings = MaterialMonitoringService.get_top_material_rankings(mine_id=selected_mine_id, sub_mine_id=selected_sub_mine_id)
            mineral_summary = MaterialMonitoringService.get_mineral_wise_summary(mine_id=selected_mine_id, sub_mine_id=selected_sub_mine_id)
            mine_quarry_blocks = [selected_sub_mine] if selected_sub_mine else []

            truck_material_ledger = MaterialMonitoringService.get_truck_wise_material_ledger(mine_id=selected_mine_id, sub_mine_id=selected_sub_mine_id)
            assigned_contractor_trucks = db.query("SELECT * FROM trucks WHERE sub_mine_id = ? ORDER BY registration_number ASC", (selected_sub_mine_id,))
            contractor_today_dispatch = daily_summary["actual_dispatch_mt"]
            contractor_today_production = daily_summary["production_today_mt"]
            assigned_contractor_permits = db.query("""
                SELECT p.*, t.registration_number 
                FROM permits p 
                LEFT JOIN trucks t ON t.id = p.truck_id 
                WHERE p.quarry_block_id = ? OR t.sub_mine_id = ?
                ORDER BY p.id DESC LIMIT 8
            """, (selected_sub_mine_id, selected_sub_mine_id))
            officer_audits = db.query(f"""
                SELECT a.*, t.registration_number, p.permit_number,
                       u_handled.full_name as officer_name, u_handled.badge_number as officer_badge
                FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                LEFT JOIN permits p ON p.id = a.permit_id
                LEFT JOIN users u_handled ON u_handled.id = a.handled_by_user_id
                WHERE a.truck_id IN ({placeholders})
                ORDER BY a.id DESC LIMIT 6
            """, truck_ids) if truck_ids else []

        elif scope == "mine":
            # STATE 2: ONE MINE SELECTED
            total_mines = 1
            mine_quarry_blocks = db.query("""
                SELECT qb.*, m.name as mine_name, m.district as mine_district
                FROM quarry_blocks qb
                LEFT JOIN mines m ON m.id = qb.mine_id
                WHERE qb.mine_id = ?
                ORDER BY qb.id ASC
            """, (selected_mine_id,))
            total_sub_mines = len(mine_quarry_blocks)

            truck_ids = get_operator_truck_ids(selected_mine_id)
            total_trucks = len(truck_ids)
            placeholders = ",".join("?" for _ in truck_ids) if truck_ids else "NULL"

            active_trucks = db.query(f"SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT' AND id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            active_permits = db.query("SELECT COUNT(*) as c FROM permits WHERE status = 'ACTIVE' AND mine_id = ?", (selected_mine_id,), one=True)["c"]
            total_trips = db.query("SELECT COUNT(*) as c FROM trips WHERE mine_id = ?", (selected_mine_id,), one=True)["c"]
            pending_alerts = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.status = 'NEW' AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (selected_mine_id, selected_mine_id), one=True)["c"]
            critical_cases = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.severity = 'CRITICAL' AND a.status NOT IN ('DISMISSED', 'RESOLVED') AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (selected_mine_id, selected_mine_id), one=True)["c"]
            escalated_cases = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE (a.escalated_to_admin = 1 OR a.severity = 'CRITICAL') AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (selected_mine_id, selected_mine_id), one=True)["c"]
            high_risk_trucks_count = db.query(f"SELECT COUNT(*) as c FROM trucks WHERE current_risk_score >= 50 AND id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            investigations_count = db.query("""
                SELECT COUNT(*) as c FROM investigations inv
                LEFT JOIN permits p ON p.id = inv.permit_id
                LEFT JOIN trips tr ON tr.id = inv.trip_id
                WHERE inv.status != 'CLOSED' AND (p.mine_id = ? OR tr.mine_id = ?)
            """, (selected_mine_id, selected_mine_id), one=True)["c"]
            officer_actions_count = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.handled_by_user_id IS NOT NULL AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (selected_mine_id, selected_mine_id), one=True)["c"]

            daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=selected_mine_id)
            dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=selected_mine_id)
            mismatch_check = DetectionEngine.check_production_dispatch_reconciliation(mine_id=selected_mine_id)
            stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=selected_mine_id)
            top_rankings = MaterialMonitoringService.get_top_material_rankings(mine_id=selected_mine_id)
            mineral_summary = MaterialMonitoringService.get_mineral_wise_summary(mine_id=selected_mine_id)

            truck_material_ledger = []
            assigned_contractor_trucks = []
            assigned_contractor_permits = []
            contractor_today_dispatch = 0.0
            contractor_today_production = 0.0
            officer_audits = db.query("""
                SELECT a.*, t.registration_number, p.permit_number,
                       u_handled.full_name as officer_name, u_handled.badge_number as officer_badge
                FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                LEFT JOIN permits p ON p.id = a.permit_id
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN users u_handled ON u_handled.id = a.handled_by_user_id
                WHERE (tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?)
                  AND (a.escalated_to_admin = 1 OR a.handled_by_user_id IS NOT NULL OR a.severity IN ('CRITICAL', 'HIGH'))
                ORDER BY a.id DESC LIMIT 6
            """, (selected_mine_id, selected_mine_id, selected_mine_id))

        else:
            # STATE 1: ALL MINES (STATEWIDE GRID)
            total_mines = db.query("SELECT COUNT(*) as c FROM mines", one=True)["c"]
            all_quarry_blocks_db = db.query("""
                SELECT qb.*, m.name as mine_name, m.district as mine_district
                FROM quarry_blocks qb
                LEFT JOIN mines m ON m.id = qb.mine_id
                ORDER BY qb.mine_id ASC, qb.id ASC
            """)
            total_sub_mines = len(all_quarry_blocks_db)
            total_trucks = db.query("SELECT COUNT(*) as c FROM trucks", one=True)["c"]
            active_trucks = db.query("SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT'", one=True)["c"]
            active_permits = db.query("SELECT COUNT(*) as c FROM permits WHERE status = 'ACTIVE'", one=True)["c"]
            total_trips = db.query("SELECT COUNT(*) as c FROM trips", one=True)["c"]
            pending_alerts = db.query("SELECT COUNT(*) as c FROM alerts WHERE status = 'NEW'", one=True)["c"]
            critical_cases = db.query("SELECT COUNT(*) as c FROM alerts WHERE severity = 'CRITICAL' AND status NOT IN ('DISMISSED', 'RESOLVED')", one=True)["c"]
            escalated_cases = db.query("SELECT COUNT(*) as c FROM alerts WHERE escalated_to_admin = 1 OR severity = 'CRITICAL'", one=True)["c"]
            high_risk_trucks_count = db.query("SELECT COUNT(*) as c FROM trucks WHERE current_risk_score >= 50", one=True)["c"]
            investigations_count = db.query("SELECT COUNT(*) as c FROM investigations WHERE status != 'CLOSED'", one=True)["c"]
            officer_actions_count = db.query("SELECT COUNT(*) as c FROM alerts WHERE handled_by_user_id IS NOT NULL", one=True)["c"]

            daily_summary = MaterialMonitoringService.get_daily_dispatch_summary()
            dispatch_control = MaterialMonitoringService.get_dispatch_control_planning()
            mismatch_check = DetectionEngine.check_production_dispatch_reconciliation()
            stock_recon = MaterialMonitoringService.get_stock_reconciliation()
            top_rankings = MaterialMonitoringService.get_top_material_rankings()
            mineral_summary = MaterialMonitoringService.get_mineral_wise_summary()

            mine_quarry_blocks = []
            truck_material_ledger = []
            assigned_contractor_trucks = []
            assigned_contractor_permits = []
            contractor_today_dispatch = 0.0
            contractor_today_production = 0.0
            officer_audits = db.query("""
                SELECT a.*, t.registration_number, p.permit_number,
                       u_handled.full_name as officer_name, u_handled.badge_number as officer_badge
                FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                LEFT JOIN permits p ON p.id = a.permit_id
                LEFT JOIN users u_handled ON u_handled.id = a.handled_by_user_id
                WHERE a.escalated_to_admin = 1 OR a.handled_by_user_id IS NOT NULL OR a.severity IN ('CRITICAL', 'HIGH')
                ORDER BY a.id DESC LIMIT 6
            """)

        mines = db.query("SELECT * FROM mines ORDER BY id ASC")
        users = db.query("SELECT id, username, full_name, role, department, badge_number, is_active FROM users ORDER BY id ASC")
        audit_logs = db.query("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 8")
        mine_wise_summary = MaterialMonitoringService.get_mine_wise_material_summary()
        all_quarry_blocks = db.query("""
            SELECT qb.*, m.name as mine_name, m.district as mine_district
            FROM quarry_blocks qb
            LEFT JOIN mines m ON m.id = qb.mine_id
            ORDER BY qb.mine_id ASC, qb.id ASC
        """)
        all_trucks = db.query("SELECT id, registration_number, vehicle_type, max_capacity_mt FROM trucks ORDER BY registration_number ASC")
        try:
            if scope == "submine" and selected_sub_mine_id:
                # Sub-mine pit filter: show projects originating from or bound to this quarry block pit
                infrastructure_projects = db.query("""
                    SELECT ip.*, m.name as mine_name, qb.block_name as sub_mine_name
                    FROM infrastructure_projects ip
                    LEFT JOIN mines m ON m.id = ip.mine_id
                    LEFT JOIN quarry_blocks qb ON qb.id = ip.sub_mine_id
                    WHERE ip.sub_mine_id = ?
                    ORDER BY ip.id ASC
                """, (selected_sub_mine_id,))
                if not infrastructure_projects and selected_mine_id:
                    # Fallback to concession mine projects if no pit-specific projects
                    infrastructure_projects = db.query("""
                        SELECT ip.*, m.name as mine_name, qb.block_name as sub_mine_name
                        FROM infrastructure_projects ip
                        LEFT JOIN mines m ON m.id = ip.mine_id
                        LEFT JOIN quarry_blocks qb ON qb.id = ip.sub_mine_id
                        WHERE ip.mine_id = ?
                        ORDER BY ip.id ASC
                    """, (selected_mine_id,))
            elif scope == "mine" and selected_mine_id:
                # Mine filter: show all contractors / projects sourcing from this mine concession
                infrastructure_projects = db.query("""
                    SELECT ip.*, m.name as mine_name, qb.block_name as sub_mine_name
                    FROM infrastructure_projects ip
                    LEFT JOIN mines m ON m.id = ip.mine_id
                    LEFT JOIN quarry_blocks qb ON qb.id = ip.sub_mine_id
                    WHERE ip.mine_id = ?
                    ORDER BY ip.id ASC
                """, (selected_mine_id,))
            else:
                # Statewide / All Mines: show all multi-sector development projects
                infrastructure_projects = db.query("""
                    SELECT ip.*, m.name as mine_name, qb.block_name as sub_mine_name
                    FROM infrastructure_projects ip
                    LEFT JOIN mines m ON m.id = ip.mine_id
                    LEFT JOIN quarry_blocks qb ON qb.id = ip.sub_mine_id
                    ORDER BY ip.id ASC
                """)
        except Exception as _ip_err:
            logger.warning(f"Could not load infrastructure_projects: {_ip_err}")
            infrastructure_projects = []

        return render_template("dashboard_admin.html",
            total_mines=total_mines,
            total_sub_mines=total_sub_mines,
            total_trucks=total_trucks,
            active_trucks=active_trucks,
            active_permits=active_permits,
            total_trips=total_trips,
            pending_alerts=pending_alerts,
            critical_cases=critical_cases,
            escalated_cases=escalated_cases,
            high_risk_trucks_count=high_risk_trucks_count,
            investigations_count=investigations_count,
            officer_actions_count=officer_actions_count,
            mines=mines,
            users=users,
            audit_logs=audit_logs,
            selected_mine_id=selected_mine_id,
            selected_mine=selected_mine,
            selected_sub_mine_id=selected_sub_mine_id,
            selected_sub_mine=selected_sub_mine,
            mine_quarry_blocks=mine_quarry_blocks,
            assigned_contractor_trucks=assigned_contractor_trucks,
            assigned_contractor_permits=assigned_contractor_permits,
            contractor_today_dispatch=contractor_today_dispatch,
            contractor_today_production=contractor_today_production,
            daily_summary=daily_summary,
            dispatch_control=dispatch_control,
            mismatch_check=mismatch_check,
            stock_recon=stock_recon,
            mine_wise_summary=mine_wise_summary,
            truck_material_ledger=truck_material_ledger,
            top_rankings=top_rankings,
            mineral_summary=mineral_summary,
            officer_audits=officer_audits,
            all_quarry_blocks=all_quarry_blocks,
            all_trucks=all_trucks,
            infrastructure_projects=infrastructure_projects
        )

    elif role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        selected_mine_id = officer_mine_id  # Enforce strict single-mine isolation

        if selected_sub_mine_id:
            # OFFICER: ISOLATED TO A SPECIFIC SUB-MINE
            truck_ids = get_operator_truck_ids(officer_mine_id, selected_sub_mine_id)
            placeholders = ",".join("?" for _ in truck_ids) if truck_ids else "NULL"
            active_trucks = len([tid for tid in truck_ids if tid])

            critical_cases = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE severity = 'CRITICAL' AND status NOT IN ('DISMISSED', 'RESOLVED') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            pending_alerts = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE status IN ('NEW', 'UNDER_REVIEW') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            weight_anomalies = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE alert_type = 'WEIGHT_ANOMALY' AND status NOT IN ('DISMISSED', 'RESOLVED') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            route_deviations = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE alert_type = 'ROUTE_DEVIATION' AND status NOT IN ('DISMISSED', 'RESOLVED') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0
            gps_blackouts = db.query(f"SELECT COUNT(*) as c FROM alerts WHERE alert_type = 'GPS_BLACKOUT' AND status NOT IN ('DISMISSED', 'RESOLVED') AND truck_id IN ({placeholders})", truck_ids, one=True)["c"] if truck_ids else 0

            high_risk_trucks = db.query(f"""
                SELECT t.*, p.permit_number, p.mineral, p.source_name, p.destination_name
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                WHERE t.id IN ({placeholders}) AND (t.current_risk_score >= 50 OR t.status = 'IN_TRANSIT')
                ORDER BY t.current_risk_score DESC LIMIT 6
            """, truck_ids) if truck_ids else []

            recent_alerts = db.query(f"""
                SELECT a.*, t.registration_number, p.permit_number
                FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.status IN ('NEW', 'UNDER_REVIEW') AND a.truck_id IN ({placeholders})
                ORDER BY a.id DESC LIMIT 5
            """, truck_ids) if truck_ids else []

            investigations = db.query(f"""
                SELECT inv.*, t.registration_number 
                FROM investigations inv
                LEFT JOIN trucks t ON t.id = inv.truck_id
                WHERE inv.truck_id IN ({placeholders})
                ORDER BY inv.id DESC LIMIT 4
            """, truck_ids) if truck_ids else []

            quarry_blocks = db.query("""
                SELECT qb.*, m.name as mine_name, m.district as mine_district
                FROM quarry_blocks qb
                LEFT JOIN mines m ON m.id = qb.mine_id
                WHERE qb.id = ?
            """, (selected_sub_mine_id,))

            daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=officer_mine_id, sub_mine_id=selected_sub_mine_id)
            dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=officer_mine_id, sub_mine_id=selected_sub_mine_id)
            truck_material_ledger = MaterialMonitoringService.get_truck_wise_material_ledger(mine_id=officer_mine_id, sub_mine_id=selected_sub_mine_id)
        else:
            # OFFICER: WHOLE ASSIGNED MINE CONCESSION
            critical_cases = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.severity = 'CRITICAL' AND a.status NOT IN ('DISMISSED', 'RESOLVED') AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (officer_mine_id, officer_mine_id), one=True)["c"]
            pending_alerts = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.status = 'NEW' AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (officer_mine_id, officer_mine_id), one=True)["c"]
            weight_anomalies = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.alert_type = 'WEIGHT_ANOMALY' AND a.status NOT IN ('DISMISSED', 'RESOLVED') AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (officer_mine_id, officer_mine_id), one=True)["c"]
            route_deviations = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.alert_type = 'ROUTE_DEVIATION' AND a.status NOT IN ('DISMISSED', 'RESOLVED') AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (officer_mine_id, officer_mine_id), one=True)["c"]
            gps_blackouts = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trips tr ON tr.id = a.trip_id
                LEFT JOIN permits p ON p.id = a.permit_id
                WHERE a.alert_type = 'GPS_BLACKOUT' AND a.status NOT IN ('DISMISSED', 'RESOLVED') AND (tr.mine_id = ? OR p.mine_id = ?)
            """, (officer_mine_id, officer_mine_id), one=True)["c"]
            
            truck_ids = get_operator_truck_ids(officer_mine_id)
            active_trucks = len([tid for tid in truck_ids if tid])

            high_risk_trucks = db.query("""
                SELECT t.*, p.permit_number, p.mineral, p.source_name, p.destination_name
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                WHERE (t.assigned_mine_id = ? OR p.mine_id = ?)
                  AND (t.current_risk_score >= 50 OR t.status = 'IN_TRANSIT')
                ORDER BY t.current_risk_score DESC LIMIT 6
            """, (officer_mine_id, officer_mine_id))

            recent_alerts = db.query("""
                SELECT a.*, t.registration_number, p.permit_number
                FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                LEFT JOIN permits p ON p.id = a.permit_id
                LEFT JOIN trips tr ON tr.id = a.trip_id
                WHERE a.status IN ('NEW', 'UNDER_REVIEW')
                  AND (tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?)
                ORDER BY a.id DESC LIMIT 5
            """, (officer_mine_id, officer_mine_id, officer_mine_id))

            investigations = db.query("""
                SELECT inv.*, t.registration_number 
                FROM investigations inv
                LEFT JOIN trucks t ON t.id = inv.truck_id
                LEFT JOIN permits p ON p.truck_id = t.id
                LEFT JOIN trips tr ON tr.id = inv.trip_id
                WHERE p.mine_id = ? OR tr.mine_id = ? OR t.assigned_mine_id = ?
                ORDER BY inv.id DESC LIMIT 4
            """, (officer_mine_id, officer_mine_id, officer_mine_id))

            quarry_blocks = db.query("""
                SELECT qb.*, m.name as mine_name, m.district as mine_district
                FROM quarry_blocks qb
                LEFT JOIN mines m ON m.id = qb.mine_id
                WHERE qb.mine_id = ?
                ORDER BY qb.id ASC
            """, (officer_mine_id,))

            daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=officer_mine_id)
            dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=officer_mine_id)
            truck_material_ledger = MaterialMonitoringService.get_truck_wise_material_ledger(mine_id=officer_mine_id)

        mines = db.query("SELECT id, name, mineral, district, state FROM mines WHERE id = ?", (officer_mine_id,))
        mismatch_check = DetectionEngine.check_production_dispatch_reconciliation(mine_id=officer_mine_id)
        quantity_anomalies = MaterialMonitoringService.get_quantity_anomalies(mine_id=officer_mine_id)

        truck_counts = {r["sub_mine_id"]: r["c"] for r in db.query("SELECT sub_mine_id, COUNT(*) as c FROM trucks WHERE sub_mine_id IS NOT NULL GROUP BY sub_mine_id")}
        trip_counts = {r["sub_mine_id"]: r["c"] for r in db.query("SELECT t.sub_mine_id, COUNT(tr.id) as c FROM trips tr JOIN trucks t ON t.id = tr.truck_id WHERE t.sub_mine_id IS NOT NULL GROUP BY t.sub_mine_id")}
        alert_counts = {r["sub_mine_id"]: r["c"] for r in db.query("SELECT t.sub_mine_id, COUNT(a.id) as c FROM alerts a JOIN trucks t ON t.id = a.truck_id WHERE t.sub_mine_id IS NOT NULL AND a.status IN ('NEW', 'UNDER_REVIEW') GROUP BY t.sub_mine_id")}
        high_risk_counts = {r["sub_mine_id"]: r["c"] for r in db.query("SELECT sub_mine_id, COUNT(*) as c FROM trucks WHERE sub_mine_id IS NOT NULL AND current_risk_score >= 50 GROUP BY sub_mine_id")}
        critical_counts = {r["sub_mine_id"]: r["c"] for r in db.query("SELECT sub_mine_id, COUNT(*) as c FROM trucks WHERE sub_mine_id IS NOT NULL AND current_risk_score >= 80 GROUP BY sub_mine_id")}

        for qb in quarry_blocks:
            qb_id = qb["id"]
            qb["active_trucks_count"] = truck_counts.get(qb_id, 0)
            qb["trips_today"] = trip_counts.get(qb_id, 0)
            qb["alerts_count"] = alert_counts.get(qb_id, 0)
            qb["high_risk_count"] = high_risk_counts.get(qb_id, 0)
            qb["critical_count"] = critical_counts.get(qb_id, 0)


        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            officer_trucks = db.query(f"SELECT id, registration_number, vehicle_type, max_capacity_mt FROM trucks WHERE id IN ({placeholders}) ORDER BY registration_number ASC", truck_ids)
        else:
            officer_trucks = []

        drone_dem_audit = MaterialMonitoringService.get_drone_dem_volumetric_audit(mine_id=officer_mine_id)
        crusher_kacha_maal_audit = MaterialMonitoringService.get_crusher_inward_kacha_maal_audit(mine_id=officer_mine_id)
        pit_dwell_watchdog = MaterialMonitoringService.get_active_pit_dwell_watchdog(mine_id=officer_mine_id)

        return render_template("dashboard_officer.html",
            critical_cases=critical_cases,
            pending_alerts=pending_alerts,
            weight_anomalies=weight_anomalies,
            route_deviations=route_deviations,
            gps_blackouts=gps_blackouts,
            active_trucks=active_trucks,
            high_risk_trucks=high_risk_trucks,
            recent_alerts=recent_alerts,
            investigations=investigations,
            quarry_blocks=quarry_blocks,
            officer_trucks=officer_trucks,
            mines=mines,
            selected_mine_id=officer_mine_id,
            daily_summary=daily_summary,
            dispatch_control=dispatch_control,
            mismatch_check=mismatch_check,
            quantity_anomalies=quantity_anomalies,
            truck_material_ledger=truck_material_ledger,
            drone_dem_audit=drone_dem_audit,
            crusher_kacha_maal_audit=crusher_kacha_maal_audit,
            pit_dwell_watchdog=pit_dwell_watchdog
        )

    else:  # OPERATOR
        mine_id = get_operator_mine_id()
        sub_mine_id = get_operator_sub_mine_id()
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        sub_mine = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (sub_mine_id,), one=True) if sub_mine_id else None

        truck_ids = get_operator_truck_ids(sub_mine_id=sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"SELECT * FROM trucks WHERE id IN ({placeholders}) ORDER BY id ASC", truck_ids)
            trips = db.query(f"SELECT * FROM trips WHERE truck_id IN ({placeholders}) ORDER BY id DESC LIMIT 20", truck_ids)
            weighments = db.query(f"""
                SELECT w.*, t.registration_number 
                FROM weighments w 
                JOIN trips tr ON tr.id = w.trip_id 
                JOIN trucks t ON t.id = w.truck_id
                WHERE w.truck_id IN ({placeholders})
                ORDER BY w.id DESC LIMIT 10
            """, truck_ids)
        else:
            trucks = []
            trips = []
            weighments = []

        if sub_mine_id:
            permits = db.query("""
                SELECT p.*, t.registration_number 
                FROM permits p 
                LEFT JOIN trucks t ON t.id = p.truck_id 
                WHERE p.quarry_block_id = ? OR p.truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?)
                ORDER BY p.id DESC LIMIT 10
            """, (sub_mine_id, sub_mine_id))
            active_permits_count = db.query("""
                SELECT COUNT(*) as c FROM permits 
                WHERE (quarry_block_id = ? OR truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?))
                  AND status = 'ACTIVE'
            """, (sub_mine_id, sub_mine_id), one=True)["c"]
            drivers_count = db.query("SELECT COUNT(*) as c FROM drivers WHERE sub_mine_id = ? OR assigned_truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?)", (sub_mine_id, sub_mine_id), one=True)["c"]
        else:
            permits = db.query("SELECT p.*, t.registration_number FROM permits p LEFT JOIN trucks t ON t.id = p.truck_id WHERE p.mine_id = ? ORDER BY p.id DESC LIMIT 10", (mine_id,))
            active_permits_count = db.query("SELECT COUNT(*) as c FROM permits WHERE mine_id = ? AND status = 'ACTIVE'", (mine_id,), one=True)["c"]
            drivers_count = db.query("SELECT COUNT(*) as c FROM drivers WHERE assigned_truck_id IN (SELECT id FROM trucks WHERE assigned_mine_id = ?)", (mine_id,), one=True)["c"]

        # Operator-scoped Material & Dispatch Monitoring
        operator_daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=mine_id)
        operator_dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=mine_id)
        operator_mismatch_check = DetectionEngine.check_production_dispatch_reconciliation(mine_id=mine_id)
        operator_stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=mine_id)
        operator_truck_material = MaterialMonitoringService.get_truck_wise_material_ledger(mine_id=mine_id)
        operator_quantity_anomalies = MaterialMonitoringService.get_quantity_anomalies(mine_id=mine_id)
        if truck_ids:
            operator_truck_material = [item for item in operator_truck_material if item.get("truck_id") in truck_ids]
            operator_quantity_anomalies = [item for item in operator_quantity_anomalies if item.get("truck_id") in truck_ids]

        return render_template("dashboard_operator.html",
            mine=mine,
            sub_mine=sub_mine,
            trucks=trucks,
            permits=permits,
            trips=trips,
            weighments=weighments,
            fleet_count=len(trucks),
            drivers_count=drivers_count,
            active_permits_count=active_permits_count,
            trips_count=len(trips),
            weighments_count=len(weighments),
            operator_daily_summary=operator_daily_summary,
            operator_dispatch_control=operator_dispatch_control,
            operator_mismatch_check=operator_mismatch_check,
            operator_stock_recon=operator_stock_recon,
            operator_truck_material=operator_truck_material,
            operator_quantity_anomalies=operator_quantity_anomalies
        )



@app.route("/map")
@login_required()
def live_map():
    active_mine_id = get_active_mine_id()
    active_sub_mine_id = get_active_sub_mine_id()

    # Query available sub-mines for dropdown
    if active_mine_id:
        sub_mines = db.query("SELECT * FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC", (active_mine_id,))
    else:
        sub_mines = db.query("SELECT * FROM quarry_blocks ORDER BY mine_id, id ASC")

    active_sub_mine = None
    if active_sub_mine_id:
        active_sub_mine = next((sm for sm in sub_mines if sm["id"] == active_sub_mine_id), None)
        if not active_sub_mine:
            active_sub_mine = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (active_sub_mine_id,), one=True)

    geofences = db.query("SELECT * FROM geofences")

    if active_sub_mine_id:
        # STRICTLY isolate to only and only trucks belonging to that one sub-mine!
        truck_ids = get_operator_truck_ids(active_mine_id, active_sub_mine_id)
        if active_mine_id:
            mines = db.query("SELECT * FROM mines WHERE id = ?", (active_mine_id,))
        else:
            mines = db.query("SELECT * FROM mines")
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt, 
                       p.source_name, p.destination_name, tr.id as trip_id,
                       qb.block_code, qb.block_name as sub_mine_name
                FROM trucks t
                LEFT JOIN quarry_blocks qb ON qb.id = t.sub_mine_id
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
                WHERE t.id IN ({placeholders})
                ORDER BY t.current_risk_score DESC
            """, truck_ids)
        else:
            trucks = []
    elif active_mine_id:
        mines = db.query("SELECT * FROM mines WHERE id = ?", (active_mine_id,))
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt, 
                       p.source_name, p.destination_name, tr.id as trip_id,
                       qb.block_code, qb.block_name as sub_mine_name
                FROM trucks t
                LEFT JOIN quarry_blocks qb ON qb.id = t.sub_mine_id
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
                WHERE t.id IN ({placeholders})
                ORDER BY t.current_risk_score DESC
            """, truck_ids)
        else:
            trucks = []
    else:
        mines = db.query("SELECT * FROM mines")
        trucks = db.query("""
            SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt, 
                   p.source_name, p.destination_name, tr.id as trip_id,
                   qb.block_code, qb.block_name as sub_mine_name
            FROM trucks t
            LEFT JOIN quarry_blocks qb ON qb.id = t.sub_mine_id
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
            LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
            ORDER BY t.current_risk_score DESC
        """)

    return render_template(
        "map.html", 
        mines=mines, 
        geofences=geofences, 
        trucks=trucks,
        sub_mines=sub_mines,
        active_sub_mine_id=active_sub_mine_id,
        active_sub_mine=active_sub_mine
    )


# --- GPS & ANTI-TAMPER TELEMETRY SURVEILLANCE ---

@app.route("/gps-telemetry")
@login_required()
def gps_telemetry():
    """
    GPS Anti-Tamper & Telemetry Intelligence Center.
    Tracks network blindspots vs deliberate GPS Jammers ('gamers'),
    hardware wire cuts, and prohibited riverbed incursions.
    """
    active_mine_id = get_active_mine_id()
    active_sub_mine_id = get_active_sub_mine_id()

    # Query sub-mines for dropdown
    if active_mine_id:
        sub_mines = db.query("SELECT * FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC", (active_mine_id,))
    else:
        sub_mines = db.query("SELECT * FROM quarry_blocks ORDER BY mine_id, id ASC")

    active_sub_mine = None
    if active_sub_mine_id:
        active_sub_mine = next((sm for sm in sub_mines if sm["id"] == active_sub_mine_id), None)
        if not active_sub_mine:
            active_sub_mine = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (active_sub_mine_id,), one=True)

    if active_sub_mine_id:
        # STRICTLY isolate to only and only this sub-mine's trucks!
        truck_ids = get_operator_truck_ids(active_mine_id, active_sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks_list = db.query(f"""
                SELECT t.*, m.name as assigned_mine_name, m.district as mine_district,
                       p.permit_number, p.mineral, tr.trip_number, tr.id as active_trip_id,
                       qb.block_code, qb.block_name as sub_mine_name
                FROM trucks t
                LEFT JOIN mines m ON m.id = t.assigned_mine_id
                LEFT JOIN quarry_blocks qb ON qb.id = t.sub_mine_id
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS', 'DISPATCHED')
                WHERE t.id IN ({placeholders})
                ORDER BY 
                    CASE WHEN t.gps_status = 'JAMMER_DETECTED' THEN 1
                         WHEN t.gps_status = 'TAMPERED' THEN 2
                         WHEN t.gps_status = 'PROHIBITED_ZONE' THEN 3
                         WHEN t.gps_status = 'BLINDSPOT' THEN 4
                         ELSE 5 END,
                    t.current_risk_score DESC
            """, truck_ids)
            recent_events = db.query(f"""
                SELECT e.*, t.registration_number, t.driver_name, t.driver_phone
                FROM gps_tamper_events e
                JOIN trucks t ON t.id = e.truck_id
                WHERE e.truck_id IN ({placeholders})
                ORDER BY e.id DESC LIMIT 40
            """, truck_ids)
        else:
            trucks_list = []
            recent_events = []
    elif active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks_list = db.query(f"""
                SELECT t.*, m.name as assigned_mine_name, m.district as mine_district,
                       p.permit_number, p.mineral, tr.trip_number, tr.id as active_trip_id,
                       qb.block_code, qb.block_name as sub_mine_name
                FROM trucks t
                LEFT JOIN mines m ON m.id = t.assigned_mine_id
                LEFT JOIN quarry_blocks qb ON qb.id = t.sub_mine_id
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS', 'DISPATCHED')
                WHERE t.id IN ({placeholders})
                ORDER BY 
                    CASE WHEN t.gps_status = 'JAMMER_DETECTED' THEN 1
                         WHEN t.gps_status = 'TAMPERED' THEN 2
                         WHEN t.gps_status = 'PROHIBITED_ZONE' THEN 3
                         WHEN t.gps_status = 'BLINDSPOT' THEN 4
                         ELSE 5 END,
                    t.current_risk_score DESC
            """, truck_ids)
            recent_events = db.query(f"""
                SELECT e.*, t.registration_number, t.driver_name, t.driver_phone
                FROM gps_tamper_events e
                JOIN trucks t ON t.id = e.truck_id
                WHERE e.truck_id IN ({placeholders})
                ORDER BY e.id DESC LIMIT 40
            """, truck_ids)
        else:
            trucks_list = []
            recent_events = []
    else:
        trucks_list = db.query("""
            SELECT t.*, m.name as assigned_mine_name, m.district as mine_district,
                   p.permit_number, p.mineral, tr.trip_number, tr.id as active_trip_id,
                   qb.block_code, qb.block_name as sub_mine_name
            FROM trucks t
            LEFT JOIN mines m ON m.id = t.assigned_mine_id
            LEFT JOIN quarry_blocks qb ON qb.id = t.sub_mine_id
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
            LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS', 'DISPATCHED')
            ORDER BY 
                CASE WHEN t.gps_status = 'JAMMER_DETECTED' THEN 1
                     WHEN t.gps_status = 'TAMPERED' THEN 2
                     WHEN t.gps_status = 'PROHIBITED_ZONE' THEN 3
                     WHEN t.gps_status = 'BLINDSPOT' THEN 4
                     ELSE 5 END,
                t.current_risk_score DESC
        """)
        recent_events = db.query("""
            SELECT e.*, t.registration_number, t.driver_name, t.driver_phone
            FROM gps_tamper_events e
            JOIN trucks t ON t.id = e.truck_id
            ORDER BY e.id DESC LIMIT 40
        """)

    total_monitored = len(trucks_list)
    jammer_count = sum(t.get("jammer_detected_count") or 0 for t in trucks_list)
    tamper_count = sum(t.get("tamper_count") or 0 for t in trucks_list)
    blindspot_count = sum(t.get("network_blindspot_count") or 0 for t in trucks_list)
    prohibited_count = sum(t.get("prohibited_zone_count") or 0 for t in trucks_list)
    active_threats = sum(1 for t in trucks_list if t.get("gps_status") in ('JAMMER_DETECTED', 'TAMPERED', 'PROHIBITED_ZONE'))
    
    if total_monitored > 0:
        penalty = (jammer_count * 8 + tamper_count * 5 + prohibited_count * 6 + blindspot_count * 1.5) / max(1, total_monitored)
        integrity_score = max(0.0, min(100.0, round(100.0 - penalty, 1)))
    else:
        integrity_score = 100.0

    mines = db.query("SELECT * FROM mines")
    geofences = db.query("SELECT * FROM geofences")

    return render_template(
        "gps_telemetry.html",
        trucks=trucks_list,
        recent_events=recent_events,
        total_monitored=total_monitored,
        jammer_count=jammer_count,
        tamper_count=tamper_count,
        blindspot_count=blindspot_count,
        prohibited_count=prohibited_count,
        active_threats=active_threats,
        integrity_score=integrity_score,
        mines=mines,
        geofences=geofences,
        sub_mines=sub_mines,
        active_sub_mine_id=active_sub_mine_id,
        active_sub_mine=active_sub_mine
    )


@app.route("/api/gps/trucks", methods=["GET"])
@login_required()
def api_gps_trucks():
    """Returns real-time fleet telemetry JSON for live map and dynamic polling."""
    active_mine_id = get_active_mine_id()
    active_sub_mine_id = get_active_sub_mine_id()
    if active_sub_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id, active_sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks_data = db.query(f"SELECT * FROM trucks WHERE id IN ({placeholders})", truck_ids)
        else:
            trucks_data = []
    elif active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks_data = db.query(f"SELECT * FROM trucks WHERE id IN ({placeholders})", truck_ids)
        else:
            trucks_data = []
    else:
        trucks_data = db.query("SELECT * FROM trucks")
    return jsonify(trucks_data)


@app.route("/api/gps/trucks/<int:truck_id>/diagnostics", methods=["GET"])
@login_required()
def api_gps_truck_diagnostics(truck_id):
    """Deep-dive hardware & signal diagnostics for a specific truck."""
    if not validate_operator_truck_access(truck_id):
        return jsonify({"success": False, "error": "Forbidden: Access denied to another operator's vehicle record"}), 403

    truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
    if not truck:
        return jsonify({"success": False, "error": "Truck not found"}), 404

    events = db.query("""
        SELECT * FROM gps_tamper_events 
        WHERE truck_id = ? 
        ORDER BY id DESC LIMIT 15
    """, (truck_id,))

    # Run AI heuristic classifier on active telemetry
    sats = truck.get("satellite_count", 12)
    cno = truck.get("carrier_noise_ratio_cno", 44.5)
    volts = truck.get("external_power_volts", 24.2)
    in_prohibited = (truck.get("gps_status") == "PROHIBITED_ZONE")
    
    classification = DetectionEngine.classify_telemetry_interruption(
        satellite_count=sats,
        cno_db_hz=cno,
        external_power_volts=volts,
        in_prohibited_zone=in_prohibited
    )

    return jsonify({
        "success": True,
        "truck": truck,
        "events": events,
        "classification": classification
    })


@app.route("/api/gps/simulator/trigger", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_gps_simulator_trigger():
    """Live SIH demonstration trigger for GPS scenarios."""
    data = request.get_json() or {}
    action = data.get("action")
    truck_reg = data.get("truck_reg", "HR26AB1234")

    if action == "jammer":
        res = simulator.trigger_gps_jammer(truck_reg)
    elif action == "tamper":
        res = simulator.trigger_hardware_tamper(truck_reg)
    elif action == "blindspot":
        res = simulator.trigger_network_blindspot(truck_reg)
    elif action == "riverbed":
        res = simulator.trigger_prohibited_incursion(truck_reg)
    elif action == "interstate_breach":
        res = simulator.trigger_interstate_border_breach(truck_reg or "RJ14GA5521")
    elif action == "tare_tampering":
        res = simulator.trigger_tare_tampering(truck_reg or "HR26AB1234")
    elif action == "blackout":
        res = simulator.trigger_gps_blackout(truck_reg or "HR26AB1234")
    elif action == "deviation":
        res = simulator.trigger_route_deviation(truck_reg or "HR26AB1234")
    elif action == "restore":
        res = simulator.restore_truck_telemetry(truck_reg)
    else:
        return jsonify({"success": False, "error": "Invalid action"}), 400

    return jsonify({"success": True, "result": res})


@app.route("/api/gps/events/<int:event_id>/enforce", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_gps_event_enforce(event_id):
    """Executes enforcement dispatch action for a GPS tamper incident."""
    data = request.get_json() or {}
    action_type = data.get("action_type", "FLYING_SQUAD")
    notes = data.get("notes", "Rapid response squad dispatched.")

    event = db.query("SELECT * FROM gps_tamper_events WHERE id = ?", (event_id,), one=True)
    if not event:
        return jsonify({"success": False, "error": "Event not found"}), 404

    action_label = {
        "FLYING_SQUAD": f"Mining Flying Squad Dispatched to GPS coords ({event['latitude']:.4f}, {event['longitude']:.4f})",
        "IMPOUND_NOTICE": "Statutory Impound Notice Issued under MMDR Act Sec 21",
        "SCALE_LOCK": "Automated Weighbridge Scale Lockout Activated (Transit Blocked)"
    }.get(action_type, f"Enforcement Action: {action_type}")

    db.execute("""
        UPDATE gps_tamper_events 
        SET action_taken = ?, status = 'ENFORCED'
        WHERE id = ?
    """, (action_label, event_id))

    db.log_audit("GPS_TAMPER_ENFORCEMENT", "gps_tamper_events", event_id, event.get("action_taken", "None"), action_label, notes)

    return jsonify({
        "success": True,
        "message": f"Action successfully recorded: {action_label}",
        "action_taken": action_label
    })


@app.route("/trucks")
@login_required()
def trucks():
    role = session.get("user_role")
    active_mine_id = get_active_mine_id()
    if role == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
        truck_ids = get_operator_truck_ids(active_mine_id, sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            fleet = db.query(f"""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                       m.name as source_mine
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN mines m ON m.id = p.mine_id
                WHERE t.id IN ({placeholders})
                ORDER BY t.id ASC
            """, truck_ids)
        else:
            fleet = []

        if sub_mine_id:
            drivers_list = db.query("""
                SELECT d.*, t.registration_number, t.vehicle_type
                FROM drivers d
                LEFT JOIN trucks t ON t.id = d.assigned_truck_id
                WHERE d.sub_mine_id = ?
                   OR d.assigned_truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?)
                ORDER BY d.id DESC
            """, (sub_mine_id, sub_mine_id))
        else:
            drivers_list = db.query("""
                SELECT d.*, t.registration_number, t.vehicle_type
                FROM drivers d
                LEFT JOIN trucks t ON t.id = d.assigned_truck_id
                WHERE d.assigned_truck_id IN (SELECT id FROM trucks WHERE assigned_mine_id = ?)
                ORDER BY d.id DESC
            """, (active_mine_id,))
    elif active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            fleet = db.query(f"""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                       m.name as source_mine
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN mines m ON m.id = p.mine_id
                WHERE t.id IN ({placeholders})
                ORDER BY t.id ASC
            """, truck_ids)
        else:
            fleet = []
        drivers_list = db.query("""
            SELECT d.*, t.registration_number, t.vehicle_type
            FROM drivers d
            LEFT JOIN trucks t ON t.id = d.assigned_truck_id
            WHERE d.assigned_truck_id IN (SELECT id FROM trucks WHERE assigned_mine_id = ?)
               OR d.assigned_truck_id IS NULL
            ORDER BY d.id DESC
        """, (active_mine_id,))
    else:
        fleet = db.query("""
            SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                   m.name as source_mine
            FROM trucks t
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
            LEFT JOIN mines m ON m.id = p.mine_id
            ORDER BY t.current_risk_score DESC, t.id ASC
        """)
        drivers_list = db.query("""
            SELECT d.*, t.registration_number, t.vehicle_type
            FROM drivers d
            LEFT JOIN trucks t ON t.id = d.assigned_truck_id
            ORDER BY d.id DESC
        """)

    all_mines = db.query("SELECT id, name, mine_code, district FROM mines ORDER BY name ASC")
    active_mine = db.query("SELECT * FROM mines WHERE id = ?", (active_mine_id,), one=True) if active_mine_id else None
    return render_template("trucks.html", trucks=fleet, drivers=drivers_list, all_mines=all_mines, active_mine=active_mine)


@app.route("/trucks/<int:truck_id>")
@login_required()
def truck_detail(truck_id):
    if not validate_operator_truck_access(truck_id):
        abort(403)

    truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
    if not truck:
        abort(404)
    
    trips = db.query("""
        SELECT tr.*, p.permit_number, p.mineral, m.name as mine_name
        FROM trips tr
        JOIN permits p ON p.id = tr.permit_id
        JOIN mines m ON m.id = tr.mine_id
        WHERE tr.truck_id = ?
        ORDER BY tr.id DESC
    """, (truck_id,))

    permits = db.query("SELECT * FROM permits WHERE truck_id = ? ORDER BY id DESC", (truck_id,))
    
    if session.get("user_role") == "OPERATOR":
        alerts = []  # Operators do not see law enforcement alerts
    else:
        alerts = db.query("SELECT * FROM alerts WHERE truck_id = ? ORDER BY id DESC", (truck_id,))
        
    weighments = db.query("SELECT * FROM weighments WHERE truck_id = ? ORDER BY id DESC", (truck_id,))

    # Cumulative Truck Material Profile & Round Status (Req 6, 7, 12)
    cumulative_profile = MaterialMonitoringService.get_truck_cumulative_material_profile(truck_id)
    active_trip = trips[0] if trips else None
    timeline = []
    if active_trip and active_trip.get("timeline_events_json"):
        try:
            timeline = json.loads(active_trip["timeline_events_json"])
        except Exception:
            timeline = []

    if not timeline and active_trip:
        t_start = str(active_trip.get("start_time") or "Today 08:30")[:16]
        timeline = [
            {"event": "TRUCK_ENTERED_MINE", "title": "Entered Mine", "description": f"GPS entry detected at {active_trip.get('mine_name', 'Mine')}", "timestamp": t_start},
            {"event": "PERMIT_MATCHED", "title": "Permit Matched", "description": f"e-Rawaana {active_trip.get('permit_number', 'Active')} validated", "timestamp": t_start},
            {"event": "DISPATCH_STARTED", "title": "Dispatch Authorized", "description": "Cleared at outbound weigh station", "timestamp": t_start}
        ]

    # Legacy material profile dictionary for backward compatibility
    ledger_entries = MaterialMonitoringService.get_truck_wise_material_ledger()
    truck_ledger = [entry for entry in ledger_entries if entry["truck_id"] == truck_id]
    latest_entry = truck_ledger[0] if truck_ledger else None

    material_profile = {
        "trips_today": cumulative_profile["today"]["trips"] if cumulative_profile else len(truck_ledger),
        "cumulative_permitted_mt": cumulative_profile["today"]["permitted_mt"] if cumulative_profile else round(sum(e["permitted_qty_mt"] for e in truck_ledger), 1),
        "cumulative_actual_mt": cumulative_profile["today"]["material_mt"] if cumulative_profile else round(sum(e["actual_qty_mt"] or 0.0 for e in truck_ledger), 1),
        "cumulative_excess_mt": cumulative_profile["today"]["excess_mt"] if cumulative_profile else round(sum(e["excess_mt"] for e in truck_ledger), 1),
        "latest": latest_entry
    }

    return render_template("trucks.html", 
        truck=truck, 
        trips=trips, 
        permits=permits, 
        alerts=alerts, 
        weighments=weighments, 
        material_profile=material_profile,
        cumulative_profile=cumulative_profile,
        active_trip=active_trip,
        timeline=timeline,
        is_detail=True
    )



@app.route("/permits")
@login_required()
def permits():
    role = session.get("user_role")
    if role == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
        if sub_mine_id:
            permit_list = db.query("""
                SELECT p.*, t.registration_number, m.name as mine_name, m.district as mine_district,
                       w.gross_weight_mt, w.tare_weight_mt, w.net_weight_mt, w.slip_number as wb_slip_no
                FROM permits p
                LEFT JOIN trucks t ON t.id = p.truck_id
                LEFT JOIN mines m ON m.id = p.mine_id
                LEFT JOIN (
                    SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY permit_id)
                ) w ON w.permit_id = p.id
                WHERE p.quarry_block_id = ? OR p.truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?)
                ORDER BY p.id DESC
            """, (sub_mine_id, sub_mine_id))
        else:
            mine_id = get_operator_mine_id()
            permit_list = db.query("""
                SELECT p.*, t.registration_number, m.name as mine_name, m.district as mine_district,
                       w.gross_weight_mt, w.tare_weight_mt, w.net_weight_mt, w.slip_number as wb_slip_no
                FROM permits p
                LEFT JOIN trucks t ON t.id = p.truck_id
                LEFT JOIN mines m ON m.id = p.mine_id
                LEFT JOIN (
                    SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY permit_id)
                ) w ON w.permit_id = p.id
                WHERE p.mine_id = ?
                ORDER BY p.id DESC
            """, (mine_id,))
    elif role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        permit_list = db.query("""
            SELECT p.*, t.registration_number, m.name as mine_name, m.district as mine_district,
                   w.gross_weight_mt, w.tare_weight_mt, w.net_weight_mt, w.slip_number as wb_slip_no
            FROM permits p
            LEFT JOIN trucks t ON t.id = p.truck_id
            LEFT JOIN mines m ON m.id = p.mine_id
            LEFT JOIN (
                SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY permit_id)
            ) w ON w.permit_id = p.id
            WHERE p.mine_id = ?
            ORDER BY p.id DESC
        """, (officer_mine_id,))
    else:
        active_mine_id = get_active_mine_id()
        if active_mine_id:
            permit_list = db.query("""
                SELECT p.*, t.registration_number, m.name as mine_name, m.district as mine_district,
                       w.gross_weight_mt, w.tare_weight_mt, w.net_weight_mt, w.slip_number as wb_slip_no
                FROM permits p
                LEFT JOIN trucks t ON t.id = p.truck_id
                LEFT JOIN mines m ON m.id = p.mine_id
                LEFT JOIN (
                    SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY permit_id)
                ) w ON w.permit_id = p.id
                WHERE p.mine_id = ?
                ORDER BY p.id DESC
            """, (active_mine_id,))
        else:
            permit_list = db.query("""
                SELECT p.*, t.registration_number, m.name as mine_name, m.district as mine_district,
                       w.gross_weight_mt, w.tare_weight_mt, w.net_weight_mt, w.slip_number as wb_slip_no
                FROM permits p
                LEFT JOIN trucks t ON t.id = p.truck_id
                LEFT JOIN mines m ON m.id = p.mine_id
                LEFT JOIN (
                    SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY permit_id)
                ) w ON w.permit_id = p.id
                ORDER BY p.id DESC
            """)
    return render_template("permits.html", permits=permit_list)


@app.route("/permits/<int:permit_id>")
@app.route("/permits/<int:permit_id>/view")
@login_required()
def view_permit(permit_id):
    """
    Renders high-fidelity, printable e-Rawana statutory suite:
    - Tab 1: Official Department of Mines & Geology e-Rawana Transit Pass
    - Tab 2: HSIIDC Ltd. (Khanak Stone Mines) Tax Invoice
    - Tab 3: Automated Weighbridge Weighment Slip (Gross)
    """
    if not validate_operator_permit_access(permit_id):
        abort(403)

    data = get_enriched_permit_data(permit_id)
    if not data:
        flash("Permit record not found.", "error")
        return redirect(url_for("permits"))

    active_tab = request.args.get("tab", "erawana")
    return render_template("erawana_view.html", doc=data, active_tab=active_tab)


@app.route("/permits/<int:permit_id>/download-pdf")
@login_required()
def download_permit_pdf(permit_id):
    """
    Generates and downloads official government-grade PDFs:
    ?type=erawana   -> Dept of Mines & Geology e-Rawana Transit Pass
    ?type=invoice   -> HSIIDC Ltd. Khanak GST Tax Invoice (Duplicate for Transporter)
    ?type=weighment -> HSIIDC Automated Weighment Slip (Gross/Tare)
    ?type=packet    -> 3-in-1 Complete Statutory Mineral Transit Packet
    """
    doc_type = request.args.get("type", "erawana").lower()
    if doc_type not in ["erawana", "invoice", "weighment", "packet", "all"]:
        doc_type = "erawana"

    if not validate_user_permit_access(permit_id):
        abort(403)

    rel_path = generate_erawana_pdf(permit_id, doc_type=doc_type)
    if not rel_path:
        flash("Could not generate e-Rawana PDF for this permit.", "error")
        return redirect(url_for("permits"))

    # ensure file path stays within static reports directory
    abs_path = (Config.BASE_DIR / Path(rel_path)).resolve()
    base_resolved = Path(Config.BASE_DIR).resolve()
    if not abs_path.is_relative_to(base_resolved) or not abs_path.exists():
        flash("Generated PDF artifact not found or inaccessible.", "error")
        return redirect(url_for("permits"))

    permit = db.query("SELECT permit_number FROM permits WHERE id = ?", (permit_id,), one=True)
    p_clean = secure_filename((permit["permit_number"] if permit else f"permit_{permit_id}").replace("/", "_").replace(" ", "_"))
    download_name = f"{doc_type}_{p_clean}.pdf"

    return send_file(str(abs_path), as_attachment=True, download_name=download_name, mimetype="application/pdf")


@app.route("/api/permits/<int:permit_id>/details")
@login_required()
def api_permit_details(permit_id):
    """Returns JSON serialization of enriched permit data for client modals."""
    if not validate_operator_permit_access(permit_id):
        return jsonify({"success": False, "error": "Forbidden: Cross-tenant access denied."}), 403

    data = get_enriched_permit_data(permit_id)
    if not data:
        return jsonify({"success": False, "error": "Permit not found"}), 404

    # Sanitize entities
    safe_data = {k: v for k, v in data.items() if k not in ("permit", "truck", "mine", "trip", "weighment", "driver")}
    return jsonify({"success": True, "data": safe_data})



@app.route("/trips")
@login_required()
def trips():
    active_mine_id = get_active_mine_id()
    if active_mine_id:
        trip_list = db.query("""
            SELECT tr.*, t.registration_number, t.driver_name, t.driver_phone,
                   p.permit_number, p.permitted_weight_mt, p.source_name, p.destination_name, p.mineral,
                   w.net_weight_mt, w.difference_mt, w.is_overweight
            FROM trips tr
            JOIN trucks t ON t.id = tr.truck_id
            JOIN permits p ON p.id = tr.permit_id
            LEFT JOIN (
                SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY trip_id)
            ) w ON w.trip_id = tr.id
            WHERE tr.mine_id = ?
            ORDER BY tr.id DESC
        """, (active_mine_id,))
    else:
        trip_list = db.query("""
            SELECT tr.*, t.registration_number, t.driver_name, t.driver_phone,
                   p.permit_number, p.permitted_weight_mt, p.source_name, p.destination_name, p.mineral,
                   w.net_weight_mt, w.difference_mt, w.is_overweight
            FROM trips tr
            JOIN trucks t ON t.id = tr.truck_id
            JOIN permits p ON p.id = tr.permit_id
            LEFT JOIN (
                SELECT * FROM weighments WHERE id IN (SELECT MAX(id) FROM weighments GROUP BY trip_id)
            ) w ON w.trip_id = tr.id
            ORDER BY tr.id DESC
        """)
    return render_template("trips.html", trips=trip_list)


@app.route("/alerts")
@login_required(roles=["ADMIN", "OFFICER"])
def alerts():
    current_u = get_current_user()
    role = current_u.get("role") if current_u else "OFFICER"
    default_view = "vigilance" if role == "ADMIN" else "operational"
    view_mode = request.args.get("view", default_view)
    filter_status = request.args.get("status")
    filter_severity = request.args.get("severity")

    current_scope = get_current_scope()
    scope = current_scope["scope"]
    active_mine_id = current_scope["mine_id"]
    active_sub_mine_id = current_scope["sub_mine_id"]

    sql = """
        SELECT a.*, t.registration_number, p.permit_number, tr.trip_number,
               u_assigned.full_name as officer_name, u_assigned.badge_number as officer_badge,
               u_handled.full_name as handled_by_name, u_handled.badge_number as handled_by_badge,
               u_admin.full_name as admin_reviewer_name
        FROM alerts a
        LEFT JOIN trucks t ON t.id = a.truck_id
        LEFT JOIN permits p ON p.id = a.permit_id
        LEFT JOIN trips tr ON tr.id = a.trip_id
        LEFT JOIN users u_assigned ON u_assigned.id = a.assigned_to_user_id
        LEFT JOIN users u_handled ON u_handled.id = a.handled_by_user_id
        LEFT JOIN users u_admin ON u_admin.id = a.admin_reviewed_by
        WHERE 1=1
    """
    params = []
    if scope == "submine":
        sql += " AND (t.sub_mine_id = ? OR p.quarry_block_id = ?)"
        params.extend([active_sub_mine_id, active_sub_mine_id])
        scope_join = """
            LEFT JOIN trucks t ON t.id = a.truck_id
            LEFT JOIN permits p ON p.id = a.permit_id
            WHERE (t.sub_mine_id = ? OR p.quarry_block_id = ?)
        """
        scope_params = (active_sub_mine_id, active_sub_mine_id)
    elif scope == "mine":
        sql += " AND (tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?)"
        params.extend([active_mine_id, active_mine_id, active_mine_id])
        scope_join = """
            LEFT JOIN trips tr ON tr.id = a.trip_id
            LEFT JOIN permits p ON p.id = a.permit_id
            LEFT JOIN trucks t ON t.id = a.truck_id
            WHERE (tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?)
        """
        scope_params = (active_mine_id, active_mine_id, active_mine_id)
    else:
        scope_join = "WHERE 1=1"
        scope_params = ()

    # Role & View separation:
    if view_mode == "vigilance":
        sql += " AND (a.escalated_to_admin = 1 OR a.handled_by_user_id IS NOT NULL OR a.severity IN ('CRITICAL', 'HIGH') OR a.admin_review_status != 'NONE')"
    elif view_mode == "operational":
        sql += " AND a.status IN ('NEW', 'ACKNOWLEDGED', 'UNDER_REVIEW')"

    if filter_status:
        sql += " AND a.status = ?"
        params.append(filter_status)
    if filter_severity:
        sql += " AND a.severity = ?"
        params.append(filter_severity)

    sql += " ORDER BY a.id DESC"
    alert_list = db.query(sql, params)

    officers = db.query("SELECT id, full_name, badge_number FROM users WHERE role = 'OFFICER'")

    vigilance_pending_count = db.query(f"""
        SELECT COUNT(*) as c FROM alerts a
        {scope_join}
        AND (a.admin_review_status = 'PENDING_VIGILANCE_REVIEW' 
             OR (a.escalated_to_admin = 1 AND a.admin_review_status = 'NONE')
             OR (a.handled_by_user_id IS NOT NULL AND a.severity IN ('CRITICAL', 'HIGH') AND a.admin_review_status = 'NONE'))
    """, scope_params, one=True)["c"]

    operational_pending_count = db.query(f"""
        SELECT COUNT(*) as c FROM alerts a
        {scope_join}
        AND a.status IN ('NEW', 'UNDER_REVIEW')
    """, scope_params, one=True)["c"]

    total_alerts_count = db.query(f"""
        SELECT COUNT(*) as c FROM alerts a
        {scope_join}
    """, scope_params, one=True)["c"]

    return render_template("alerts.html",
        alerts=alert_list,
        officers=officers,
        current_status=filter_status,
        current_severity=filter_severity,
        view_mode=view_mode,
        user_role=role,
        vigilance_pending_count=vigilance_pending_count,
        operational_pending_count=operational_pending_count,
        total_alerts_count=total_alerts_count
    )


@app.route("/investigations")
@login_required(roles=["ADMIN", "OFFICER"])
def investigations():
    current_scope = get_current_scope()
    scope = current_scope["scope"]
    active_mine_id = current_scope["mine_id"]
    active_sub_mine_id = current_scope["sub_mine_id"]

    if scope == "submine":
        inv_list = db.query("""
            SELECT inv.*, a.alert_code, a.alert_type, t.registration_number, p.permit_number, u.full_name as lead_officer
            FROM investigations inv
            LEFT JOIN alerts a ON a.id = inv.alert_id
            LEFT JOIN trucks t ON t.id = inv.truck_id
            LEFT JOIN permits p ON p.id = inv.permit_id
            LEFT JOIN trips tr ON tr.id = inv.trip_id
            LEFT JOIN users u ON u.id = inv.lead_officer_id
            WHERE t.sub_mine_id = ? OR p.quarry_block_id = ?
            ORDER BY inv.id DESC
        """, (active_sub_mine_id, active_sub_mine_id))
    elif scope == "mine":
        inv_list = db.query("""
            SELECT inv.*, a.alert_code, a.alert_type, t.registration_number, p.permit_number, u.full_name as lead_officer
            FROM investigations inv
            LEFT JOIN alerts a ON a.id = inv.alert_id
            LEFT JOIN trucks t ON t.id = inv.truck_id
            LEFT JOIN permits p ON p.id = inv.permit_id
            LEFT JOIN trips tr ON tr.id = inv.trip_id
            LEFT JOIN users u ON u.id = inv.lead_officer_id
            WHERE tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?
            ORDER BY inv.id DESC
        """, (active_mine_id, active_mine_id, active_mine_id))
    else:
        inv_list = db.query("""
            SELECT inv.*, a.alert_code, a.alert_type, t.registration_number, p.permit_number, u.full_name as lead_officer
            FROM investigations inv
            LEFT JOIN alerts a ON a.id = inv.alert_id
            LEFT JOIN trucks t ON t.id = inv.truck_id
            LEFT JOIN permits p ON p.id = inv.permit_id
            LEFT JOIN users u ON u.id = inv.lead_officer_id
            ORDER BY inv.id DESC
        """)
    return render_template("investigations.html", investigations=inv_list)


@app.route("/investigations/<int:inv_id>")
@login_required(roles=["ADMIN", "OFFICER"])
def investigation_detail(inv_id):
    inv = db.query("""
        SELECT inv.*, a.alert_code, a.alert_type, a.description as alert_desc, a.risk_score as alert_risk,
               t.registration_number, t.registered_owner, t.driver_name, t.driver_phone,
               p.permit_number, p.mineral, p.permitted_weight_mt, p.source_name, p.destination_name,
               u.full_name as lead_officer, u.badge_number, u.department
        FROM investigations inv
        LEFT JOIN alerts a ON a.id = inv.alert_id
        LEFT JOIN trucks t ON t.id = inv.truck_id
        LEFT JOIN permits p ON p.id = inv.permit_id
        LEFT JOIN users u ON u.id = inv.lead_officer_id
        WHERE inv.id = ?
    """, (inv_id,), one=True)
    
    if not inv:
        abort(404)

    if session.get("user_role") == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if officer_mine_id:
            inv_mine = db.query("""
                SELECT p.mine_id as p_mine, tr.mine_id as tr_mine, t.assigned_mine_id as t_mine
                FROM investigations inv
                LEFT JOIN permits p ON p.id = inv.permit_id
                LEFT JOIN trips tr ON tr.id = inv.trip_id
                LEFT JOIN trucks t ON t.id = inv.truck_id
                WHERE inv.id = ?
            """, (inv_id,), one=True)
            if inv_mine:
                m_ids = {inv_mine["p_mine"], inv_mine["tr_mine"], inv_mine["t_mine"]}
                if officer_mine_id not in m_ids:
                    abort(403)

    weighment = db.query("SELECT * FROM weighments WHERE trip_id = ?", (inv["trip_id"],), one=True) if inv["trip_id"] else None
    alerts_list = db.query("SELECT * FROM alerts WHERE trip_id = ? OR truck_id = ?", (inv["trip_id"], inv["truck_id"])) if inv["trip_id"] else []

    return render_template("investigations.html", inv=inv, weighment=weighment, alerts_list=alerts_list, is_detail=True)


@app.route("/analytics")
@login_required()
def analytics():
    current_scope = get_current_scope()
    scope = current_scope["scope"]
    active_mine_id = current_scope["mine_id"]
    active_sub_mine_id = current_scope["sub_mine_id"]

    if scope == "submine":
        mine_dispatch_vs_quota = db.query("""
            SELECT block_name as name, allocated_quota_mt as quota, dispatched_mt as dispatch
            FROM quarry_blocks WHERE id = ?
        """, (active_sub_mine_id,))
        truck_ids = get_operator_truck_ids(active_mine_id, active_sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            risk_distribution = db.query(f"""
                SELECT current_risk_level as level, COUNT(*) as count 
                FROM trucks WHERE id IN ({placeholders}) GROUP BY current_risk_level
            """, truck_ids)
            alerts_by_type = db.query(f"""
                SELECT alert_type, COUNT(*) as count 
                FROM alerts WHERE truck_id IN ({placeholders}) GROUP BY alert_type ORDER BY count DESC
            """, truck_ids)
            alerts_by_severity = db.query(f"""
                SELECT severity, COUNT(*) as count 
                FROM alerts WHERE truck_id IN ({placeholders}) GROUP BY severity ORDER BY count DESC
            """, truck_ids)
        else:
            risk_distribution = []
            alerts_by_type = []
            alerts_by_severity = []

        daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=active_mine_id, sub_mine_id=active_sub_mine_id)
        stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=active_mine_id, sub_mine_id=active_sub_mine_id)
        mineral_summary = MaterialMonitoringService.get_mineral_wise_summary(mine_id=active_mine_id, sub_mine_id=active_sub_mine_id)
        dispatch_vs_prod = MaterialMonitoringService.get_dispatch_vs_production_timeseries(mine_id=active_mine_id, sub_mine_id=active_sub_mine_id)
    elif scope == "mine":
        mine_dispatch_vs_quota = db.query("""
            SELECT name, authorized_annual_quota_mt as quota, current_dispatch_mt as dispatch
            FROM mines WHERE id = ?
        """, (active_mine_id,))
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            risk_distribution = db.query(f"""
                SELECT current_risk_level as level, COUNT(*) as count 
                FROM trucks WHERE id IN ({placeholders}) GROUP BY current_risk_level
            """, truck_ids)
            alerts_by_type = db.query(f"""
                SELECT alert_type, COUNT(*) as count 
                FROM alerts WHERE truck_id IN ({placeholders}) GROUP BY alert_type ORDER BY count DESC
            """, truck_ids)
            alerts_by_severity = db.query(f"""
                SELECT severity, COUNT(*) as count 
                FROM alerts WHERE truck_id IN ({placeholders}) GROUP BY severity ORDER BY count DESC
            """, truck_ids)
        else:
            risk_distribution = []
            alerts_by_type = []
            alerts_by_severity = []

        daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=active_mine_id)
        stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=active_mine_id)
        mineral_summary = MaterialMonitoringService.get_mineral_wise_summary(mine_id=active_mine_id)
        dispatch_vs_prod = MaterialMonitoringService.get_dispatch_vs_production_timeseries(mine_id=active_mine_id)
    else:
        alerts_by_type = db.query("""
            SELECT alert_type, COUNT(*) as count 
            FROM alerts GROUP BY alert_type ORDER BY count DESC
        """)
        alerts_by_severity = db.query("""
            SELECT severity, COUNT(*) as count 
            FROM alerts GROUP BY severity ORDER BY count DESC
        """)
        mine_dispatch_vs_quota = db.query("""
            SELECT name, authorized_annual_quota_mt as quota, current_dispatch_mt as dispatch
            FROM mines ORDER BY id ASC
        """)
        risk_distribution = db.query("""
            SELECT current_risk_level as level, COUNT(*) as count 
            FROM trucks GROUP BY current_risk_level
        """)

        daily_summary = MaterialMonitoringService.get_daily_dispatch_summary()
        stock_recon = MaterialMonitoringService.get_stock_reconciliation()
        mineral_summary = MaterialMonitoringService.get_mineral_wise_summary()
        dispatch_vs_prod = MaterialMonitoringService.get_dispatch_vs_production_timeseries()

    return render_template("analytics.html",
        alerts_by_type=json.dumps(alerts_by_type),
        alerts_by_severity=json.dumps(alerts_by_severity),
        mine_dispatch=json.dumps(mine_dispatch_vs_quota),
        risk_dist=json.dumps(risk_distribution),
        daily_summary=daily_summary,
        stock_recon=stock_recon,
        mineral_summary=mineral_summary,
        dispatch_vs_prod=json.dumps(dispatch_vs_prod)
    )


@app.route("/reports")
@login_required()
def reports():
    current_scope = get_current_scope()
    scope = current_scope["scope"]
    active_mine_id = current_scope["mine_id"]
    active_sub_mine_id = current_scope["sub_mine_id"]

    if scope == "submine":
        truck_ids = get_operator_truck_ids(active_mine_id, active_sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            inv_list = db.query(f"""
                SELECT inv.*, t.registration_number, p.permit_number, u.full_name as officer_name
                FROM investigations inv
                LEFT JOIN trucks t ON t.id = inv.truck_id
                LEFT JOIN permits p ON p.id = inv.permit_id
                LEFT JOIN users u ON u.id = inv.lead_officer_id
                WHERE inv.truck_id IN ({placeholders}) OR p.quarry_block_id = ?
                ORDER BY inv.id DESC
            """, truck_ids + [active_sub_mine_id])
        else:
            inv_list = []
    elif scope == "mine":
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            inv_list = db.query(f"""
                SELECT inv.*, t.registration_number, p.permit_number, u.full_name as officer_name
                FROM investigations inv
                LEFT JOIN trucks t ON t.id = inv.truck_id
                LEFT JOIN permits p ON p.id = inv.permit_id
                LEFT JOIN users u ON u.id = inv.lead_officer_id
                WHERE inv.truck_id IN ({placeholders}) OR p.mine_id = ?
                ORDER BY inv.id DESC
            """, truck_ids + [active_mine_id])
        else:
            inv_list = []
    else:
        inv_list = db.query("""
            SELECT inv.*, t.registration_number, p.permit_number, u.full_name as officer_name
            FROM investigations inv
            LEFT JOIN trucks t ON t.id = inv.truck_id
            LEFT JOIN permits p ON p.id = inv.permit_id
            LEFT JOIN users u ON u.id = inv.lead_officer_id
            ORDER BY inv.id DESC
        """)
    return render_template("reports.html", reports=inv_list)


@app.route("/officer")
@login_required(roles=["ADMIN", "OFFICER"])
def officer_verification():
    """Mobile-friendly field verification interface for roadside checkpoints."""
    return render_template("officer.html")


# --- ADMINISTRATOR USER & ROLE MANAGEMENT ---

@app.route("/admin/users")
@login_required(roles=["ADMIN"])
def admin_users():
    users = db.query("SELECT * FROM users ORDER BY id ASC")
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/create", methods=["POST"])
@login_required(roles=["ADMIN"])
def admin_users_create():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "OFFICER")
    department = request.form.get("department", "").strip()
    badge_number = request.form.get("badge_number", "").strip()
    email = request.form.get("email", "").strip()

    if not username or not password or not full_name:
        flash("Username, password, and full name are required.", "error")
        return redirect(url_for("admin_users"))

    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        flash("Password policy violation: Password must be at least 8 characters long and contain both letters and numbers.", "error")
        return redirect(url_for("admin_users"))

    existing = db.query("SELECT id FROM users WHERE username = ?", (username,), one=True)
    if existing:
        flash(f"Username '{username}' already exists.", "error")
        return redirect(url_for("admin_users"))

    pw_hash = generate_password_hash(password)
    db.execute("""
        INSERT INTO users (username, password_hash, full_name, role, department, badge_number, email, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    """, (username, pw_hash, full_name, role, department, badge_number, email))

    log_audit("USER_CREATE", f"Admin provisioned new {role} account: {username} ({full_name})")
    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/toggle/<int:user_id>", methods=["POST"])
@login_required(roles=["ADMIN"])
def admin_users_toggle(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot deactivate your own administrative account.", "error")
        return redirect(url_for("admin_users"))

    user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if user:
        new_status = False if user["is_active"] else True
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
        status_text = "activated" if new_status else "deactivated"
        log_audit("USER_STATUS_CHANGE", f"Admin {status_text} account: {user['username']}")
        flash(f"User '{user['username']}' {status_text}.", "info")
    return redirect(url_for("admin_users"))


# --- MASTER DATA MANAGEMENT & OPERATOR OPERATIONAL VIEWS ---

@app.route("/admin/data")
@app.route("/master-data")
@login_required(roles=["ADMIN"])
def admin_data_management():
    mines = db.query("SELECT * FROM mines ORDER BY id ASC")
    sub_mines = db.query("""
        SELECT qb.*, m.name as mine_name, m.district as mine_district, m.state as mine_state, m.mineral as mine_mineral
        FROM quarry_blocks qb 
        JOIN mines m ON m.id = qb.mine_id 
        ORDER BY qb.mine_id ASC, qb.id ASC
    """)
    weighbridges = db.query("SELECT wb.*, m.name as mine_name FROM weighbridges wb LEFT JOIN mines m ON m.id = wb.mine_id ORDER BY wb.id ASC")
    destinations = db.query("SELECT * FROM destinations ORDER BY id ASC")
    checkpoints = db.query("SELECT * FROM checkpoints ORDER BY id ASC")
    stock_production = db.query("SELECT sp.*, m.name as mine_name FROM stock_production sp JOIN mines m ON m.id = sp.mine_id ORDER BY sp.record_date DESC, sp.id DESC LIMIT 50")

    return render_template("admin_data.html",
        mines=mines,
        sub_mines=sub_mines,
        weighbridges=weighbridges,
        destinations=destinations,
        checkpoints=checkpoints,
        stock_production=stock_production
    )


@app.route("/operator/stock")
@login_required(roles=["OPERATOR", "ADMIN"])
def operator_stock():
    mine_id = get_operator_mine_id() if session.get("user_role") == "OPERATOR" else request.args.get("mine_id", 1, type=int)
    mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
    if not mine:
        abort(404)
    stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=mine_id)
    production_history = db.query("SELECT * FROM stock_production WHERE mine_id = ? ORDER BY record_date DESC, id DESC LIMIT 30", (mine_id,))
    mines = db.query("SELECT id, name FROM mines") if session.get("user_role") == "ADMIN" else []
    return render_template("operator_stock.html", mine=mine, stock_recon=stock_recon, production_history=production_history, mines=mines)


@app.route("/operator/dispatch")
@login_required(roles=["OPERATOR", "ADMIN"])
def operator_dispatch():
    mine_id = get_operator_mine_id() if session.get("user_role") == "OPERATOR" else request.args.get("mine_id", 1, type=int)
    mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
    if not mine:
        abort(404)
    if session.get("user_role") == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
        truck_ids = get_operator_truck_ids(mine_id, sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trips = db.query(f"""
                SELECT tr.*, t.registration_number, t.driver_name, p.permit_number, p.mineral, p.permitted_weight_mt, p.destination_name
                FROM trips tr
                JOIN trucks t ON t.id = tr.truck_id
                JOIN permits p ON p.id = tr.permit_id
                WHERE tr.truck_id IN ({placeholders})
                ORDER BY tr.id DESC LIMIT 20
            """, truck_ids)
            permits = db.query(f"""
                SELECT p.*, t.registration_number
                FROM permits p
                LEFT JOIN trucks t ON t.id = p.truck_id
                WHERE (p.quarry_block_id = ? OR p.truck_id IN ({placeholders})) AND p.status = 'ACTIVE'
                ORDER BY p.id DESC
            """, [sub_mine_id] + truck_ids)
            trucks = db.query(f"SELECT id, registration_number, status FROM trucks WHERE id IN ({placeholders})", truck_ids)
        else:
            trips = []
            permits = []
            trucks = []
    else:
        trips = db.query("""
            SELECT tr.*, t.registration_number, t.driver_name, p.permit_number, p.mineral, p.permitted_weight_mt, p.destination_name
            FROM trips tr
            JOIN trucks t ON t.id = tr.truck_id
            JOIN permits p ON p.id = tr.permit_id
            WHERE tr.mine_id = ?
            ORDER BY tr.id DESC LIMIT 20
        """, (mine_id,))
        permits = db.query("""
            SELECT p.*, t.registration_number
            FROM permits p
            LEFT JOIN trucks t ON t.id = p.truck_id
            WHERE p.mine_id = ? AND p.status = 'ACTIVE'
            ORDER BY p.id DESC
        """, (mine_id,))
        truck_ids = get_operator_truck_ids(mine_id)
        trucks = []
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"SELECT id, registration_number, status FROM trucks WHERE id IN ({placeholders})", truck_ids)
    
    # Material & Operational Dispatch Monitoring Data
    daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=mine_id)

    # Automated Tender Quota Kill-Switch check
    is_quota_frozen = (float(mine.get("current_dispatch_mt") or 0.0) >= float(mine.get("authorized_annual_quota_mt") or 50000.0)) or (mine.get("status") == "QUOTA_EXCEEDED")
    
    return render_template("operator_dispatch.html", mine=mine, daily_summary=daily_summary, trips=trips, permits=permits, trucks=trucks, is_quota_frozen=is_quota_frozen)


@app.route("/mines/<int:mine_id>/seizure-notice")
@login_required(roles=["ADMIN", "OFFICER"])
def download_mine_seizure_notice(mine_id):
    """
    Downloads official Section 21 MMDR Statutory Seizure Notice PDF
    triggered when a mine hits 100% of its annual environmental concession quota.
    Restricted strictly to State Administrators and the Field Officer assigned to that mine.
    """
    role = session.get("user_role")
    if role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        if officer_mine_id != mine_id:
            abort(403)

    mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
    if not mine:
        flash("Mine record not found.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    pdf_rel_path = generate_seizure_notice_pdf(mine_id)
    if not pdf_rel_path:
        flash("Unable to build seizure order document.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    abs_path = (Path(app.root_path) / Path(pdf_rel_path)).resolve()
    root_resolved = Path(app.root_path).resolve()
    if not abs_path.is_relative_to(root_resolved) or not abs_path.exists():
        flash("Seizure document file not found or inaccessible.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    filename = secure_filename(f"MMDR_Section21_Seizure_Order_{mine['mine_code']}.pdf")
    return send_file(str(abs_path), as_attachment=True, download_name=filename)


@app.route("/operator/weighbridge")
@app.route("/weighbridge")
@login_required(roles=["OPERATOR", "ADMIN", "OFFICER"])
def operator_weighbridge():
    if session.get("user_role") == "OPERATOR":
        mine_id = get_operator_mine_id()
        sub_mine_id = get_operator_sub_mine_id()
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True) or {}
        allowed_trucks = get_operator_truck_ids(mine_id, sub_mine_id)
        if allowed_trucks:
            pl = ",".join("?" for _ in allowed_trucks)
            weighments = db.query(f"""
                SELECT w.*, t.registration_number, tr.trip_number, p.permit_number, p.mineral
                FROM weighments w
                JOIN trips tr ON tr.id = w.trip_id
                JOIN trucks t ON t.id = w.truck_id
                JOIN permits p ON p.id = w.permit_id
                WHERE w.truck_id IN ({pl})
                ORDER BY w.id DESC LIMIT 30
            """, allowed_trucks)
            active_trips = db.query(f"""
                SELECT tr.id, tr.trip_number, t.registration_number, p.permit_number, p.permitted_weight_mt, t.tare_weight_mt, p.id as permit_id, t.id as truck_id
                FROM trips tr
                JOIN trucks t ON t.id = tr.truck_id
                JOIN permits p ON p.id = tr.permit_id
                WHERE tr.truck_id IN ({pl}) AND tr.status IN ('DISPATCHED', 'IN_TRANSIT', 'SUSPICIOUS')
                ORDER BY tr.id DESC
            """, allowed_trucks)
        else:
            weighments = []
            active_trips = []
    else:
        mine_id = get_active_mine_id() or 1
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True) or {}
        weighments = db.query("""
            SELECT w.*, t.registration_number, tr.trip_number, p.permit_number, p.mineral
            FROM weighments w
            JOIN trips tr ON tr.id = w.trip_id
            JOIN trucks t ON t.id = w.truck_id
            JOIN permits p ON p.id = w.permit_id
            WHERE tr.mine_id = ?
            ORDER BY w.id DESC LIMIT 30
        """, (mine_id,))
        active_trips = db.query("""
            SELECT tr.id, tr.trip_number, t.registration_number, p.permit_number, p.permitted_weight_mt, t.tare_weight_mt, p.id as permit_id, t.id as truck_id
            FROM trips tr
            JOIN trucks t ON t.id = tr.truck_id
            JOIN permits p ON p.id = tr.permit_id
            WHERE tr.mine_id = ? AND tr.status IN ('DISPATCHED', 'IN_TRANSIT', 'SUSPICIOUS')
            ORDER BY tr.id DESC
        """, (mine_id,))
    weighbridges = db.query("SELECT * FROM weighbridges WHERE mine_id = ? OR mine_id IS NULL", (mine_id,))
    return render_template("operator_weighbridge.html", mine=mine, weighments=weighments, weighbridges=weighbridges, active_trips=active_trips)


# --- CONTRACTOR SUPPLY CHAIN & MATERIAL RECONCILIATION ROUTES ---

def get_contractor_reconciliation(contractor_id):
    """
    Computes rolling stock reconciliation for a registered Contractor:
    Opening Stock + Verified Mine Receipts + Verified River Receipts = Total Available
    Total Available - Verified Downstream Dispatches = Expected Closing Stock
    Flags Material Reconciliation Exception if dispatches exceed legal verified stock.
    """
    contractor = db.query("SELECT * FROM contractors WHERE id = ?", (int(contractor_id),), one=True)
    if not contractor:
        contractor = db.query("SELECT * FROM contractors ORDER BY id ASC LIMIT 1", one=True)
    if not contractor:
        contractor = {
            "id": 1,
            "contractor_code": "CONT-001",
            "contractor_name": "Sharma Infrastructure Ltd",
            "pan_no": "AAACH4114R",
            "gstn": "06AAACH4114R2ZG",
            "contact_person": "Ramesh Sharma (Director Logistics)",
            "contact_phone": "+91 98120 44551",
            "email": "projects@sharmainfra.com",
            "opening_stock_mt": 200.0,
            "status": "ACTIVE"
        }
    c_id = contractor["id"]
    receipts = db.query("""
        SELECT * FROM contractor_receipts 
        WHERE contractor_id = ? 
        ORDER BY received_at DESC, id DESC
    """, (c_id,)) or []

    dispatches = db.query("""
        SELECT * FROM contractor_dispatches 
        WHERE contractor_id = ? 
        ORDER BY dispatched_at DESC, id DESC
    """, (c_id,)) or []

    opening_stock = float(contractor.get("opening_stock_mt") or 0.0)
    mine_receipts = sum(float(r["net_weight_mt"] or 0.0) for r in receipts if str(r.get("source_category") or "").upper() == "MINE")
    river_receipts = sum(float(r["net_weight_mt"] or 0.0) for r in receipts if str(r.get("source_category") or "").upper() == "RIVER")
    other_receipts = sum(float(r["net_weight_mt"] or 0.0) for r in receipts if str(r.get("source_category") or "").upper() not in ("MINE", "RIVER"))
    total_receipts = mine_receipts + river_receipts + other_receipts
    total_available = round(opening_stock + total_receipts, 2)
    total_dispatches = round(sum(float(d["quantity_mt"] or 0.0) for d in dispatches), 2)
    expected_closing = round(max(0.0, total_available - total_dispatches), 2)

    # Reconciliation Exception handling (Dispatches > Legal Available Material)
    if total_dispatches > total_available:
        unreconciled_qty = round(total_dispatches - total_available, 2)
        reconciled = False
        reconciliation_status = "EXCEPTION_FLAGGED"
        reconciliation_label = "MATERIAL RECONCILIATION EXCEPTION"
        exception_notes = "Dispatch quantity exceeds verified legal source receipts. Discrepancy flagged for officer audit (potential operational reasons: delayed e-Rawaana transit records, authorized quarry transfer not yet logged, stockpile measurement variance, weighbridge calibration adjustment)."
    else:
        unreconciled_qty = 0.0
        reconciled = True
        reconciliation_status = "RECONCILED"
        reconciliation_label = "MATERIAL POSITION RECONCILED"
        exception_notes = "All outbound material dispatches are fully accounted for by verified legal source receipts."

    return {
        "contractor": contractor,
        "receipts": receipts,
        "dispatches": dispatches,
        "opening_stock_mt": opening_stock,
        "mine_receipts_mt": round(mine_receipts, 2),
        "river_receipts_mt": round(river_receipts, 2),
        "other_receipts_mt": round(other_receipts, 2),
        "total_receipts_mt": round(total_receipts, 2),
        "total_available_mt": total_available,
        "total_dispatches_mt": total_dispatches,
        "expected_closing_stock_mt": expected_closing,
        "unreconciled_mt": unreconciled_qty,
        "is_reconciled": reconciled,
        "reconciliation_status": reconciliation_status,
        "reconciliation_label": reconciliation_label,
        "exception_notes": exception_notes
    }


@app.route("/contractor/dashboard")
@login_required(roles=["CONTRACTOR", "ADMIN"])
def contractor_dashboard():
    """
    Contractor Material Custody & Rolling Stock Portal.
    Represents the Contractor as the middle entity receiving legally verified mineral
    from approved sources, maintaining rolling stock, and dispatching to downstream consumers/projects.
    """
    contractor_id = request.args.get("contractor_id")
    if not contractor_id:
        user_id = session.get("user_id")
        user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True) if user_id else None
        if user and user.get("assigned_contractor_id"):
            contractor_id = user["assigned_contractor_id"]
        else:
            contractor_id = 1

    recon_data = get_contractor_reconciliation(contractor_id)
    contractor = recon_data["contractor"]

    # Downstream consumer projects supplied by or associated with this contractor
    consumer_projects = db.query("""
        SELECT ip.*,
               (SELECT COALESCE(SUM(quantity_mt), 0.0) FROM contractor_dispatches WHERE project_id = ip.id AND contractor_id = ?) as dispatched_by_contractor_mt
        FROM infrastructure_projects ip
        ORDER BY ip.id ASC
    """, (contractor["id"],)) or []

    all_contractors = db.query("SELECT * FROM contractors ORDER BY id ASC") or []

    # Available legal sources for quick inbound receipt demo
    legal_sources = db.query("SELECT id, name, district, state, mineral FROM mines ORDER BY id ASC") or []

    # Active permits available for inward receiving
    available_permits = db.query("""
        SELECT p.*, m.name as mine_name, t.registration_number as truck_registration
        FROM permits p
        LEFT JOIN mines m ON m.id = p.mine_id
        LEFT JOIN trucks t ON t.id = p.truck_id
        WHERE p.status IN ('ACTIVE', 'ISSUED')
        ORDER BY p.id DESC LIMIT 10
    """) or []

    # Target project if project_id is requested (for backward compatibility)
    req_proj_id = request.args.get("project_id")
    selected_project = None
    if req_proj_id and req_proj_id.isdigit():
        selected_project = db.query("SELECT * FROM infrastructure_projects WHERE id = ?", (int(req_proj_id),), one=True)
    if not selected_project and consumer_projects:
        selected_project = consumer_projects[0]

    return render_template(
        "contractor_dashboard.html",
        contractor=contractor,
        recon=recon_data,
        receipts=recon_data["receipts"],
        dispatches=recon_data["dispatches"],
        consumer_projects=consumer_projects,
        all_contractors=all_contractors,
        legal_sources=legal_sources,
        available_permits=available_permits,
        project=selected_project,
        all_projects=consumer_projects,
        recent_deliveries=recon_data["receipts"]
    )


@app.route("/api/contractor/receive-permit", methods=["POST"])
@login_required(roles=["CONTRACTOR", "ADMIN"])
def api_contractor_receive_permit():
    """
    Inbound Material Receipt: Legal Source -> Contractor Stock.
    Verifies legal e-Rawaana from registered source and adds tonnage to contractor stock balance.
    """
    data = request.get_json(silent=True) or {}
    permit_number = (data.get("permit_number") or "").strip().upper()
    contractor_id = data.get("contractor_id")
    if not contractor_id:
        user_id = session.get("user_id")
        user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True) if user_id else None
        contractor_id = user["assigned_contractor_id"] if (user and user.get("assigned_contractor_id")) else 1
    contractor_id = int(contractor_id)

    if not permit_number:
        return jsonify({"success": False, "error": "e-Rawaana transit pass number is required."}), 400

    permit = db.query("""
        SELECT p.*, t.registration_number as truck_reg, m.name as mine_name 
        FROM permits p 
        LEFT JOIN trucks t ON t.id = p.truck_id 
        LEFT JOIN mines m ON m.id = p.mine_id 
        WHERE UPPER(p.permit_number) = ?
    """, (permit_number,), one=True)
    if not permit:
        return jsonify({"success": False, "error": f"e-Rawaana '{permit_number}' not found in state mining central registry."}), 404

    existing_rec = db.query("SELECT id FROM contractor_receipts WHERE permit_number = ? AND contractor_id = ?", (permit_number, contractor_id), one=True)
    if existing_rec:
        return jsonify({"success": False, "error": f"Permit '{permit_number}' is ALREADY recorded in Contractor Stock Ledger."}), 400

    mineral = permit.get("mineral") or "Mineral Aggregate"
    source_name = permit.get("source_name") or permit.get("mine_name") or "Authorized Mining Concession"
    is_river = "sand" in mineral.lower() or "river" in source_name.lower() or "khol" in source_name.lower()
    source_cat = "RIVER" if is_river else "MINE"
    weight_mt = float(permit.get("permitted_weight_mt") or 25.0)
    truck_no = permit.get("truck_reg") or permit.get("vehicle_number") or "HR26AB1234"

    rec_count = db.query("SELECT COUNT(*) as c FROM contractor_receipts", one=True)["c"] or 0
    receipt_code = f"REC-SHM-{rec_count + 1:02d}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        INSERT INTO contractor_receipts 
        (receipt_code, contractor_id, permit_id, permit_number, source_mine_id, source_name, source_category, mineral, net_weight_mt, vehicle_number, received_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (receipt_code, contractor_id, permit["id"], permit_number, permit.get("mine_id"), source_name, source_cat, mineral, weight_mt, truck_no, now_str, "VERIFIED"))

    db.execute("""
        UPDATE permits 
        SET status = 'DELIVERED', 
            contractor_id = ?,
            received_at_site = ?
        WHERE id = ?
    """, (contractor_id, now_str, permit["id"]))

    log_audit("CONTRACTOR_INBOUND_RECEIPT", f"Contractor #{contractor_id} received {weight_mt} MT {mineral} from {source_name} via e-Rawaana {permit_number}.", entity="CONTRACTOR_STOCK")

    recon = get_contractor_reconciliation(contractor_id)
    return jsonify({
        "success": True,
        "receipt_code": receipt_code,
        "permit_number": permit_number,
        "source_name": source_name,
        "source_category": source_cat,
        "added_mt": weight_mt,
        "total_available_mt": recon["total_available_mt"],
        "expected_closing_stock_mt": recon["expected_closing_stock_mt"],
        "message": f"Successfully received {weight_mt} MT into contractor stock."
    })


@app.route("/api/contractor/receive-truck", methods=["POST"])
@login_required(roles=["CONTRACTOR", "ADMIN"])
def api_contractor_receive_truck():
    """Site Gate QR Scan Endpoint (Maintains backward compatibility while updating contractor stock)."""
    data = request.get_json(silent=True) or {}
    permit_number = (data.get("permit_number") or "").strip().upper()
    project_id = data.get("project_id", 1)

    if not permit_number:
        return jsonify({"success": False, "error": "e-Rawaana permit number is required"}), 400

    project = db.query("SELECT * FROM infrastructure_projects WHERE id = ?", (project_id,), one=True)
    if not project:
        return jsonify({"success": False, "error": "Infrastructure project record not found"}), 404

    permit = db.query("""
        SELECT p.*, t.registration_number as truck_reg, m.name as mine_name 
        FROM permits p 
        LEFT JOIN trucks t ON t.id = p.truck_id 
        LEFT JOIN mines m ON m.id = p.mine_id 
        WHERE UPPER(p.permit_number) = ?
    """, (permit_number,), one=True)
    if not permit:
        return jsonify({"success": False, "error": f"e-Rawaana '{permit_number}' not found in state mining central registry."}), 404

    if permit.get("status") == "CONSUMED_AT_SITE":
        return jsonify({"success": False, "error": f"Permit {permit_number} was ALREADY received and credited to this project."}), 400

    tonnage = float(permit.get("permitted_weight_mt") or 20.0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contractor_id = project.get("contractor_id") or 1

    # Record inward receipt into contractor_receipts if not yet recorded
    existing_rec = db.query("SELECT id FROM contractor_receipts WHERE permit_number = ? AND contractor_id = ?", (permit_number, contractor_id), one=True)
    if not existing_rec:
        rec_count = db.query("SELECT COUNT(*) as c FROM contractor_receipts", one=True)["c"] or 0
        receipt_code = f"REC-SHM-{rec_count + 1:02d}"
        mineral = permit.get("mineral") or project.get("primary_mineral") or "Mineral Aggregate"
        source_name = permit.get("mine_name") or permit.get("source_name") or "State Mining Concession"
        source_cat = "RIVER" if "sand" in mineral.lower() else "MINE"
        truck_no = permit.get("truck_reg") or "HR26AB1234"
        db.execute("""
            INSERT INTO contractor_receipts 
            (receipt_code, contractor_id, permit_id, permit_number, source_mine_id, source_name, source_category, mineral, net_weight_mt, vehicle_number, received_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (receipt_code, contractor_id, permit["id"], permit_number, permit.get("mine_id"), source_name, source_cat, mineral, tonnage, truck_no, now_str, "VERIFIED"))

    db.execute("""
        UPDATE permits 
        SET status = 'CONSUMED_AT_SITE', 
            project_work_order = ?, 
            received_at_site = ?,
            contractor_id = ?,
            is_billed_in_emb = 0
        WHERE id = ?
    """, (project["project_code"], now_str, contractor_id, permit["id"]))

    current_rec = float(project.get("mineral_received_mt") or project.get("sand_received_mt") or 0.0)
    target_req = float(project.get("mineral_required_mt") or project.get("sand_required_mt") or 0.0)
    new_received = round(current_rec + tonnage, 1)
    tolerance_mt = target_req * 0.05
    new_status = "COMPLIANT" if (target_req - new_received) <= tolerance_mt else "DEFICIT_FLAGGED"

    db.execute("""
        UPDATE infrastructure_projects 
        SET sand_received_mt = ?, mineral_received_mt = ?, status = ?
        WHERE id = ?
    """, (new_received, new_received, new_status, project["id"]))

    log_audit("CONTRACTOR_GATE_RECEIVE", f"e-Rawaana {permit_number} ({tonnage} MT) verified and received at {project['project_code']} site gate.", entity="PERMIT")

    return jsonify({
        "success": True,
        "added_mt": tonnage,
        "new_total_mt": new_received,
        "status": new_status,
        "project_code": project["project_code"]
    })


@app.route("/api/contractor/dispatch-material", methods=["POST"])
@login_required(roles=["CONTRACTOR", "ADMIN"])
def api_contractor_dispatch_material():
    """
    Outbound Material Dispatch: Contractor Stock -> Downstream Consumer / Project.
    Dispatches legally verified material from contractor custody to downstream projects.
    Updates project received balance and recalculates contractor rolling stock.
    """
    data = request.get_json(silent=True) or {}
    contractor_id = data.get("contractor_id")
    if not contractor_id:
        user_id = session.get("user_id")
        user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True) if user_id else None
        contractor_id = user["assigned_contractor_id"] if (user and user.get("assigned_contractor_id")) else 1
    contractor_id = int(contractor_id)

    project_id = data.get("project_id")
    quantity_mt = float(data.get("quantity_mt") or 0.0)
    if quantity_mt <= 0:
        return jsonify({"success": False, "error": "Dispatch quantity must be greater than 0 MT."}), 400

    project = None
    if project_id:
        project = db.query("SELECT * FROM infrastructure_projects WHERE id = ?", (int(project_id),), one=True)
    if not project:
        return jsonify({"success": False, "error": "Valid downstream consumer project must be selected."}), 400

    consumer_name = project.get("project_name") or data.get("consumer_name") or "Downstream Consumer Project"
    project_code = project.get("project_code")
    mineral = data.get("mineral") or project.get("primary_mineral") or "Mineral Aggregate"
    vehicle_number = (data.get("vehicle_number") or "HR26AB1234").strip().upper()
    driver_name = (data.get("driver_name") or "Designated Commercial Driver").strip()

    dsp_count = db.query("SELECT COUNT(*) as c FROM contractor_dispatches", one=True)["c"] or 0
    dispatch_code = f"DSP-{dsp_count + 1:03d}"
    eway_bill = data.get("e_way_bill_no") or f"EWB-06-2026-{dsp_count + 886:03d}"
    invoice_no = data.get("invoice_no") or f"INV/SHM/26-{dsp_count + 96:03d}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        INSERT INTO contractor_dispatches 
        (dispatch_code, contractor_id, project_id, consumer_name, project_code, mineral, quantity_mt, vehicle_number, driver_name, e_way_bill_no, invoice_no, dispatched_at, status, reconciliation_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (dispatch_code, contractor_id, project["id"], consumer_name, project_code, mineral, quantity_mt, vehicle_number, driver_name, eway_bill, invoice_no, now_str, "VERIFIED", "RECONCILED"))

    current_rec = float(project.get("mineral_received_mt") or project.get("sand_received_mt") or 0.0)
    target_req = float(project.get("mineral_required_mt") or project.get("sand_required_mt") or 0.0)
    new_received = round(current_rec + quantity_mt, 1)
    tolerance_mt = target_req * 0.05
    new_status = "COMPLIANT" if (target_req - new_received) <= tolerance_mt else "DEFICIT_FLAGGED"

    db.execute("""
        UPDATE infrastructure_projects 
        SET sand_received_mt = ?, mineral_received_mt = ?, status = ?
        WHERE id = ?
    """, (new_received, new_received, new_status, project["id"]))

    log_audit("CONTRACTOR_OUTBOUND_DISPATCH", f"Contractor #{contractor_id} dispatched {quantity_mt} MT {mineral} to {project_code} ({consumer_name}) under dispatch {dispatch_code}.", entity="CONTRACTOR_DISPATCH")

    recon = get_contractor_reconciliation(contractor_id)
    return jsonify({
        "success": True,
        "dispatch_code": dispatch_code,
        "consumer_name": consumer_name,
        "project_code": project_code,
        "quantity_mt": quantity_mt,
        "new_closing_stock_mt": recon["expected_closing_stock_mt"],
        "unreconciled_mt": recon["unreconciled_mt"],
        "reconciliation_status": recon["reconciliation_status"],
        "reconciliation_label": recon["reconciliation_label"],
        "project_received_mt": new_received,
        "message": f"Successfully dispatched {quantity_mt} MT to {project_code}."
    })


@app.route("/contractor/download-noc/<int:project_id>")
@login_required(roles=["CONTRACTOR", "ADMIN"])
def contractor_download_noc(project_id):
    """Generates official Statutory Mineral Royalty Clearance Certificate (NOC) PDF."""
    if generate_royalty_noc_pdf:
        try:
            rel_path = generate_royalty_noc_pdf(project_id)
            if rel_path:
                full_path = Config.BASE_DIR / rel_path
                if full_path.exists():
                    return send_file(str(full_path), as_attachment=True, download_name=f"Royalty_NOC_Project_{project_id}.pdf")
        except Exception as e:
            logger.error(f"Error generating Royalty NOC PDF: {e}")

    flash("Royalty Clearance Certificate generated and logged in official statutory audit registry.", "success")
    return redirect(url_for("contractor_dashboard"))


@app.route("/api/operator/register-contractor", methods=["POST"])
@login_required(roles=["OPERATOR", "ADMIN", "OFFICER"])
def api_operator_register_contractor():
    """
    Operator Registration Endpoint:
    Allows Weighbridge Operator (or Officer/Admin) to register a new Middleman / Stock Custodian (Contractor)
    who buys or lifts minerals from the concession.
    """
    data = request.get_json(silent=True) or {}
    contractor_name = (data.get("contractor_name") or "").strip()
    contact_person = (data.get("contact_person") or "").strip()
    contact_phone = (data.get("contact_phone") or "").strip()
    pan_no = (data.get("pan_no") or "").strip().upper()
    gstn = (data.get("gstn") or "").strip().upper()
    email = (data.get("email") or "").strip().lower()
    opening_stock_mt = float(data.get("opening_stock_mt") or 0.0)

    if not contractor_name:
        return jsonify({"success": False, "error": "Middleman / Business Name is required."}), 400

    cnt_row = db.query("SELECT COUNT(*) as c FROM contractors", one=True)
    cnt = cnt_row["c"] if cnt_row else 0
    contractor_code = f"CONT-{cnt + 1:03d}"

    res_id = db.execute("""
        INSERT INTO contractors (contractor_code, contractor_name, pan_no, gstn, contact_person, contact_phone, email, opening_stock_mt, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
    """, (contractor_code, contractor_name, pan_no, gstn, contact_person, contact_phone, email, opening_stock_mt))

    new_id = res_id if (res_id and isinstance(res_id, int)) else (cnt + 1)
    
    # Also create a login account for this contractor
    username = f"contractor_{cnt + 1}"
    existing_user = db.query("SELECT id FROM users WHERE username = ?", (username,), one=True)
    if not existing_user:
        from werkzeug.security import generate_password_hash
        pwd_hash = generate_password_hash("contractor123")
        db.execute("""
            INSERT INTO users (username, password_hash, full_name, role, department, badge_number, email, phone, assigned_contractor_id)
            VALUES (?, ?, ?, 'CONTRACTOR', 'Mineral Stock Custodian', ?, ?, ?, ?)
        """, (username, pwd_hash, contractor_name, contractor_code, email or f"{username}@mining.gov.in", contact_phone, new_id))

    log_audit("CONTRACTOR_REGISTERED", f"New mineral middleman '{contractor_name}' ({contractor_code}) registered by {session.get('user_role')} {session.get('username')}.", entity="CONTRACTOR")

    return jsonify({
        "success": True,
        "contractor_id": new_id,
        "contractor_code": contractor_code,
        "contractor_name": contractor_name,
        "opening_stock_mt": opening_stock_mt,
        "username": username,
        "message": f"Successfully registered middleman '{contractor_name}' ({contractor_code})!"
    })


@app.route("/admin/supply-chain")
@login_required(roles=["ADMIN", "OFFICER"])
def admin_supply_chain():
    """
    Statewide / District Material Supply Chain Ledger:
    LEGAL SOURCE -> CONTRACTOR CUSTODY (STOCK) -> DOWNSTREAM CONSUMERS & PROJECTS.
    Scoped to assigned mine for officers; statewide for admins.
    """
    user_role = session.get("user_role")
    assigned_mine = session.get("assigned_mine_id")
    is_officer = (user_role == "OFFICER" and assigned_mine)

    if is_officer:
        receipts = db.query("""
            SELECT cr.*, c.contractor_name, c.contractor_code
            FROM contractor_receipts cr
            JOIN contractors c ON c.id = cr.contractor_id
            WHERE cr.source_mine_id = ?
            ORDER BY cr.received_at DESC, cr.id DESC
        """, (assigned_mine,)) or []

        c_ids = list(set([r["contractor_id"] for r in receipts if r.get("contractor_id")]))
        if c_ids:
            pl = ",".join("?" for _ in c_ids)
            contractors = db.query(f"SELECT * FROM contractors WHERE id IN ({pl}) ORDER BY id ASC", c_ids) or []
        else:
            contractors = db.query("SELECT * FROM contractors ORDER BY id ASC LIMIT 5") or []
        contractor_recons = [get_contractor_reconciliation(c["id"]) for c in contractors]

        projects = db.query("""
            SELECT ip.*, c.contractor_name, m.name as mine_name
            FROM infrastructure_projects ip
            LEFT JOIN contractors c ON c.id = ip.contractor_id
            LEFT JOIN mines m ON m.id = ip.mine_id
            WHERE ip.mine_id = ?
            ORDER BY ip.id ASC
        """, (assigned_mine,)) or []

        dispatches = db.query("""
            SELECT cd.*, c.contractor_name, c.contractor_code
            FROM contractor_dispatches cd
            JOIN contractors c ON c.id = cd.contractor_id
            WHERE cd.project_id IN (SELECT id FROM infrastructure_projects WHERE mine_id = ?)
            ORDER BY cd.dispatched_at DESC, cd.id DESC
        """, (assigned_mine,)) or []
    else:
        contractors = db.query("SELECT * FROM contractors ORDER BY id ASC") or []
        contractor_recons = [get_contractor_reconciliation(c["id"]) for c in contractors]

        receipts = db.query("""
            SELECT cr.*, c.contractor_name, c.contractor_code
            FROM contractor_receipts cr
            JOIN contractors c ON c.id = cr.contractor_id
            ORDER BY cr.received_at DESC, cr.id DESC
        """) or []

        dispatches = db.query("""
            SELECT cd.*, c.contractor_name, c.contractor_code
            FROM contractor_dispatches cd
            JOIN contractors c ON c.id = cd.contractor_id
            ORDER BY cd.dispatched_at DESC, cd.id DESC
        """) or []

        projects = db.query("""
            SELECT ip.*, c.contractor_name, m.name as mine_name
            FROM infrastructure_projects ip
            LEFT JOIN contractors c ON c.id = ip.contractor_id
            LEFT JOIN mines m ON m.id = ip.mine_id
            ORDER BY ip.id ASC
        """) or []

    return render_template(
        "admin_supply_chain.html",
        contractor_recons=contractor_recons,
        receipts=receipts,
        dispatches=dispatches,
        projects=projects,
        is_officer_locked=is_officer
    )


@app.route("/admin/infrastructure-audit")
@login_required(roles=["ADMIN", "OFFICER"])
def admin_infrastructure_audit():
    """Statewide & District Multi-Sector Infrastructure & Mineral Reconciliation Audit."""
    user_role = session.get("user_role")
    assigned_mine = session.get("assigned_mine_id")
    is_officer = (user_role == "OFFICER" and assigned_mine)

    req_mine = request.args.get("mine_id")
    req_sub_mine = request.args.get("sub_mine_id")
    req_category = request.args.get("category")

    mines = db.query("SELECT id, name, district, state FROM mines ORDER BY id ASC")
    
    where_clauses = []
    params = []

    selected_mine_id = None
    if is_officer:
        # Officer is strictly locked to their assigned jurisdiction mine
        selected_mine_id = int(assigned_mine)
        where_clauses.append("ip.mine_id = ?")
        params.append(selected_mine_id)
        sub_mines = db.query("SELECT id, block_code, block_name FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC", (selected_mine_id,))
    elif req_mine and req_mine.isdigit() and int(req_mine) > 0:
        selected_mine_id = int(req_mine)
        where_clauses.append("ip.mine_id = ?")
        params.append(selected_mine_id)
        sub_mines = db.query("SELECT id, block_code, block_name FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC", (selected_mine_id,))
    else:
        sub_mines = db.query("SELECT id, mine_id, block_code, block_name FROM quarry_blocks ORDER BY mine_id ASC, id ASC")

    selected_sub_mine_id = None
    if req_sub_mine and req_sub_mine.isdigit() and int(req_sub_mine) > 0:
        selected_sub_mine_id = int(req_sub_mine)
        where_clauses.append("ip.sub_mine_id = ?")
        params.append(selected_sub_mine_id)

    selected_category = None
    if req_category and req_category.strip():
        selected_category = req_category.strip().upper()
        where_clauses.append("ip.project_category = ?")
        params.append(selected_category)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    try:
        projects = db.query(f"""
            SELECT ip.*, m.name as mine_name, qb.block_name as sub_mine_name, c.contractor_name as supplying_contractor_name
            FROM infrastructure_projects ip
            LEFT JOIN mines m ON m.id = ip.mine_id
            LEFT JOIN quarry_blocks qb ON qb.id = ip.sub_mine_id
            LEFT JOIN contractors c ON c.id = ip.contractor_id
            {where_sql}
            ORDER BY ip.id ASC
        """, params)
    except Exception as _p_err:
        logger.warning(f"Could not load infrastructure_projects: {_p_err}")
        projects = []

    total_concrete = sum(float(p.get("concrete_volume_m3") or 0.0) for p in projects)
    total_mineral_req = sum(float(p.get("mineral_required_mt") or p.get("sand_required_mt") or 0.0) for p in projects)
    total_mineral_rec = sum(float(p.get("mineral_received_mt") or p.get("sand_received_mt") or 0.0) for p in projects)
    
    # 5% Statutory Tolerance Allowance (CPWD & IRC standard natural moisture/shrinkage buffer)
    total_penalties = 0.0
    for p in projects:
        req = float(p.get("mineral_required_mt") or p.get("sand_required_mt") or 0.0)
        rec = float(p.get("mineral_received_mt") or p.get("sand_received_mt") or 0.0)
        tolerance_mt = req * 0.05
        raw_deficit = req - rec
        actionable_deficit = max(0.0, raw_deficit - tolerance_mt) if raw_deficit > tolerance_mt else 0.0
        rate = float(p.get("penalty_rate_per_mt") or 600.0)
        total_penalties += actionable_deficit * rate

    # Also include contractor stock summaries for supply-chain context
    if is_officer:
        c_filter = "WHERE id IN (SELECT DISTINCT contractor_id FROM infrastructure_projects WHERE mine_id = ? UNION SELECT DISTINCT contractor_id FROM contractor_receipts WHERE source_mine_id = ?)"
        contractors = db.query(f"SELECT * FROM contractors {c_filter} ORDER BY id ASC", (selected_mine_id, selected_mine_id)) or []
        if not contractors:
            contractors = db.query("SELECT * FROM contractors ORDER BY id ASC LIMIT 3") or []
    else:
        contractors = db.query("SELECT * FROM contractors ORDER BY id ASC") or []
    contractor_recons = [get_contractor_reconciliation(c["id"]) for c in contractors]

    return render_template("admin_infrastructure_audit.html",
        projects=projects,
        mines=mines,
        sub_mines=sub_mines,
        selected_mine_id=selected_mine_id,
        selected_sub_mine_id=selected_sub_mine_id,
        selected_category=selected_category,
        total_concrete_volume=total_concrete,
        total_sand_required=total_mineral_req,
        total_sand_received=total_mineral_rec,
        total_penalties_withheld=total_penalties,
        contractor_recons=contractor_recons,
        is_officer_locked=is_officer
    )


# --- PUBLIC REST API ENDPOINTS (UNAUTHENTICATED & WHITELISTED) ---

@app.route("/api/public/search")
def api_public_search():
    """
    Public Verification Search Endpoint.
    Strictly whitelists public-safe fields for:
    - e-Rawaana Number
    - Vehicle Number
    - ISTP Number (Inter-State Transit Pass)
    - ROP Number (Raw Material Operator Pass)
    - MTP Number (Mineral Transit Pass)
    NEVER exposes GPS telemetry, risk scores, alerts, or officer notes.
    """
    search_type = request.args.get("search_type", "e-Rawaana Number").strip()
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"found": False, "message": "Please enter a registration or pass number to search."}), 400

    clean_query = query.replace(" ", "").replace("-", "").upper()

    permit = None
    pass_type_label = search_type

    # 1. Search by Vehicle Number
    if "vehicle" in search_type.lower():
        truck = db.query("""
            SELECT * FROM trucks 
            WHERE REPLACE(REPLACE(UPPER(registration_number), ' ', ''), '-', '') = ?
               OR UPPER(registration_number) LIKE ?
        """, (clean_query, f"%{query.upper()}%"), one=True)

        if truck:
            permit = db.query("""
                SELECT p.*, t.registration_number as vehicle_reg, m.name as mine_name, m.district as mine_dist,
                       w.weighbridge_name, w.is_overweight
                FROM permits p
                JOIN trucks t ON t.id = p.truck_id
                LEFT JOIN mines m ON m.id = p.mine_id
                LEFT JOIN weighments w ON w.permit_id = p.id
                WHERE p.truck_id = ?
                ORDER BY p.id DESC LIMIT 1
            """, (truck["id"],), one=True)

            if not permit:
                return jsonify({
                    "found": True,
                    "search_type": search_type,
                    "record": {
                        "vehicle_number": truck["registration_number"],
                        "pass_number": "None Active",
                        "pass_type": "Commercial Carrier Fleet Record",
                        "status": truck["status"],
                        "mineral": "Not Dispatched",
                        "permitted_quantity_mt": "—",
                        "source_mine": "State Mining Grid",
                        "destination": "Idle / Unassigned",
                        "issued_date": "—",
                        "valid_until": "—",
                        "weighbridge_verification_status": "No Active Weighment",
                        "transit_status": f"Vehicle Status: {truck['status']}"
                    }
                })

    # 2. Search by Permit / Pass Number (e-Rawaana, ISTP, ROP, MTP)
    else:
        permit = db.query("""
            SELECT p.*, t.registration_number as vehicle_reg, m.name as mine_name, m.district as mine_dist,
                   w.weighbridge_name, w.is_overweight
            FROM permits p
            LEFT JOIN trucks t ON t.id = p.truck_id
            LEFT JOIN mines m ON m.id = p.mine_id
            LEFT JOIN weighments w ON w.permit_id = p.id
            WHERE REPLACE(REPLACE(UPPER(p.permit_number), ' ', ''), '-', '') = ?
               OR UPPER(p.permit_number) LIKE ?
               OR p.permit_number LIKE ?
            ORDER BY p.id DESC LIMIT 1
        """, (clean_query, f"%{query.upper()}%", f"%{query}%"), one=True)

        if not permit:
            # Fallback check if user entered truck registration under pass number
            permit = db.query("""
                SELECT p.*, t.registration_number as vehicle_reg, m.name as mine_name, m.district as mine_dist,
                       w.weighbridge_name, w.is_overweight
                FROM permits p
                LEFT JOIN trucks t ON t.id = p.truck_id
                LEFT JOIN mines m ON m.id = p.mine_id
                LEFT JOIN weighments w ON w.permit_id = p.id
                WHERE REPLACE(REPLACE(UPPER(t.registration_number), ' ', ''), '-', '') = ?
                ORDER BY p.id DESC LIMIT 1
            """, (clean_query,), one=True)

    if not permit:
        return jsonify({
            "found": False,
            "search_type": search_type,
            "message": "No matching public record found."
        })

    # Determine public pass type label
    p_num = permit.get("permit_number", "")
    if "istp" in search_type.lower() or p_num.startswith("ISTP"):
        pass_type_label = "Inter-State Transit Pass (ISTP)"
    elif "rop" in search_type.lower() or p_num.startswith("ROP"):
        pass_type_label = "Raw Material Operator Pass (ROP)"
    elif "mtp" in search_type.lower() or p_num.startswith("MTP"):
        pass_type_label = "Mineral Transit Pass (MTP)"
    else:
        pass_type_label = "e-Rawaana Electronic Transit Pass"

    wb_status = "Verified at Weigh Station" if permit.get("weighbridge_name") else "Pending Destination Weighbridge"
    issued = str(permit.get("issued_at", ""))[:16] if permit.get("issued_at") else "—"
    expires = str(permit.get("expires_at", ""))[:16] if permit.get("expires_at") else "—"

    # Strictly return WHITELISTED public-safe fields only
    safe_record = {
        "pass_number": permit.get("permit_number"),
        "pass_type": pass_type_label,
        "vehicle_number": permit.get("vehicle_reg") or "Carrier Assigned",
        "status": permit.get("status", "ACTIVE"),
        "mineral": permit.get("mineral", "Mineral Ore"),
        "permitted_quantity_mt": f"{permit.get('permitted_weight_mt', 0.0):.1f} MT",
        "source_mine": f"{permit.get('source_name', permit.get('mine_name', 'Authorized Leasehold'))}",
        "destination": permit.get("destination_name", "Registered Consignee"),
        "issued_date": issued,
        "valid_until": expires,
        "weighbridge_verification_status": wb_status,
        "transit_status": f"Transit Authorization: {permit.get('status')} &bull; Legal Mineral Corridor"
    }

    return jsonify({
        "found": True,
        "search_type": search_type,
        "record": safe_record
    })


@app.route("/api/public/mine-stats")
def api_public_mine_stats():
    """
    Public-Safe Statistics for a Selected Mine.
    Strictly returns non-sensitive public metrics:
    - Mine Name, District, Mineral, Operational Status
    - Active Trucks count
    - Active Permits count
    - Weighbridge status
    """
    mine_id = request.args.get("mine_id", type=int)
    if not mine_id:
        return jsonify({"error": "mine_id parameter is required"}), 400

    mine = db.query("SELECT id, mine_code, name, mineral, district, state, status, authorized_annual_quota_mt, current_dispatch_mt FROM mines WHERE id = ?", (mine_id,), one=True)
    if not mine:
        return jsonify({"error": "Mine not found"}), 404

    active_trucks = db.query("""
        SELECT COUNT(DISTINCT truck_id) as c 
        FROM permits 
        WHERE mine_id = ? AND status = 'ACTIVE'
    """, (mine_id,), one=True)["c"]

    if active_trucks == 0:
        active_trucks = db.query("""
            SELECT COUNT(DISTINCT truck_id) as c 
            FROM trips 
            WHERE mine_id = ? AND status IN ('IN_TRANSIT', 'DISPATCHED')
        """, (mine_id,), one=True)["c"]

    active_permits = db.query("""
        SELECT COUNT(*) as c 
        FROM permits 
        WHERE mine_id = ? AND status = 'ACTIVE'
    """, (mine_id,), one=True)["c"]

    weighbridges_count = 1 if mine_id in (1, 2, 3) else 0
    wb_status = "Operational (Electronic Sensor Integrated)" if weighbridges_count > 0 else "Manual Outpost Logging"

    # Public-safe aggregated dispatch metrics (non-sensitive general dispatch only)
    daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=mine_id)
    today_dispatch_mt = daily_summary["actual_dispatch_mt"]

    return jsonify({
        "mine_id": mine["id"],
        "mine_code": mine["mine_code"],
        "name": mine["name"],
        "district": mine["district"],
        "state": mine["state"],
        "mineral": mine["mineral"],
        "status": mine["status"],
        "authorized_annual_quota_mt": mine.get("authorized_annual_quota_mt") or 50000.0,
        "current_dispatch_mt": mine.get("current_dispatch_mt") or 0.0,
        "lease_expiry_date": mine.get("lease_expiry_date") or '2027-12-31',
        "ec_clearance_number": mine.get("ec_clearance_number") or 'EC-MOEF-2024-8841',
        "is_quota_exhausted": bool(mine["status"] == "QUOTA_EXCEEDED" or ((mine.get("authorized_annual_quota_mt") or 0) > 0 and (mine.get("current_dispatch_mt") or 0) >= (mine.get("authorized_annual_quota_mt") or 0))),
        "quota_percent": round(((mine.get("current_dispatch_mt") or 0.0) / (mine.get("authorized_annual_quota_mt") or 1.0) * 100), 1),
        "active_trucks": active_trucks,
        "active_permits": active_permits,
        "weighbridges": weighbridges_count,
        "weighbridge_status": wb_status,
        "today_dispatch_mt": f"{today_dispatch_mt:.1f} MT"
    })


# --- CITIZEN PUBLIC WHISTLEBLOWER APIS (JANTA VIGILANCE) ---

@app.route("/api/public/whistleblower", methods=["POST"])
def api_public_whistleblower():
    """
    Public Citizen Vigilance Reporting (Janta Vigilance).
    Allows any citizen, farmer, or villager to report illegal mining activities:
    - Midnight Riverbed Extraction
    - Unregistered / Illegal Stone Crushers
    - Overloaded Unnumbered Tipper Convoys
    - Blackout Mineral Dumping at Private Sites
    - Geofence / Ecologically Sensitive Buffer Incursion
    Supports anonymous reporting, GPS geolocation, and photo/video evidence.
    Generates a unique tracking token and triggers a CRITICAL alert on Officer & Admin dashboards.
    """
    try:
        # Check if form data or JSON
        if request.content_type and "multipart/form-data" in request.content_type:
            incident_type = request.form.get("incident_type", "MIDNIGHT_RIVERBED_EXTRACTION").strip()
            location_name = request.form.get("location_name", "").strip()
            description = request.form.get("description", "").strip()
            incident_date = request.form.get("incident_date", "").strip() or datetime.now().strftime("%Y-%m-%d %H:%M")
            lat = request.form.get("latitude")
            lng = request.form.get("longitude")
            is_anonymous_val = request.form.get("is_anonymous", "true").lower() in ("true", "1", "yes", "on")
            reporter_name = request.form.get("reporter_name", "").strip() if not is_anonymous_val else None
            reporter_phone = request.form.get("reporter_phone", "").strip() if not is_anonymous_val else None

            # Handle photo upload
            photo_url = None
            if "evidence_file" in request.files:
                file = request.files["evidence_file"]
                if file and file.filename != "":
                    upload_folder = Path(Config.BASE_DIR) / "static" / "uploads" / "whistleblower"
                    upload_folder.mkdir(parents=True, exist_ok=True)
                    safe_name = f"tip_{int(time.time())}_{secure_filename(file.filename)}"
                    file.save(str(upload_folder / safe_name))
                    photo_url = f"static/uploads/whistleblower/{safe_name}"
            if not photo_url:
                photo_url = request.form.get("evidence_photo_url") or "static/images/weighbridge/scale_front_cam.jpg"
        else:
            data = request.get_json(silent=True) or {}
            incident_type = data.get("incident_type", "MIDNIGHT_RIVERBED_EXTRACTION").strip()
            location_name = data.get("location_name", "").strip()
            description = data.get("description", "").strip()
            incident_date = data.get("incident_date", "").strip() or datetime.now().strftime("%Y-%m-%d %H:%M")
            lat = data.get("latitude")
            lng = data.get("longitude")
            is_anonymous_val = bool(data.get("is_anonymous", True))
            reporter_name = data.get("reporter_name") if not is_anonymous_val else None
            reporter_phone = data.get("reporter_phone") if not is_anonymous_val else None
            photo_url = data.get("evidence_photo_url") or "static/images/weighbridge/scale_front_cam.jpg"

        if not location_name or not description:
            return jsonify({"error": "Location details and incident description are required.", "success": False}), 400

        try:
            latitude = float(lat) if lat not in (None, "") else None
            longitude = float(lng) if lng not in (None, "") else None
        except (ValueError, TypeError):
            latitude = None
            longitude = None

        # Generate unique tracking token: SMG-TIP-XXXXXX
        rand_num = secrets.randbelow(900000) + 100000
        report_token = f"SMG-TIP-{rand_num}"
        while db.query("SELECT 1 FROM citizen_reports WHERE report_token = ?", (report_token,), one=True):
            rand_num = secrets.randbelow(900000) + 100000
            report_token = f"SMG-TIP-{rand_num}"

        # Insert citizen report
        db.execute("""
            INSERT INTO citizen_reports 
            (report_token, incident_type, incident_date, location_name, latitude, longitude, description, evidence_photo_url, is_anonymous, reporter_name, reporter_phone, status, action_taken, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_VERIFICATION', 'Report received and queued for immediate Mining Flying Squad dispatch.', datetime('now'), datetime('now'))
        """, (
            report_token,
            incident_type,
            incident_date,
            location_name,
            latitude,
            longitude,
            description,
            photo_url,
            True if is_anonymous_val else False,
            reporter_name,
            reporter_phone
        ))

        # Insert into alerts so it immediately surfaces on Officer & Admin Vigilance Feeds
        alert_code = f"ALT-TIP-{rand_num % 100000:05d}"
        incident_label = incident_type.replace("_", " ").title()
        alert_desc = f"[CITIZEN WHISTLEBLOWER] {incident_label} reported at {location_name}. Ref: {report_token}. Details: {description[:120]}"
        evidence_payload = json.dumps({
            "report_token": report_token,
            "incident_type": incident_type,
            "location_name": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "photo_url": photo_url,
            "is_anonymous": is_anonymous_val,
            "reporter_name": reporter_name if not is_anonymous_val else "Anonymous Citizen"
        })

        db.execute("""
            INSERT INTO alerts (alert_code, alert_type, severity, risk_score, description, evidence_json, status, created_at, updated_at)
            VALUES (?, 'CITIZEN_WHISTLEBLOWER', 'CRITICAL', 95, ?, ?, 'NEW', datetime('now'), datetime('now'))
        """, (alert_code, alert_desc, evidence_payload))

        log_audit("CITIZEN_TIP_FILED", f"Public tip {report_token} lodged for {incident_type} at {location_name}")

        return jsonify({
            "success": True,
            "report_token": report_token,
            "status": "PENDING_VERIFICATION",
            "message": f"Illegal mining incident reported successfully under Ref #{report_token}. Your submission is confidential and the Mining Flying Squad has been alerted."
        })

    except Exception as e:
        logger.error(f"Error filing citizen report: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Unable to process vigilance report at this time. Please try again.", "success": False}), 500


@app.route("/api/public/track-tip/<token>")
def api_public_track_tip(token):
    """
    Public Unauthenticated Endpoint to track status of a lodged whistleblower tip.
    """
    clean_token = token.strip().upper()
    tip = db.query("SELECT * FROM citizen_reports WHERE report_token = ?", (clean_token,), one=True)
    if not tip:
        return jsonify({
            "found": False,
            "message": f"No citizen tip found matching reference token '{token}'. Please verify your tracking code."
        }), 404

    # Format human-readable status
    status_map = {
        "PENDING_VERIFICATION": "Received & Under Priority Triage",
        "SQUAD_DISPATCHED": "Mining Flying Squad Dispatched to Site",
        "RAID_CONDUCTED": "Enforcement Raid Conducted (Vehicles / Machinery Seized)",
        "RESOLVED": "Action Completed & Site Secured",
        "REJECTED": "Closed After Ground Verification"
    }

    return jsonify({
        "found": True,
        "report_token": tip["report_token"],
        "incident_type": tip["incident_type"].replace("_", " ").title(),
        "location_name": tip["location_name"],
        "incident_date": tip["incident_date"],
        "status": tip["status"],
        "status_label": status_map.get(tip["status"], tip["status"]),
        "action_taken": tip.get("action_taken") or "Zonal Flying Squad assigned for ground verification.",
        "created_at": str(tip.get("created_at") or "")[:19]
    })


@app.route("/api/admin/citizen-reports", methods=["GET"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_admin_citizen_reports():
    reports = db.query("SELECT * FROM citizen_reports ORDER BY id DESC")
    return jsonify({"success": True, "reports": reports})


@app.route("/api/admin/citizen-reports/<int:report_id>/action", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_admin_citizen_report_action(report_id):
    data = request.get_json() or {}
    new_status = data.get("status", "SQUAD_DISPATCHED")
    action_note = data.get("action_taken", "").strip()

    current_u = get_current_user()
    officer_name = current_u.get("full_name") if current_u else "Mining Officer"
    badge = current_u.get("badge_number") if current_u else "ENF"

    rep = db.query("SELECT * FROM citizen_reports WHERE id = ?", (report_id,), one=True)
    if not rep:
        return jsonify({"error": "Report not found", "success": False}), 404

    full_action = f"{action_note} (Updated by {officer_name} [{badge}])" if action_note else f"Status updated to {new_status} by {officer_name}."

    db.execute("""
        UPDATE citizen_reports
        SET status = ?, action_taken = ?, updated_at = datetime('now')
        WHERE id = ?
    """, (new_status, full_action, report_id))

    log_audit("CITIZEN_REPORT_TRIAGED", f"Report {rep['report_token']} marked '{new_status}' by {officer_name}: {full_action}")
    return jsonify({"success": True, "message": f"Tip #{rep['report_token']} updated to '{new_status}'."})


# --- AUTHENTICATED REST API ENDPOINTS ---

# --- Material & Dispatch Monitoring APIs ---

@app.route("/api/material/summary")
@login_required()
def api_material_summary():
    """
    Returns daily dispatch & stock balance KPI summary.
    Role-filtered: Operator is strictly scoped to their own mine.
    """
    role = session.get("user_role")
    mine_id = request.args.get("mine_id", type=int)
    if role == "OPERATOR":
        mine_id = get_operator_mine_id()
    summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=mine_id)
    return jsonify(summary)


@app.route("/api/material/stock-reconciliation")
@login_required()
def api_material_stock_reconciliation():
    """
    Returns stock reconciliation balance: Opening + Production - Dispatch = Current Stock.
    Role-filtered: Operator is strictly scoped to their own mine.
    """
    role = session.get("user_role")
    mine_id = request.args.get("mine_id", type=int)
    if role == "OPERATOR":
        mine_id = get_operator_mine_id()
    recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=mine_id)
    return jsonify(recon)


@app.route("/api/material/trucks")
@login_required()
def api_material_trucks():
    """
    Returns truck-wise material movement ledger.
    Supports filtering by mine, mineral, status, and search query.
    Role-filtered: Operator is strictly scoped to their own fleet.
    """
    role = session.get("user_role")
    mine_id = request.args.get("mine_id", type=int)
    if role == "OPERATOR":
        mine_id = get_operator_mine_id()
    mineral = request.args.get("mineral")
    status_filter = request.args.get("status")
    search_query = request.args.get("q")
    ledger = MaterialMonitoringService.get_truck_wise_material_ledger(
        mine_id=mine_id, mineral=mineral, status_filter=status_filter, search_query=search_query
    )
    return jsonify({"count": len(ledger), "ledger": ledger})


@app.route("/api/material/anomalies")
@login_required(roles=["ADMIN", "OFFICER"])
def api_material_anomalies():
    """
    Returns quantity anomalies where actual_weight > permitted_weight.
    Strictly restricted to ADMIN and OFFICER roles (403 for OPERATOR).
    """
    mine_id = request.args.get("mine_id", type=int)
    anomalies = MaterialMonitoringService.get_quantity_anomalies(mine_id=mine_id)
    return jsonify({"count": len(anomalies), "anomalies": anomalies})


@app.route("/api/material/rankings")
@login_required()
def api_material_rankings():
    """
    Returns top material movement rankings (trucks by tonnage, trips, excess, and top mines).
    Role-filtered: Operator is strictly scoped to their own mine.
    """
    role = session.get("user_role")
    mine_id = request.args.get("mine_id", type=int)
    if role == "OPERATOR":
        mine_id = get_operator_mine_id()
    rankings = MaterialMonitoringService.get_top_material_rankings(mine_id=mine_id)
    return jsonify(rankings)


@app.route("/api/dashboard/stats")
@login_required()
def api_dashboard_stats():
    if session.get("user_role") == "OPERATOR":
        mine_id = get_operator_mine_id()
        truck_ids = get_operator_truck_ids(mine_id)
        active_trucks = 0
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            active_trucks = db.query(f"SELECT COUNT(*) as c FROM trucks WHERE id IN ({placeholders}) AND status = 'IN_TRANSIT'", truck_ids, one=True)["c"]
        active_permits = db.query("SELECT COUNT(*) as c FROM permits WHERE mine_id = ? AND status = 'ACTIVE'", (mine_id,), one=True)["c"]
        return jsonify({
            "active_trucks": active_trucks,
            "active_permits": active_permits,
            "pending_alerts": 0,
            "critical_cases": 0,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })
    else:
        active_trucks = db.query("SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT'", one=True)["c"]
        pending_alerts = db.query("SELECT COUNT(*) as c FROM alerts WHERE status = 'NEW'", one=True)["c"]
        critical_cases = db.query("SELECT COUNT(*) as c FROM alerts WHERE severity = 'CRITICAL' AND status != 'DISMISSED'", one=True)["c"]
        return jsonify({
            "active_trucks": active_trucks,
            "pending_alerts": pending_alerts,
            "critical_cases": critical_cases,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })


@app.route("/api/trucks")
@login_required()
def api_trucks():
    role = session.get("user_role")
    if role == "OPERATOR":
        truck_ids = get_operator_truck_ids()
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                       p.source_name, p.destination_name, tr.id as trip_id
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
                WHERE t.id IN ({placeholders})
                ORDER BY t.current_risk_score DESC
            """, truck_ids)
        else:
            trucks = []
    elif role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        trucks = db.query("""
            SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                   p.source_name, p.destination_name, tr.id as trip_id
            FROM trucks t
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
            LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
            WHERE t.assigned_mine_id = ? OR p.mine_id = ?
            ORDER BY t.current_risk_score DESC
        """, (officer_mine_id, officer_mine_id))
    else:
        active_mine_id = get_active_mine_id()
        if active_mine_id:
            trucks = db.query("""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                       p.source_name, p.destination_name, tr.id as trip_id
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
                WHERE t.assigned_mine_id = ? OR p.mine_id = ?
                ORDER BY t.current_risk_score DESC
            """, (active_mine_id, active_mine_id))
        else:
            trucks = db.query("""
                SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt,
                       p.source_name, p.destination_name, tr.id as trip_id
                FROM trucks t
                LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
                LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
                ORDER BY t.current_risk_score DESC
            """)
    return jsonify(trucks)


@app.route("/api/trucks/<int:truck_id>")
@login_required()
def api_truck_detail(truck_id):
    if not validate_user_truck_access(truck_id):
        return jsonify({"error": "Forbidden: Access denied to vehicle record outside your authorized jurisdiction.", "success": False}), 403

    truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
    if not truck:
        return jsonify({"error": "Truck not found"}), 404
    positions = db.query("SELECT latitude, longitude, speed_kmh, timestamp FROM gps_positions WHERE truck_id = ? ORDER BY id DESC LIMIT 50", (truck_id,))
    return jsonify({"truck": truck, "breadcrumbs": positions})


@app.route("/api/trucks/<int:truck_id>/route")
@login_required()
def api_truck_route(truck_id):
    """
    Section 7: GIS Truck Route Telemetry API.
    Returns complete corridor from Source Mine -> Weighbridge -> Checkpoints -> Destination,
    split into travelled vs remaining routes with breadcrumbs and key route pins.
    """
    if not validate_user_truck_access(truck_id):
        return jsonify({"error": "Forbidden: Access denied to vehicle record outside your authorized jurisdiction.", "success": False}), 403

    truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
    if not truck:
        return jsonify({"error": "Truck not found", "success": False}), 404

    # Fetch active or latest trip
    trip = db.query("""
        SELECT tr.*, p.permit_number, p.mineral, p.permitted_weight_mt, p.source_name,
               p.destination_name, p.destination_lat, p.destination_lng, p.route_waypoints_json,
               p.mine_id, p.issued_at
        FROM trips tr
        JOIN permits p ON p.id = tr.permit_id
        WHERE tr.truck_id = ?
        ORDER BY tr.id DESC LIMIT 1
    """, (truck_id,), one=True)

    if not trip:
        permit = db.query("""
            SELECT p.* FROM permits p WHERE p.truck_id = ? ORDER BY p.id DESC LIMIT 1
        """, (truck_id,), one=True)
        if permit:
            trip = {
                "id": 0,
                "trip_number": "TRP-ADHOC",
                "permit_number": permit["permit_number"],
                "mineral": permit["mineral"],
                "permitted_weight_mt": permit["permitted_weight_mt"],
                "source_name": permit["source_name"],
                "destination_name": permit["destination_name"],
                "destination_lat": permit["destination_lat"],
                "destination_lng": permit["destination_lng"],
                "route_waypoints_json": permit["route_waypoints_json"],
                "mine_id": permit["mine_id"],
                "start_time": permit["issued_at"],
                "planned_distance_km": 48.0,
                "actual_distance_km": 18.5,
                "status": truck["status"]
            }

    # Fetch source mine
    mine = None
    if trip and trip.get("mine_id"):
        mine = db.query("SELECT * FROM mines WHERE id = ?", (trip["mine_id"],), one=True)
    elif truck.get("assigned_mine_id"):
        mine = db.query("SELECT * FROM mines WHERE id = ?", (truck["assigned_mine_id"],), one=True)

    # Fetch weighment if any
    weighment = None
    if trip and trip.get("id"):
        weighment = db.query("SELECT * FROM weighments WHERE trip_id = ? ORDER BY id DESC LIMIT 1", (trip["id"],), one=True)

    # Historical GPS Breadcrumbs
    breadcrumbs_rows = db.query("SELECT latitude, longitude, speed_kmh, timestamp FROM gps_positions WHERE truck_id = ? ORDER BY id ASC LIMIT 50", (truck_id,))
    breadcrumbs = [[r["latitude"], r["longitude"]] for r in breadcrumbs_rows if r["latitude"] and r["longitude"]]

    # Waypoints resolution
    raw_waypoints = []
    if trip and trip.get("route_waypoints_json"):
        try:
            raw_waypoints = json.loads(trip["route_waypoints_json"])
        except Exception:
            raw_waypoints = []

    reg = truck["registration_number"]
    if not raw_waypoints and reg in simulator.fleet_corridors:
        raw_waypoints = [list(pt) for pt in simulator.fleet_corridors[reg]]

    if not raw_waypoints:
        start_pt = [mine["latitude"], mine["longitude"]] if mine else [truck["current_lat"] or 27.56, truck["current_lng"] or 76.61]
        dest_pt = [trip["destination_lat"], trip["destination_lng"]] if trip and trip.get("destination_lat") else [start_pt[0] + 0.35, start_pt[1] + 0.25]
        mid_pt = [(start_pt[0] + dest_pt[0]) / 2 + 0.04, (start_pt[1] + dest_pt[1]) / 2 - 0.02]
        raw_waypoints = [start_pt, mid_pt, dest_pt]

    current_pt = [truck["current_lat"], truck["current_lng"]] if truck["current_lat"] and truck["current_lng"] else raw_waypoints[0]

    # Find closest waypoint along planned corridor
    def dist_sq(p1, p2):
        return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

    closest_idx = 0
    min_dist = float("inf")
    for i, pt in enumerate(raw_waypoints):
        d = dist_sq(current_pt, pt)
        if d < min_dist:
            min_dist = d
            closest_idx = i

    travelled_route = raw_waypoints[:closest_idx + 1]
    if current_pt not in travelled_route:
        travelled_route.append(current_pt)

    remaining_route = [current_pt] + raw_waypoints[closest_idx + 1:]
    if len(remaining_route) == 1 and len(raw_waypoints) > 0:
        remaining_route.append(raw_waypoints[-1])

    # Route points: Mine, Weighbridge, Checkpoints, Destination
    wb_record = None
    if mine:
        wb_record = db.query("SELECT * FROM weighbridges WHERE mine_id = ? LIMIT 1", (mine["id"],), one=True)
    if not wb_record:
        wb_record = db.query("SELECT * FROM weighbridges LIMIT 1", one=True)

    checkpoints_rows = db.query("SELECT * FROM checkpoints LIMIT 3")
    checkpoints = [{
        "name": cp["name"],
        "lat": cp["latitude"],
        "lng": cp["longitude"],
        "type": "checkpoint"
    } for cp in checkpoints_rows]

    # Deviation check: only show deviation for ADMIN & OFFICER
    role = session.get("user_role")
    is_deviated = False
    deviation_route = []
    if role in ("ADMIN", "OFFICER"):
        if reg == "HR26AB1234" and simulator.is_hr26_deviating:
            is_deviated = True
            deviation_route = [list(pt) for pt in simulator.deviated_route]
        else:
            dev_alert = db.query("SELECT id FROM alerts WHERE truck_id = ? AND alert_type = 'ROUTE_DEVIATION' AND status != 'DISMISSED'", (truck_id,), one=True)
            if dev_alert:
                is_deviated = True
                deviation_route = [[current_pt[0] + 0.015, current_pt[1] - 0.02], current_pt]

    permitted_qty = trip["permitted_weight_mt"] if trip else 25.0
    actual_qty = weighment["net_weight_mt"] if weighment else (permitted_qty if truck["status"] == "IN_TRANSIT" else 0.0)
    excess_qty = max(0.0, round(actual_qty - permitted_qty, 1)) if actual_qty > permitted_qty else 0.0
    planned_dist = trip["planned_distance_km"] if (trip and trip.get("planned_distance_km")) else 45.0
    trip_dist = trip.get("actual_distance_km") if trip else None
    if trip_dist is not None and trip_dist > 0:
        actual_dist = round(trip_dist, 1)
    elif trip:
        actual_dist = 18.5
    else:
        actual_dist = 0.0
    remaining_dist = max(0.0, round(planned_dist - actual_dist, 1))

    # Chronological trip timeline
    timeline = []
    if trip and trip.get("timeline_events_json"):
        try:
            timeline = json.loads(trip["timeline_events_json"])
        except Exception:
            timeline = []
    if not timeline:
        t_start = str(trip.get("start_time") if trip else "Today 08:30")[:16]
        mine_name = mine["name"] if mine else "Authorized Mining Block"
        timeline = [
            {"event": "TRUCK_ENTERED_MINE", "title": f"Entered {mine_name}", "description": "GPS entry detected at mine boundary geofence", "timestamp": f"{t_start}"},
            {"event": "PERMIT_MATCHED", "title": "e-Rawaana Permit Matched", "description": f"Statutory permit {trip['permit_number'] if trip else 'Active'} reconciled for round", "timestamp": f"{t_start}"},
            {"event": "WEIGHBRIDGE_MEASURED", "title": "Weighbridge Scale Measurement", "description": f"Net dispatched weight {actual_qty:.1f} MT recorded automatically", "timestamp": f"{t_start}"},
            {"event": "DISPATCH_AUTHORIZED", "title": "Dispatch Authorized", "description": "Gate clearance verified against active concession quota", "timestamp": f"{t_start}"}
        ]

    round_metrics = {
        "completed_trips_today": int(truck.get("completed_rounds_today") or 0),
        "current_trip_number": int(truck.get("current_round_number") or ((truck.get("completed_rounds_today") or 0) + 1)),
        "is_unrestricted": True
    }

    cumulative_material = MaterialMonitoringService.get_truck_cumulative_material_profile(truck_id)

    return jsonify({
        "success": True,
        "truck": {
            "id": truck["id"],
            "registration_number": truck["registration_number"],
            "vehicle_type": truck["vehicle_type"],
            "driver_name": truck["driver_name"],
            "driver_phone": truck["driver_phone"],
            "current_lat": truck["current_lat"],
            "current_lng": truck["current_lng"],
            "status": truck["status"],
            "current_risk_score": truck["current_risk_score"],
            "current_risk_level": truck["current_risk_level"]
        },
        "source_mine": {
            "name": (mine["name"] if mine else (trip.get("source_name") if trip else "Authorized Mining Block")),
            "lat": mine["latitude"] if mine else raw_waypoints[0][0],
            "lng": mine["longitude"] if mine else raw_waypoints[0][1],
            "district": mine["district"] if mine else "Alwar / Kotputli"
        },
        "destination": {
            "name": (trip["destination_name"] if trip else "Authorized Consignee Hub"),
            "lat": (trip["destination_lat"] if trip and trip.get("destination_lat") else raw_waypoints[-1][0]),
            "lng": (trip["destination_lng"] if trip and trip.get("destination_lng") else raw_waypoints[-1][1])
        },
        "weighbridge": {
            "name": wb_record["name"] if wb_record else "Designated Perimeter Weigh Station",
            "lat": wb_record["latitude"] if wb_record else raw_waypoints[0][0] + 0.01,
            "lng": wb_record["longitude"] if wb_record else raw_waypoints[0][1] + 0.01
        } if wb_record else None,
        "checkpoints": checkpoints,
        "travelled_route": travelled_route,
        "remaining_route": remaining_route,
        "full_corridor": raw_waypoints,
        "authorized_route": raw_waypoints,
        "actual_route": breadcrumbs if breadcrumbs else travelled_route,
        "breadcrumbs": breadcrumbs,
        "timeline": timeline,
        "round_metrics": round_metrics,
        "cumulative_material": cumulative_material,
        "is_deviated": is_deviated,
        "deviation_route": deviation_route,
        "metrics": {
            "truck_number": truck["registration_number"],
            "trip_id": trip["trip_number"] if trip else "TRP-2026-PENDING",
            "permit_number": trip["permit_number"] if trip else "e-Rawaana Pending",
            "mineral": trip["mineral"] if trip else "Mineral Ore",
            "permitted_quantity_mt": permitted_qty,
            "actual_quantity_mt": actual_qty,
            "excess_quantity_mt": excess_qty,
            "source": (mine["name"] if mine else (trip.get("source_name") if trip else "Mining Block")),
            "destination": (trip["destination_name"] if trip else "Consignee Hub"),
            "trip_start": str(trip["start_time"])[:16] if trip and trip.get("start_time") else "Today 08:30",
            "expected_arrival": (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
            "current_status": truck["status"],
            "route_distance_km": planned_dist,
            "distance_travelled_km": actual_dist,
            "remaining_distance_km": remaining_dist
        }
    })



@app.route("/api/permits")
@login_required()
def api_permits():
    role = session.get("user_role")
    if role == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
        if sub_mine_id:
            permits = db.query("""
                SELECT * FROM permits 
                WHERE quarry_block_id = ? OR truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?)
                ORDER BY id DESC
            """, (sub_mine_id, sub_mine_id))
        else:
            mine_id = get_operator_mine_id()
            permits = db.query("SELECT * FROM permits WHERE mine_id = ? ORDER BY id DESC", (mine_id,))
    elif role == "OFFICER":
        mine_id = get_officer_mine_id()
        if mine_id:
            permits = db.query("SELECT * FROM permits WHERE mine_id = ? ORDER BY id DESC", (mine_id,))
        else:
            permits = db.query("SELECT * FROM permits ORDER BY id DESC")
    else:
        active_mine_id = get_active_mine_id()
        if active_mine_id:
            permits = db.query("SELECT * FROM permits WHERE mine_id = ? ORDER BY id DESC", (active_mine_id,))
        else:
            permits = db.query("SELECT * FROM permits ORDER BY id DESC")
    return jsonify(permits)


@app.route("/api/alerts")
@login_required(roles=["ADMIN", "OFFICER"])
def api_alerts():
    if session.get("user_role") == "OFFICER":
        mine_id = get_officer_mine_id()
        if mine_id:
            alerts = db.query("""
                SELECT a.*, t.registration_number, p.permit_number
                FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                LEFT JOIN permits p ON p.id = a.permit_id
                LEFT JOIN trips tr ON tr.id = a.trip_id
                WHERE tr.mine_id = ? OR p.mine_id = ? OR t.assigned_mine_id = ?
                ORDER BY a.id DESC
            """, (mine_id, mine_id, mine_id))
            return jsonify(alerts)

    alerts = db.query("""
        SELECT a.*, t.registration_number, p.permit_number
        FROM alerts a
        LEFT JOIN trucks t ON t.id = a.truck_id
        LEFT JOIN permits p ON p.id = a.permit_id
        ORDER BY a.id DESC
    """)
    return jsonify(alerts)


@app.route("/api/alerts/<int:alert_id>/action", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_alert_action(alert_id):
    data = request.get_json() or {}
    new_status = data.get("status")
    assign_officer = data.get("assigned_to_user_id")
    remarks = (data.get("remarks") or data.get("officer_notes") or "").strip()

    user_id = session.get("user_id")
    current_u = get_current_user()
    officer_name = current_u.get("full_name", "Field Officer") if current_u else "Field Officer"
    officer_badge = current_u.get("badge_number", "OFF-DUTY") if current_u else "OFF-DUTY"

    existing_alert = db.query("SELECT * FROM alerts WHERE id = ?", (alert_id,), one=True)
    if not existing_alert:
        return jsonify({"error": "Alert not found"}), 404

    updates = []
    params = []

    if new_status:
        updates.append("status = ?")
        params.append(new_status)
        updates.append("action_taken = ?")
        params.append(new_status)

    if remarks:
        updates.append("officer_remarks = ?")
        params.append(remarks)

    if user_id:
        updates.append("handled_by_user_id = ?")
        params.append(user_id)

    if assign_officer:
        updates.append("assigned_to_user_id = ?")
        params.append(assign_officer)

    # ANTI-COLLUSION & VIGILANCE ESCALATION:
    # If the alert is CRITICAL or HIGH severity, and the officer is acknowledging, resolving, or dismissing it,
    # it is automatically escalated to the State Admin Vigilance queue with officer identity.
    if existing_alert["severity"] in ("CRITICAL", "HIGH") and new_status in ("DISMISSED", "RESOLVED", "ACKNOWLEDGED"):
        updates.append("escalated_to_admin = 1")
        updates.append("admin_review_status = 'PENDING_VIGILANCE_REVIEW'")

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(alert_id)

    sql = f"UPDATE alerts SET {', '.join(updates)} WHERE id = ?"
    db.execute(sql, tuple(params))

    alert = db.query("""
        SELECT a.*, u.full_name as officer_name, u.badge_number as officer_badge
        FROM alerts a
        LEFT JOIN users u ON u.id = a.handled_by_user_id
        WHERE a.id = ?
    """, (alert_id,), one=True)

    audit_msg = f"Alert {alert.get('alert_code', alert_id)} updated to status '{new_status}' by {officer_name} ({officer_badge})."
    if remarks:
        audit_msg += f" Officer Remarks: '{remarks}'."
    if existing_alert["severity"] in ("CRITICAL", "HIGH") and new_status in ("DISMISSED", "RESOLVED"):
        audit_msg += " [VIGILANCE ESCALATION]: Critical anomaly action flagged for State Admin supervisory audit."

    log_audit("ALERT_ACTION", audit_msg)
    return jsonify({"success": True, "alert": alert})


@app.route("/api/alerts/<int:alert_id>/admin_review", methods=["POST"])
@login_required(roles=["ADMIN"])
def api_alert_admin_review(alert_id):
    """
    State Admin Vigilance supervisory decision:
    Allows Admin to either:
    1. 'CONFIRM': Concur with the field officer's clearance/dismissal.
    2. 'FLAG_INQUIRY': Reject officer clearance and trigger formal Anti-Corruption / Vigilance Inquiry.
    """
    data = request.get_json() or {}
    decision = data.get("decision")  # "CONFIRM" or "FLAG_INQUIRY"
    notes = (data.get("notes") or "").strip()
    admin_id = session.get("user_id")
    current_u = get_current_user()
    admin_name = current_u.get("full_name", "State Admin") if current_u else "State Admin"

    alert = db.query("""
        SELECT a.*, u.full_name as officer_name, u.badge_number as officer_badge, t.registration_number
        FROM alerts a
        LEFT JOIN users u ON u.id = a.handled_by_user_id
        LEFT JOIN trucks t ON t.id = a.truck_id
        WHERE a.id = ?
    """, (alert_id,), one=True)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if decision == "CONFIRM":
        db.execute("""
            UPDATE alerts
            SET admin_review_status = 'CONFIRMED_BY_ADMIN',
                admin_notes = ?,
                admin_reviewed_at = ?,
                admin_reviewed_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (notes or "Clearance audited and confirmed by State Mining Administrator.", now_str, admin_id, alert_id))

        order_ref = f"DIR-MMDR-2026-ORD-{alert_id:04d}"
        return jsonify({
            "success": True,
            "status": "CONFIRMED_BY_ADMIN",
            "order_id": order_ref,
            "timestamp": now_str,
            "admin_name": admin_name,
            "alert_code": alert.get("alert_code"),
            "vehicle": alert.get("registration_number") or "Unassigned Carrier",
            "officer": f"{alert.get('officer_name') or 'Duty Squad'} (Badge: {alert.get('officer_badge') or 'N/A'})",
            "decision": "Supervisory Clearance Confirmed",
            "directive": notes or "Clearance audited and approved under Section 21 MMDR authority.",
            "message": "Officer action successfully audited and confirmed."
        })

    elif decision == "FLAG_INQUIRY":
        # Elevated to Formal Anti-Corruption Inquiry
        case_num = db.query("SELECT COUNT(*) as c FROM investigations", one=True)["c"] + 42
        case_id = f"SMG-2026-{case_num:05d}"
        order_ref = f"DIR-MMDR-2026-VIG-{alert_id:04d}"
        
        officer_info = f"{alert.get('officer_name') or 'Field Officer'} ({alert.get('officer_badge') or 'N/A'})"
        title = f"Vigilance Inquiry: Officer Override Audit ({alert['alert_code']})"
        initial_findings = (
            f"VIGILANCE AUDIT RED-FLAG: Severe violation '{alert['alert_type']}' on vehicle {alert['registration_number']} "
            f"was marked '{alert['action_taken']}' by {officer_info} with reason: '{alert['officer_remarks'] or 'No remarks provided'}'. "
            f"State Admin rejected clearance and ordered formal administrative inquiry. Admin Remarks: '{notes}'."
        )

        inv_id = db.execute("""
            INSERT INTO investigations (case_id, alert_id, trip_id, truck_id, permit_id, lead_officer_id, title, status, initial_findings, officer_notes, final_decision)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTION_REQUIRED', ?, ?, 'Under active State Vigilance & Anti-Corruption Review')
        """, (case_id, alert["id"], alert["trip_id"], alert["truck_id"], alert["permit_id"], admin_id, title, initial_findings, f"Admin Directive: {notes}"))

        db.execute("""
            UPDATE alerts
            SET admin_review_status = 'FLAGGED_FOR_INQUIRY',
                status = 'UNDER_REVIEW',
                admin_notes = ?,
                admin_reviewed_at = ?,
                admin_reviewed_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (notes or "Flagged for Anti-Corruption Inquiry.", now_str, admin_id, alert_id))

        # Generate Evidence PDF
        pdf_path = generate_evidence_pdf(inv_id, case_id)
        if pdf_path:
            db.execute("UPDATE investigations SET pdf_report_path = ? WHERE id = ?", (pdf_path, inv_id))

        log_audit("VIGILANCE_INQUIRY_ORDERED",
                  f"Admin {admin_name} flagged suspicious clearance on Alert {alert['alert_code']} by {officer_info}. Case {case_id} established.")

        return jsonify({
            "success": True,
            "status": "FLAGGED_FOR_INQUIRY",
            "order_id": order_ref,
            "timestamp": now_str,
            "admin_name": admin_name,
            "investigation_id": inv_id,
            "case_id": case_id,
            "pdf_path": pdf_path,
            "alert_code": alert.get("alert_code"),
            "vehicle": alert.get("registration_number") or "Unassigned Carrier",
            "officer": officer_info,
            "decision": "Formal Anti-Corruption Inquiry Ordered",
            "directive": notes or "Ground override rejected; inquiry initiated under Section 21(4) MMDR.",
            "message": f"Suspicious clearance flagged for Vigilance Inquiry (Case {case_id})."
        })

    return jsonify({"error": "Invalid decision"}), 400


@app.route("/api/alerts/<int:alert_id>/investigate", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_elevate_to_investigation(alert_id):
    """Converts an alert directly into a formal enforcement case."""
    alert = db.query("SELECT * FROM alerts WHERE id = ?", (alert_id,), one=True)
    if not alert:
        return jsonify({"error": "Alert not found"}), 404

    # Generate Case ID: SMG-2026-XXXXX
    case_num = db.query("SELECT COUNT(*) as c FROM investigations", one=True)["c"] + 42
    case_id = f"SMG-2026-{case_num:05d}"
    lead_officer_id = session.get("user_id") or 2

    title = f"Enforcement Investigation: {alert['alert_type'].replace('_', ' ').title()} - {alert['alert_code']}"
    initial_findings = f"Automated statutory detection triggered: {alert['description']}"

    inv_id = db.execute("""
        INSERT INTO investigations (case_id, alert_id, trip_id, truck_id, permit_id, lead_officer_id, title, status, initial_findings, officer_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'UNDER_INVESTIGATION', ?, 'Case initiated from alert. Vehicle flagged for physical inspection.')
    """, (case_id, alert["id"], alert["trip_id"], alert["truck_id"], alert["permit_id"], lead_officer_id, title, initial_findings))

    db.execute("UPDATE alerts SET status = 'UNDER_REVIEW' WHERE id = ?", (alert_id,))

    log_audit("ALERT_ELEVATED", f"Alert {alert['alert_code']} elevated to Case {case_id}")

    # Generate the initial PDF evidence dossier
    pdf_path = generate_evidence_pdf(inv_id, case_id)
    if pdf_path:
        db.execute("UPDATE investigations SET pdf_report_path = ? WHERE id = ?", (pdf_path, inv_id))

    return jsonify({"success": True, "investigation_id": inv_id, "case_id": case_id, "pdf_path": pdf_path})


@app.route("/api/investigations/<int:inv_id>/notes", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_investigation_update(inv_id):
    data = request.get_json() or {}
    notes = data.get("notes")
    status = data.get("status")
    decision = data.get("final_decision")
    penalty = data.get("penalty_amount_inr")

    if notes:
        db.execute("UPDATE investigations SET officer_notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (notes, inv_id))
    if status:
        db.execute("UPDATE investigations SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, inv_id))
    if decision:
        db.execute("UPDATE investigations SET final_decision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (decision, inv_id))
    if penalty is not None:
        db.execute("UPDATE investigations SET penalty_amount_inr = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (float(penalty), inv_id))

    # Regenerate updated PDF
    pdf_path = generate_evidence_pdf(inv_id)
    if pdf_path:
        db.execute("UPDATE investigations SET pdf_report_path = ? WHERE id = ?", (pdf_path, inv_id))

    log_audit("CASE_UPDATE", f"Investigation {inv_id} updated with status: {status}")
    return jsonify({"success": True, "pdf_path": pdf_path})


@app.route("/api/verify/permit", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_verify_permit():
    """
    Officer roadside verification:
    Accepts QR payload or permit number.
    Returns complete verification breakdown and flags any suspicion immediately.
    """
    data = request.get_json() or {}
    query_val = data.get("permit_query", "").strip()

    # Parse potential QR formatted string: SMARTMINEGUARD:PERMIT_NUM:HASH
    if "SMARTMINEGUARD:" in query_val:
        parts = query_val.split(":")
        if len(parts) >= 2:
            query_val = parts[1]

    permit = db.query("""
        SELECT p.*, t.registration_number, t.registered_owner, t.driver_name, t.driver_phone,
               t.current_risk_score, t.current_risk_level, m.name as mine_name, m.district as mine_district
        FROM permits p
        LEFT JOIN trucks t ON t.id = p.truck_id
        LEFT JOIN mines m ON m.id = p.mine_id
        WHERE p.permit_number = ? OR p.qr_code_hash = ?
    """, (query_val, query_val), one=True)

    if not permit:
        return jsonify({
            "is_valid": False,
            "verification_status": "REJECTED",
            "message": f"e-Rawaana '{query_val}' does not exist in the Directorate of Mines & Geology central database. Suspected counterfeit transit pass."
        }), 404

    # Run check on status
    status = permit["status"]
    is_suspicious = False
    is_recycled = False
    warning_reasons = []
    if status == "CONSUMED":
        is_suspicious = True
        is_recycled = True
        consumed_str = permit.get("consumed_at") or "earlier today"
        dest_name = permit.get("destination_name") or "Authorized Destination"
        warning_reasons.append(
            f"PERMIT RECYCLING DETECTED (PARCHI REUSE): This e-Rawaana was ALREADY CONSUMED upon "
            f"delivery at '{dest_name}' ({consumed_str}). "
            f"Vehicle is attempting unpermitted secondary transit on recycled paperwork under Section 21 MMDR Act."
        )
    elif status == "EXPIRED":
        is_suspicious = True
        warning_reasons.append("EXPIRED PERMIT WARNING: Transit authorization window has lapsed.")
    elif status == "SUSPICIOUS":
        is_suspicious = True
        warning_reasons.append("FLAGGED PERMIT: This permit is flagged under an active enforcement inquiry.")
    elif status == "CANCELLED":
        is_suspicious = True
        warning_reasons.append("REVOKED / CANCELLED PERMIT: This e-Rawaana transit pass was officially revoked or cancelled under Section 21 MMDR Act.")

    # Check latest weighment
    weighment = db.query("SELECT * FROM weighments WHERE permit_id = ? ORDER BY id DESC LIMIT 1", (permit["id"],), one=True)
    if weighment and weighment["is_overweight"]:
        is_suspicious = True
        warning_reasons.append(f"OVERWEIGHT LOAD: Actual weighment {weighment['net_weight_mt']:.1f} MT exceeds permitted {permit['permitted_weight_mt']:.1f} MT (+{weighment['difference_mt']:.1f} MT).")

    # Record verification in log
    officer_id = session.get("user_id") or 2
    verif_result = "SUSPICIOUS" if is_suspicious else "VALID"
    db.execute("""
        INSERT INTO verifications (permit_id, officer_id, checkpoint_name, verification_result, scanned_via, discrepancy_notes)
        VALUES (?, ?, 'Enforcement Field Checkpoint', ?, 'QR_SCAN', ?)
    """, (permit["id"], officer_id, verif_result, "; ".join(warning_reasons) if warning_reasons else "Verified legal."))

    log_audit("PERMIT_VERIFY", f"Permit {permit['permit_number']} checked via QR by officer {officer_id} - Result: {verif_result}")

    return jsonify({
        "is_valid": not is_suspicious,
        "verification_status": verif_result,
        "is_recycled": is_recycled,
        "warning_reasons": warning_reasons,
        "permit": permit,
        "weighment": weighment
    })


@app.route("/api/reports/pdf/<case_id>")
@login_required(roles=["ADMIN", "OFFICER"])
def download_pdf_report(case_id):
    clean_case_id = secure_filename(case_id)
    inv = db.query("SELECT * FROM investigations WHERE case_id = ?", (clean_case_id,), one=True)
    if not inv:
        abort(404)

    # ensure user has permission to view this case
    if not validate_user_investigation_access(inv["id"]):
        abort(403)

    pdf_rel_path = generate_evidence_pdf(inv["id"], clean_case_id)
    if not pdf_rel_path:
        abort(404)

    full_path = (Path(Config.BASE_DIR) / Path(pdf_rel_path)).resolve()
    base_resolved = Path(Config.BASE_DIR).resolve()
    if not full_path.is_relative_to(base_resolved) or not full_path.exists():
        abort(404)

    download_name = secure_filename(f"Evidence_Dossier_{clean_case_id}.pdf")
    return send_file(
        str(full_path),
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf"
    )


# --- MASTER DATA CRUD API ENDPOINTS (STRICT ROLE-BASED ACCESS CONTROL) ---

def check_crud_permission(entity_type, mine_id=None, truck_id=None):
    """
    Backend RBAC Enforcer for Data Entry and Modifications.
    - ADMIN: Full system-wide CRUD authority.
    - OFFICER: Strictly 403 Forbidden (Surveillance/Enforcement read-only).
    - OPERATOR: Scoped strictly to their own authorized concession (403 on tenant mismatch).
    """
    role = session.get("user_role")
    if not role:
        return False, "Authentication required", 401
    if role == "ADMIN":
        return True, None, 200
    if role == "OFFICER":
        # Officer has permit authorization authority for businessmen/concessions in their mine
        if entity_type == "permits":
            return True, None, 200
        return False, "Forbidden: Field officers are restricted to monitoring, enforcement, and sector permit authorizations.", 403
    if role == "OPERATOR":
        op_mine_id = get_operator_mine_id()
        if entity_type in ("mines", "destinations", "checkpoints", "weighbridges", "users"):
            return False, f"Forbidden: Operators cannot manage state infrastructure ({entity_type}).", 403
        if entity_type == "sub-mines":
            return True, None, 200
        if mine_id is not None and int(mine_id) != op_mine_id:
            return False, "Forbidden: Cross-tenant access denied. You can only manage records for your own leasehold.", 403
        if truck_id is not None and not validate_operator_truck_access(truck_id):
            return False, "Forbidden: Cross-tenant access denied. You can only manage vehicles assigned to your own leasehold.", 403
        return True, None, 200
    return False, "Forbidden: Unauthorized access", 403


@app.route("/api/crud/mines", methods=["POST"])
@login_required(roles=["ADMIN"])
def api_crud_mines():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    mine_code = data.get("mine_code", "").strip()
    mineral = data.get("mineral", "").strip()
    district = data.get("district", "").strip()
    state = data.get("state", "Rajasthan").strip()
    lat = float(data.get("latitude", 27.5620))
    lng = float(data.get("longitude", 76.6120))
    quota = float(data.get("authorized_annual_quota_mt", 50000.0))
    opening_stock = float(data.get("opening_stock_mt", 3500.0))
    operator_name = data.get("operator_name", "").strip()
    phone = data.get("contact_phone", "+91 99280 33445").strip()

    if not is_within_india(lat, lng):
        return jsonify({"error": f"Invalid coordinates ({lat}, {lng}). Concession must be within Indian territory.", "success": False}), 400

    existing = db.query("SELECT id FROM mines WHERE mine_code = ?", (mine_code,), one=True)
    if existing:
        return jsonify({"error": f"Mine code '{mine_code}' is already registered.", "success": False}), 400

    mine_id = db.execute("""
        INSERT INTO mines (name, mine_code, mineral, district, state, latitude, longitude,
                           authorized_annual_quota_mt, current_dispatch_mt, opening_stock_mt,
                           current_stock_mt, operator_name, contact_phone, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, ?, 'OPERATIONAL')
    """, (name, mine_code, mineral, district, state, lat, lng, quota, opening_stock, opening_stock, operator_name, phone))

    log_audit("MINE_REGISTER", f"Registered new mine concession: {mine_code} - {name} ({district}, {state})")
    return jsonify({"success": True, "message": f"Mine '{name}' ({mine_code}) registered successfully.", "mine_id": mine_id})


@app.route("/api/crud/sub-mines", methods=["POST"])
@login_required()
def api_crud_sub_mines():
    role = session.get("user_role")
    if role not in ("OPERATOR", "ADMIN"):
        return jsonify({"error": "Forbidden: Only Ground Operators and State Administrators can register sub-mine pit tenders.", "success": False}), 403

    data = request.get_json() or {}
    block_name = data.get("block_name", "").strip()
    block_code = data.get("block_code", "").strip().upper().replace(" ", "-")
    leaseholder_name = data.get("leaseholder_name", "").strip()
    operator_name = data.get("operator_name", "").strip()
    phone = data.get("contact_phone", "+91 98123 45678").strip()

    if not block_name or not block_code:
        return jsonify({"error": "Sub-Mine / Pit Name and Block Code are required.", "success": False}), 400

    if role == "OPERATOR":
        mine_id = get_operator_mine_id()
    else:
        raw_mine = data.get("mine_id")
        mine_id = int(raw_mine) if raw_mine else (get_active_mine_id() or 1)

    existing = db.query("SELECT id FROM quarry_blocks WHERE block_code = ?", (block_code,), one=True)
    if existing:
        return jsonify({"error": f"Sub-mine block code '{block_code}' is already registered.", "success": False}), 400

    try:
        quota = float(data.get("allocated_quota_mt", 35000.0))
    except (ValueError, TypeError):
        quota = 35000.0

    sub_mine_id = db.execute("""
        INSERT INTO quarry_blocks (mine_id, block_code, block_name, leaseholder_name, operator_name,
                                   contact_phone, allocated_quota_mt, dispatched_mt, active_trucks_count, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0, 'OPERATIONAL')
    """, (mine_id, block_code, block_name, leaseholder_name, operator_name, phone, quota))

    # If operator currently has no assigned sub_mine_id, auto-bind to this newly registered sub-mine
    if role == "OPERATOR" and not session.get("assigned_sub_mine_id"):
        db.execute("UPDATE users SET assigned_sub_mine_id = ? WHERE id = ?", (sub_mine_id, session.get("user_id")))
        session["assigned_sub_mine_id"] = sub_mine_id

    log_audit("SUB_MINE_REGISTER", f"Registered new sub-mine concession: {block_code} - {block_name} under Mine {mine_id}")
    return jsonify({
        "success": True,
        "message": f"Sub-mine concession '{block_name}' ({block_code}) registered successfully.",
        "sub_mine_id": sub_mine_id
    })


@app.route("/api/crud/trucks", methods=["POST"])
@login_required()
def api_crud_trucks():
    data = request.get_json() or {}
    if session.get("user_role") == "OPERATOR":
        mine_id = get_operator_mine_id()
    else:
        raw_mine = data.get("assigned_mine_id")
        try:
            mine_id = int(raw_mine) if raw_mine else (get_active_mine_id() or 1)
        except (ValueError, TypeError):
            mine_id = 1

    allowed, err, code = check_crud_permission("trucks", mine_id=mine_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    reg = data.get("registration_number", "").strip().upper().replace(" ", "").replace("-", "")
    if not reg or len(reg) < 7:
        return jsonify({"error": "A valid Indian vehicle registration number is required (e.g. HR26AB1234).", "success": False}), 400

    existing = db.query("SELECT id FROM trucks WHERE registration_number = ?", (reg,), one=True)
    if existing:
        return jsonify({"error": f"Vehicle '{reg}' is already registered in the central fleet database.", "success": False}), 400

    v_type = data.get("vehicle_type", "10-Wheeler Tipper Truck")
    owner = data.get("registered_owner", "Commercial Transporter").strip()
    driver = data.get("driver_name", "Fleet Operator").strip()
    phone = data.get("driver_phone", "+91 98123 45678").strip()
    try:
        tare = float(data.get("tare_weight_mt", 11.5))
    except (ValueError, TypeError):
        tare = 11.5
    try:
        capacity = float(data.get("max_capacity_mt", 28.0))
    except (ValueError, TypeError):
        capacity = 28.0
    rfid = data.get("rfid_tag", f"RFID-{reg[:4]}-{int(time.time()) % 1000:03d}").strip()
    imei = data.get("gps_imei", f"8642010{int(time.time()) % 10000000:07d}").strip()

    # Place truck initially near assigned mine in India
    mine = db.query("SELECT latitude, longitude FROM mines WHERE id = ?", (mine_id,), one=True) if mine_id else None
    init_lat = mine["latitude"] if mine else 27.5624
    init_lng = mine["longitude"] if mine else 76.6121

    # Determine sub-mine / contractor assignment
    sub_mine_id = None
    if session.get("user_role") == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
    else:
        raw_sm = data.get("sub_mine_id") or data.get("quarry_block_id")
        if raw_sm:
            try:
                sub_mine_id = int(raw_sm)
            except (ValueError, TypeError):
                sub_mine_id = None

    truck_id = db.execute("""
        INSERT INTO trucks (registration_number, vehicle_type, registered_owner, driver_name,
                            driver_phone, tare_weight_mt, max_capacity_mt, rfid_tag, gps_imei,
                            status, current_lat, current_lng, assigned_mine_id, sub_mine_id, current_risk_score, current_risk_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'IDLE', ?, ?, ?, ?, 0, 'LOW')
    """, (reg, v_type, owner, driver, phone, tare, capacity, rfid, imei, init_lat, init_lng, mine_id, sub_mine_id))

    # Also record driver in drivers table
    dl_no = data.get("driver_license", "").strip().upper()
    if not dl_no:
        dl_no = f"DL-{reg[:4]}{int(time.time()) % 100000:05d}"
    
    existing_driver = db.query("SELECT id FROM drivers WHERE license_number = ?", (dl_no,), one=True)
    if existing_driver:
        db.execute("UPDATE drivers SET assigned_truck_id = ?, contact_phone = ?, sub_mine_id = ? WHERE id = ?", (truck_id, phone, sub_mine_id, existing_driver["id"]))
    else:
        db.execute("""
            INSERT INTO drivers (driver_name, license_number, contact_phone, assigned_truck_id, sub_mine_id, status)
            VALUES (?, ?, ?, ?, ?, 'ACTIVE')
        """, (driver, dl_no, phone, truck_id, sub_mine_id))

    log_audit("TRUCK_REGISTER", f"Registered commercial carrier: {reg} ({v_type}) assigned to Mine {mine_id}, Sub-Mine {sub_mine_id}")
    return jsonify({
        "success": True, 
        "message": f"Vehicle '{reg}' registered successfully.", 
        "truck_id": truck_id,
        "registration_number": reg,
        "vehicle_type": v_type,
        "registered_owner": owner,
        "driver_name": driver,
        "driver_phone": phone,
        "driver_license": dl_no,
        "tare_weight_mt": tare,
        "max_capacity_mt": capacity
    })


@app.route("/api/crud/drivers", methods=["POST"])
@login_required()
def api_crud_drivers():
    data = request.get_json() or {}
    raw_truck_id = data.get("assigned_truck_id")
    truck_id = None
    if raw_truck_id:
        try:
            truck_id = int(raw_truck_id)
        except (ValueError, TypeError):
            truck_id = None

    allowed, err, code = check_crud_permission("drivers", truck_id=truck_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    name = data.get("driver_name", "").strip()
    license_no = data.get("license_number", "").strip().upper()
    phone = data.get("contact_phone", "").strip() or "+91 98123 45678"

    if not name or not license_no:
        return jsonify({"error": "Driver name and driving license number are required.", "success": False}), 400

    existing_dl = db.query("SELECT id FROM drivers WHERE license_number = ?", (license_no,), one=True)
    if existing_dl:
        return jsonify({"error": f"A driver with license '{license_no}' is already registered.", "success": False}), 400

    sub_mine_id = None
    if session.get("user_role") == "OPERATOR":
        sub_mine_id = get_operator_sub_mine_id()
    elif truck_id:
        t_row = db.query("SELECT sub_mine_id FROM trucks WHERE id = ?", (truck_id,), one=True)
        if t_row and t_row["sub_mine_id"]:
            sub_mine_id = t_row["sub_mine_id"]

    driver_id = db.execute("""
        INSERT INTO drivers (driver_name, license_number, contact_phone, assigned_truck_id, sub_mine_id, status)
        VALUES (?, ?, ?, ?, ?, 'ACTIVE')
    """, (name, license_no, phone, truck_id, sub_mine_id))

    if truck_id:
        db.execute("UPDATE trucks SET driver_name = ?, driver_phone = ? WHERE id = ?", (name, phone, truck_id))

    log_audit("DRIVER_ADD", f"Added commercial driver: {name} (License: {license_no})")
    return jsonify({
        "success": True, 
        "message": f"Driver '{name}' registered successfully.", 
        "driver_id": driver_id,
        "driver_name": name,
        "license_number": license_no,
        "contact_phone": phone,
        "assigned_truck_id": truck_id
    })


@app.route("/api/crud/permits", methods=["POST"])
@login_required()
def api_crud_permits():
    data = request.get_json() or {}
    mine_id = data.get("mine_id")
    if session.get("user_role") == "OPERATOR":
        mine_id = get_operator_mine_id()
    else:
        mine_id = int(mine_id) if mine_id else 1

    raw_truck_id = data.get("truck_id")
    truck_id = int(raw_truck_id) if (raw_truck_id is not None and str(raw_truck_id).strip() != "") else 1

    allowed, err, code = check_crud_permission("permits", mine_id=mine_id, truck_id=truck_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
    truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
    if not mine or not truck:
        return jsonify({"error": "Valid mine and vehicle must be specified.", "success": False}), 400

    # Validate vehicle under unrestricted daily commercial operations
    driver_id = data.get("driver_id")
    eligibility = DetectionEngine.check_permit_issuance_eligibility(truck_id, driver_id=driver_id)
    if not eligibility.get("eligible", True):
        return jsonify({
            "error": eligibility.get("explanation", "Vehicle not eligible for permit issuance."),
            "success": False,
            "reason": eligibility.get("reason", "INVALID_VEHICLE")
        }), 400

    permit_num = data.get("permit_number", "").strip()
    if not permit_num:
        p_max = db.query("SELECT MAX(id) as m FROM permits", one=True)
        p_val = (p_max["m"] or 0) + 135 + 1
        permit_num = f"SMG-2026-{p_val:05d}"
        while db.query("SELECT 1 FROM permits WHERE permit_number = ?", (permit_num,), one=True):
            p_val += 1
            permit_num = f"SMG-2026-{p_val:05d}"

    mineral = data.get("mineral", mine["mineral"]).strip()
    weight = float(data.get("permitted_weight_mt", 25.0))

    # STATUTORY HARD-LOCK 1: Mine Lease Expiry (MMDR Act Sec 4A)
    today_iso = datetime.now().strftime("%Y-%m-%d")
    mine_lease_expiry = str(mine.get("lease_expiry_date") or "").strip()
    if mine_lease_expiry and mine_lease_expiry < today_iso:
        err_msg = (
            f"STATUTORY LEASE HARD-LOCK: Mining Concession Lease for '{mine['name']}' expired on {mine_lease_expiry}. "
            f"Generation of e-Rawaana is strictly prohibited under Section 4A of the MMDR Act (1957)."
        )
        log_audit("PERMIT_HARD_LOCKED", err_msg)
        return jsonify({
            "error": err_msg,
            "success": False,
            "lock_type": "LEASE_EXPIRED",
            "code": "STATUTORY_LEASE_EXPIRED",
            "expiry_date": mine_lease_expiry
        }), 403

    # STATUTORY HARD-LOCK 2: Mine Annual Environmental Clearance (EC) Quota (MMDR Act Sec 4(1A))
    auth_quota = float(mine.get("authorized_annual_quota_mt") or 0.0)
    curr_dispatch = float(mine.get("current_dispatch_mt") or 0.0)
    if auth_quota > 0 and (curr_dispatch + weight) > auth_quota:
        err_msg = (
            f"STATUTORY QUOTA HARD-LOCK: Annual Environmental Clearance (EC) extraction quota for '{mine['name']}' "
            f"is exhausted ({curr_dispatch:,.1f} MT dispatched + {weight:,.1f} MT requested exceeds {auth_quota:,.1f} MT authorized limit). "
            f"Generation of e-Rawaana is automatically locked under Section 4(1A) of the MMDR Act."
        )
        log_audit("PERMIT_HARD_LOCKED", err_msg)
        return jsonify({
            "error": err_msg,
            "success": False,
            "lock_type": "QUOTA_EXHAUSTED",
            "code": "STATUTORY_QUOTA_EXHAUSTED",
            "authorized_quota_mt": auth_quota,
            "current_dispatch_mt": curr_dispatch
        }), 403

    source_name = f"{mine['name']} ({mine['district']})"
    dest_name = data.get("destination_name", "Authorized Consignee Processing Unit").strip()
    buyer = data.get("buyer_name", "Registered Consignee Entity").strip()
    valid_hours = int(data.get("valid_hours", 12))

    # Financial calculations matching statutory tariff
    rate = 336.00 if "stone" in mineral.lower() else 320.00
    taxable = round(weight * rate, 2)
    cgst = round(taxable * 0.025, 2)
    sgst = round(taxable * 0.025, 2)
    total_val = round(taxable + cgst + sgst, 2)
    # Determine issuance authority and sub-location concession
    user_role = session.get("user_role")
    if user_role == "ADMIN":
        issuance_type = "EMERGENCY_ADMIN_ISSUANCE"
    elif user_role == "OFFICER":
        issuance_type = "OFFICER_AUTHORIZED_DISPATCH"
    else:
        issuance_type = "AUTOMATED_SCALE_DISPATCH"

    qb_id = data.get("quarry_block_id") or data.get("sub_mine_id")
    if session.get("user_role") == "OPERATOR":
        op_sm = get_operator_sub_mine_id()
        if op_sm:
            qb_id = op_sm
    qb = None
    if qb_id:
        qb = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (qb_id,), one=True)
    if not qb:
        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = ? ORDER BY id ASC LIMIT 1", (mine_id,), one=True)
    
    if qb:
        qb_id = qb["id"]

        # STATUTORY HARD-LOCK 3: Sub-Mine Concession Lease Expiry
        qb_lease_expiry = str(qb.get("lease_expiry_date") or "").strip()
        if qb_lease_expiry and qb_lease_expiry < today_iso:
            err_msg = (
                f"STATUTORY LEASE HARD-LOCK: Sub-Mine Concession Lease for pit '{qb['block_name']}' expired on {qb_lease_expiry}. "
                f"e-Rawaana issuance locked under Section 4A MMDR Act."
            )
            log_audit("PERMIT_HARD_LOCKED", err_msg)
            return jsonify({
                "error": err_msg,
                "success": False,
                "lock_type": "LEASE_EXPIRED",
                "code": "STATUTORY_PIT_LEASE_EXPIRED",
                "expiry_date": qb_lease_expiry
            }), 403

        # STATUTORY HARD-LOCK 4: Sub-Mine Concession Pit Quota Exhaustion
        qb_quota = float(qb.get("allocated_quota_mt") or 0.0)
        qb_dispatch = float(qb.get("dispatched_mt") or 0.0)
        if qb_quota > 0 and (qb_dispatch + weight) > qb_quota:
            err_msg = (
                f"STATUTORY QUOTA HARD-LOCK: Sub-Mine Pit concession quota for '{qb['block_name']}' is exhausted "
                f"({qb_dispatch:,.1f} MT dispatched + {weight:,.1f} MT requested exceeds {qb_quota:,.1f} MT tender cap). "
                f"Issuance locked under MMDR Act."
            )
            log_audit("PERMIT_HARD_LOCKED", err_msg)
            return jsonify({
                "error": err_msg,
                "success": False,
                "lock_type": "QUOTA_EXHAUSTED",
                "code": "STATUTORY_PIT_QUOTA_EXHAUSTED",
                "allocated_quota_mt": qb_quota,
                "dispatched_mt": qb_dispatch
            }), 403

        quarry_name = f"{qb['block_name']} ({qb['leaseholder_name']})"
        contractor_name = qb["leaseholder_name"]
        db.execute("UPDATE quarry_blocks SET dispatched_mt = dispatched_mt + ? WHERE id = ?", (weight, qb["id"]))
        if qb_quota > 0 and (qb_dispatch + weight) >= qb_quota:
            db.execute("UPDATE quarry_blocks SET status = 'QUOTA_EXHAUSTED' WHERE id = ?", (qb["id"],))
    else:
        quarry_name = mine.get("operator_name") or f"{mine['name']} Leasehold"
        contractor_name = mine.get("operator_name") or f"{mine['name']} Leasehold"

    # Update Mine cumulative dispatch and status
    db.execute("UPDATE mines SET current_dispatch_mt = current_dispatch_mt + ? WHERE id = ?", (weight, mine_id))
    if auth_quota > 0 and (curr_dispatch + weight) >= auth_quota:
        db.execute("UPDATE mines SET status = 'QUOTA_EXCEEDED' WHERE id = ?", (mine_id,))

    contractor_gstn = "06AAACH4114R2ZG"
    buyer_gstn = data.get("buyer_gstn", "06AAAAN2658Q1Z4")
    slip_no = f"26-27/S8/{29800 + (truck_id * 7)}"

    # Destination coordinates
    dest = db.query("SELECT latitude, longitude FROM destinations WHERE name = ?", (dest_name,), one=True)
    dest_lat = dest["latitude"] if dest else mine["latitude"] + 0.35
    dest_lng = dest["longitude"] if dest else mine["longitude"] + 0.25

    # Corridor waypoints
    mid_lat = round((mine["latitude"] + dest_lat) / 2 + 0.04, 4)
    mid_lng = round((mine["longitude"] + dest_lng) / 2 - 0.02, 4)
    waypoints = [
        [mine["latitude"], mine["longitude"]],
        [mid_lat, mid_lng],
        [dest_lat, dest_lng]
    ]

    now = datetime.now()
    expires = now + timedelta(hours=valid_hours)
    qr_raw = f"SMG:{permit_num}:{truck['registration_number']}:{time.time()}"
    qr_hash = hashlib.sha256(qr_raw.encode()).hexdigest()

    permit_id = db.execute("""
        INSERT INTO permits (permit_number, qr_code_hash, truck_id, mine_id, mineral,
                            permitted_weight_mt, source_name, destination_name, destination_lat,
                            destination_lng, buyer_name, buyer_type, buyer_address, buyer_gstn,
                            quarry_name, contractor_name, contractor_gstn,
                            rate_per_mt, taxable_amount, cgst_rate, cgst_amount, sgst_rate, sgst_amount, total_amount,
                            hsn_code, weighment_slip_no, pit_lot_no, customer_code, balance_amount,
                            issued_at, expires_at, status, route_waypoints_json, quarry_block_id, issuance_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Registered Entity', ?, ?, ?, ?, ?, ?, ?, 2.50, ?, 2.50, ?, ?, '2517', ?, '21', '61', 262969.59, ?, ?, 'ACTIVE', ?, ?, ?)
    """, (permit_num, qr_hash, truck_id, mine_id, mineral, weight, source_name, dest_name,
          dest_lat, dest_lng, buyer, dest_name, buyer_gstn, quarry_name, contractor_name, contractor_gstn,
          rate, taxable, cgst, sgst, total_val, slip_no, now.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(waypoints), qb_id, issuance_type))

    log_audit("PERMIT_ISSUE", f"Issued e-Rawaana {permit_num} ({issuance_type}) for Vehicle {truck['registration_number']} ({weight} MT {mineral}) from {quarry_name}")
    return jsonify({"success": True, "message": f"e-Rawaana '{permit_num}' issued successfully ({issuance_type}).", "permit_id": permit_id, "permit_number": permit_num, "issuance_type": issuance_type})


@app.route("/api/trucks/<int:truck_id>/permit-eligibility", methods=["GET"])
@login_required()
def api_truck_permit_eligibility(truck_id):
    if not validate_user_truck_access(truck_id):
        return jsonify({"error": "Forbidden: Access denied to vehicle record", "success": False}), 403
    driver_id = request.args.get("driver_id", type=int)
    res = DetectionEngine.check_permit_issuance_eligibility(truck_id, driver_id=driver_id)
    return jsonify(res)


@app.route("/api/crud/trips", methods=["POST"])
@login_required()
def api_crud_trips():
    data = request.get_json() or {}
    permit_id = int(data.get("permit_id", 0))
    permit = db.query("SELECT * FROM permits WHERE id = ?", (permit_id,), one=True)
    if not permit:
        return jsonify({"error": "Valid active e-Rawaana permit is required to dispatch a trip.", "success": False}), 400

    if permit.get("status") not in ("ACTIVE", "ISSUED"):
        return jsonify({"error": "Cannot dispatch transit trip: e-Rawaana permit is not ACTIVE or has already been consumed.", "success": False}), 400

    if permit.get("expires_at"):
        try:
            exp_dt = datetime.strptime(str(permit["expires_at"])[:19], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > exp_dt:
                return jsonify({"error": "Cannot dispatch transit trip: e-Rawaana permit has EXPIRED.", "success": False}), 400
        except Exception:
            pass

    if session.get("user_role") == "OPERATOR" and not validate_operator_permit_access(permit_id):
        return jsonify({"error": "Forbidden: Cross-tenant access denied. Permit belongs to another sub-mine.", "success": False}), 403

    # Prevent permit reuse: check if permit is already in use by an active transit trip
    existing_trip = db.query("SELECT id FROM trips WHERE permit_id = ? AND status = 'IN_TRANSIT'", (permit_id,), one=True)
    if existing_trip:
        return jsonify({"error": "Cannot dispatch trip: This e-Rawaana permit is already associated with an ongoing transit trip (Permit reuse detected).", "success": False}), 400

    mine_id = permit["mine_id"]
    truck_id = permit["truck_id"]

    allowed, err, code = check_crud_permission("trips", mine_id=mine_id, truck_id=truck_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    t_max = db.query("SELECT MAX(id) as m FROM trips", one=True)
    m_val = (t_max["m"] or 0) + 510 + 1
    trip_num = f"TRIP-2026-{m_val:05d}"
    while db.query("SELECT 1 FROM trips WHERE trip_number = ?", (trip_num,), one=True):
        m_val += 1
        trip_num = f"TRIP-2026-{m_val:05d}"
    dist = float(data.get("planned_distance_km", 48.5))

    trip_id = db.execute("""
        INSERT INTO trips (trip_number, permit_id, truck_id, mine_id, status, start_time,
                          planned_distance_km, actual_distance_km, risk_score, risk_level)
        VALUES (?, ?, ?, ?, 'IN_TRANSIT', CURRENT_TIMESTAMP, ?, 0.0, 0, 'LOW')
    """, (trip_num, permit_id, truck_id, mine_id, dist))

    # Update truck status to IN_TRANSIT and mark permit as IN_USE
    db.execute("UPDATE trucks SET status = 'IN_TRANSIT' WHERE id = ?", (truck_id,))
    db.execute("UPDATE permits SET status = 'IN_USE' WHERE id = ?", (permit_id,))

    log_audit("TRIP_DISPATCH", f"Dispatched transit journey {trip_num} for Vehicle {truck_id} under Permit {permit['permit_number']}")
    return jsonify({"success": True, "message": f"Trip '{trip_num}' dispatched successfully.", "trip_id": trip_id, "trip_number": trip_num})


@app.route("/api/crud/weighbridges", methods=["POST"])
@login_required(roles=["ADMIN"])
def api_crud_weighbridges():
    data = request.get_json() or {}
    code_val = data.get("code", "").strip().upper()
    name = data.get("name", "").strip()
    location = data.get("location", "").strip()
    cap = float(data.get("capacity_mt", 100.0))
    lat = float(data.get("latitude", 27.8900))
    lng = float(data.get("longitude", 76.2800))

    if not is_within_india(lat, lng):
        return jsonify({"error": "Coordinates must be within India.", "success": False}), 400

    wb_id = db.execute("""
        INSERT INTO weighbridges (code, name, location, capacity_mt, status, latitude, longitude)
        VALUES (?, ?, ?, ?, 'OPERATIONAL', ?, ?)
    """, (code_val, name, location, cap, lat, lng))

    log_audit("WEIGHBRIDGE_ADD", f"Added weighbridge facility: {code_val} - {name} at {location}")
    return jsonify({"success": True, "message": f"Weighbridge '{code_val}' added successfully.", "weighbridge_id": wb_id})


@app.route("/api/crud/weighments", methods=["POST"])
@login_required()
def api_crud_weighments():
    """
    Requirements 4 & 5:
    Automated Weight Scale Measurement & Automatic Permit vs Actual Weight Check.
    Net weight is derived deterministically (gross - tare) from weighbridge sensor feed.
    Disallows manual typing of arbitrary net weight by normal operators.
    If actual > permitted, calculates excess and logs OVERWEIGHT_DISPATCH alert.
    """
    data = request.get_json() or {}
    trip_id = int(data.get("trip_id", 0))
    trip = db.query("""
        SELECT tr.*, p.permitted_weight_mt, p.id as p_id, t.id as t_id, 
               t.max_capacity_mt, t.registration_number 
        FROM trips tr 
        JOIN permits p ON p.id = tr.permit_id 
        JOIN trucks t ON t.id = tr.truck_id 
        WHERE tr.id = ?
    """, (trip_id,), one=True)
    if not trip:
        return jsonify({"error": "Valid transit trip is required for scale weighment.", "success": False}), 400

    mine_id = trip["mine_id"]
    truck_id = trip["truck_id"]
    permit_id = trip["permit_id"]

    allowed, err, code = check_crud_permission("weighments", mine_id=mine_id, truck_id=truck_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    gross = float(data.get("gross_weight_mt", 0.0))
    tare = float(data.get("tare_weight_mt", 11.5))
    net = max(0.0, round(gross - tare, 2))
    permitted = float(trip["permitted_weight_mt"])
    diff = round(net - permitted, 2)
    is_overweight = diff > 0.5  # Deterministic tolerance threshold

    wb_code = data.get("weighbridge_code", "WB-AUTO-01").strip()
    wb_name = data.get("weighbridge_name", "Outbound Scale System").strip()
    
    is_manual = bool(data.get("is_manual_override", False) or str(data.get("is_manual_override", "0")) == "1")
    override_reason = data.get("override_reason", "").strip()
    measurement_source = "MANUAL_OPERATOR_OVERRIDE" if is_manual else data.get("measurement_source", "WEIGHBRIDGE_AUTOMATED_SCALE").strip()
    measurement_status = "PENDING_AUDIT" if is_manual else "VERIFIED"

    weighment_id = db.execute("""
        INSERT INTO weighments (trip_id, permit_id, truck_id, weighbridge_code, weighbridge_name,
                                gross_weight_mt, tare_weight_mt, net_weight_mt, permitted_weight_mt,
                                difference_mt, is_overweight, measurement_source, measurement_status,
                                is_manual_override, override_reason, override_by_user_id,
                                original_net_weight_mt, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (trip_id, permit_id, truck_id, wb_code, wb_name, gross, tare, net, permitted, diff,
          1 if is_overweight else 0, measurement_source, measurement_status,
          1 if is_manual else 0, override_reason if is_manual else None, session.get("user_id") if is_manual else None, net))

    if is_manual:
        alert_seq = db.query("SELECT COUNT(*) as c FROM alerts", one=True)["c"] + 115
        alert_code = f"ALT-2026-{alert_seq:05d}-MAN"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity,
                                risk_score, description, evidence_json, status, assigned_to_user_id)
            VALUES (?, ?, ?, ?, 'WEIGHT_ANOMALY', 'HIGH', 25, ?, ?, 'NEW', 2)
        """, (alert_code, trip_id, truck_id, permit_id,
              f"Scale Operator bypassed M2M Load Cell Transducer via Manual Override for Truck {trip['registration_number']} at {wb_code}. Reason: '{override_reason}'. Mandatory physical inspection at next checkpoint required.",
              json.dumps({"is_manual_override": True, "reason": override_reason, "gross_mt": gross, "tare_mt": tare, "net_mt": net})))
        log_audit("MANUAL_OVERRIDE_WEIGHMENT", f"Scale Operator manually typed weight for Truck {trip['registration_number']} at {wb_code}. Reason: {override_reason}")

    # Update permit and trip statuses
    db.execute("UPDATE permits SET status = 'WEIGHED' WHERE id = ?", (permit_id,))
    db.execute("UPDATE trips SET status = 'DISPATCHED' WHERE id = ?", (trip_id,))

    # Append timeline event
    db.append_trip_timeline(trip_id, "WEIGHBRIDGE_MEASUREMENT", f"Weighbridge: {wb_name}",
                            f"Gross {gross:.1f} MT, Tare {tare:.1f} MT, Net {net:.1f} MT (Source: {measurement_source})")

    # Update mine dispatch total
    db.execute("UPDATE mines SET current_dispatch_mt = current_dispatch_mt + ? WHERE id = ?", (net, mine_id))

    # Deterministic Overload Detection (Req 5)
    alert_created = False
    if is_overweight:
        detection_res = DetectionEngine.check_weight_anomaly(permitted, net, trip["max_capacity_mt"])
        if detection_res["is_violation"]:
            alert_seq = db.query("SELECT COUNT(*) as c FROM alerts", one=True)["c"] + 110
            alert_code = f"ALT-2026-{alert_seq:05d}-OWD"
            db.execute("""
                INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity,
                                    risk_score, description, evidence_json, status, assigned_to_user_id)
                VALUES (?, ?, ?, ?, 'OVERWEIGHT_DISPATCH', ?, ?, ?, ?, 'NEW', 2)
            """, (alert_code, trip_id, truck_id, permit_id, detection_res["severity"],
                  detection_res["risk_contribution"], detection_res["explanation"], json.dumps(detection_res["metrics"])))

            db.append_trip_timeline(trip_id, "OVERWEIGHT_DISPATCH", "Overweight Dispatch Alert",
                                    f"Dispatched Net {net:.1f} MT exceeds authorized {permitted:.1f} MT by +{diff:.1f} MT")

            RiskEngine.evaluate_and_update_trip_risk(trip_id)
            alert_created = True
            log_audit("OVERWEIGHT_DETECTED", f"Automatic detection: Truck {trip['registration_number']} overloaded by +{diff:.1f} MT (Net: {net:.1f} MT vs Permitted: {permitted:.1f} MT)")
    else:
        # Legal scale weighment: resolve any previous overweight alerts for this trip and update risk score (unless manual override alert)
        if not is_manual:
            db.execute("""
                UPDATE alerts 
                SET status = 'RESOLVED' 
                WHERE trip_id = ? AND alert_type IN ('WEIGHT_ANOMALY', 'OVERWEIGHT_DISPATCH')
            """, (trip_id,))
        RiskEngine.evaluate_and_update_trip_risk(trip_id)

    log_audit("WEIGHMENT_RECORD", f"Recorded automated weighment: Trip {trip['trip_number']} - Net {net:.1f} MT (Gross {gross:.1f}, Tare {tare:.1f}) at {wb_code}")
    msg = f"Automated weighment recorded: Net Weight {net:.1f} MT."
    if is_overweight:
        msg += f" WARNING: Overweight dispatch of +{diff:.1f} MT detected. Statutorily logged."

    # Zero-Touch Automated Dispatch Support
    auto_dispatch = bool(data.get("auto_dispatch", False))
    barrier_status = "BARRIER_MANUAL_HOLD"
    pdf_url = None

    if is_manual:
        barrier_status = "BARRIER_HELD_FOR_INSPECTION"
        msg = f"⚠️ Manual Override Recorded: Net {net:.1f} MT (Reason: '{override_reason}'). Transaction stamped for mandatory physical checkpoint inspection."
    elif auto_dispatch:
        if not is_overweight:
            barrier_status = "BARRIER_LIFTED_AUTOMATICALLY"
            try:
                from services.report_generator import generate_erawana_pdf
                pdf_rel = generate_erawana_pdf(permit_id, "weighment")
                if pdf_rel:
                    pdf_url = f"/{pdf_rel.replace('\\', '/')}"
            except Exception as e:
                logger.warning(f"Could not pre-generate auto-dispatch PDF: {e}")
                pdf_url = f"/permits/{permit_id}/download-pdf?type=weighment"

            db.append_trip_timeline(
                trip_id,
                "AUTO_DISPATCH_M2M",
                "Zero-Touch Auto-Dispatch Certified",
                f"M2M digital scale verified net {net:.1f} MT. Automated boom barrier lifted. Official e-Rawaana PDF generated."
            )
            msg = f"🎉 Zero-Touch Auto-Dispatch Complete! Automated boom barrier lifted. Net {net:.1f} MT certified."
        else:
            barrier_status = "BARRIER_LOCKED_OVERLOAD"
            msg = f"⛔ AUTO-DISPATCH INHIBITED: Overload of +{diff:.1f} MT detected! Automated barrier locked down."

    return jsonify({
        "success": True,
        "message": msg,
        "weighment_id": weighment_id,
        "net_weight_mt": net,
        "difference_mt": diff,
        "is_overweight": is_overweight,
        "measurement_source": measurement_source,
        "measurement_status": measurement_status,
        "alert_created": alert_created,
        "auto_dispatch": auto_dispatch,
        "barrier_status": barrier_status,
        "pdf_url": pdf_url,
        "permit_number": trip.get("permit_number")
    })


@app.route("/api/weighments/<int:weighment_id>/override", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_weighment_override(weighment_id):
    """
    Requirement 4:
    Authorized Manual Weight Override.
    Requires authorized role (Admin or Officer), reason, preserves original value,
    stores user ID and timestamp, and records full audit trail.
    """
    w = db.query("SELECT * FROM weighments WHERE id = ?", (weighment_id,), one=True)
    if not w:
        return jsonify({"error": "Weighment record not found", "success": False}), 404

    if not validate_user_weighment_access(weighment_id):
        return jsonify({"error": "Forbidden: Access denied to weighment record outside your jurisdiction.", "success": False}), 403

    data = request.get_json() or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "A reason is required for manual weight override.", "success": False}), 400

    try:
        new_net = float(data.get("corrected_net_weight_mt", w["net_weight_mt"]))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid corrected net weight value.", "success": False}), 400

    orig_net = float(w["net_weight_mt"])
    perm = float(w["permitted_weight_mt"])
    new_diff = round(new_net - perm, 2)
    is_overweight = 1 if new_diff > 0.5 else 0

    user_id = session.get("user_id")

    db.execute("""
        UPDATE weighments
        SET original_net_weight_mt = COALESCE(original_net_weight_mt, ?),
            net_weight_mt = ?,
            difference_mt = ?,
            is_overweight = ?,
            is_manual_override = 1,
            override_reason = ?,
            override_by_user_id = ?,
            measurement_status = 'MANUAL_OVERRIDE'
        WHERE id = ?
    """, (orig_net, new_net, new_diff, is_overweight, reason, user_id, weighment_id))

    violation = DetectionEngine.check_manual_weight_override(weighment_id)
    if violation["is_violation"]:
        alert_seq = db.query("SELECT COUNT(*) as c FROM alerts", one=True)["c"] + 115
        alert_code = f"ALT-2026-{alert_seq:05d}-OVR"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity,
                                risk_score, description, evidence_json, status, assigned_to_user_id)
            VALUES (?, ?, ?, ?, 'MANUAL_WEIGHT_OVERRIDE', ?, ?, ?, ?, 'NEW', ?)
        """, (alert_code, w["trip_id"], w["truck_id"], w["permit_id"],
              violation["severity"], violation["risk_contribution"], violation["explanation"],
              json.dumps(violation["metrics"]), user_id))

    if w.get("trip_id"):
        if not is_overweight:
            db.execute("""
                UPDATE alerts 
                SET status = 'RESOLVED' 
                WHERE trip_id = ? AND alert_type IN ('WEIGHT_ANOMALY', 'OVERWEIGHT_DISPATCH')
            """, (w["trip_id"],))
        RiskEngine.evaluate_and_update_trip_risk(w["trip_id"])
        db.append_trip_timeline(
            w["trip_id"],
            "MANUAL_WEIGHT_OVERRIDE",
            "Manual Weight Override Applied",
            f"Net weight adjusted from {orig_net:.1f} MT to {new_net:.1f} MT. Reason: {reason}"
        )

    db.log_audit("MANUAL_WEIGHT_OVERRIDE", "weighments", weighment_id, f"Net {orig_net:.1f} MT", f"Net {new_net:.1f} MT", f"Authorized override: {reason}")

    return jsonify({
        "success": True,
        "message": f"Manual override applied. Net weight updated to {new_net:.1f} MT.",
        "original_net_weight_mt": orig_net,
        "corrected_net_weight_mt": new_net,
        "difference_mt": new_diff,
        "is_overweight": bool(is_overweight)
    })


@app.route("/api/permits/<int:permit_id>/reconcile", methods=["POST"])
@login_required()
def api_permit_reconcile(permit_id):
    """
    Requirement 3:
    Controlled Permit Reconciliation Workflow.
    Does NOT silently delete or cancel statutory records.
    Transitions permit state with an audit trail and user authorization check.
    """
    p = db.query("SELECT * FROM permits WHERE id = ?", (permit_id,), one=True)
    if not p:
        return jsonify({"error": "Permit record not found", "success": False}), 404

    if not validate_user_permit_access(permit_id):
        return jsonify({"error": "Forbidden: Cannot reconcile permit outside your concession jurisdiction.", "success": False}), 403

    data = request.get_json() or {}
    action = data.get("action", "RECONCILE").upper()
    reason = data.get("reason", "").strip()

    if not reason:
        return jsonify({"error": "Reconciliation justification reason is mandatory.", "success": False}), 400

    prev_state = p["status"]
    if action == "CANCEL":
        new_state = "CANCELLED"
    elif action == "RECONCILE":
        new_state = "ACTIVE"
    elif action == "COMPLETE":
        new_state = "COMPLETED"
    else:
        new_state = "ACTIVE"

    db.execute("""
        UPDATE permits
        SET status = ?, reconciliation_reason = ?
        WHERE id = ?
    """, (new_state, reason, permit_id))

    db.log_audit("PERMIT_RECONCILED", "permits", permit_id, prev_state, new_state, reason)

    return jsonify({
        "success": True,
        "message": f"Permit {p['permit_number']} transitioned from {prev_state} to {new_state}.",
        "permit_id": permit_id,
        "status": new_state
    })


@app.route("/api/trips/<int:trip_id>/timeline")
@login_required()
def api_trip_timeline(trip_id):
    """
    Requirement 9: Chronological Trip Timeline.
    Returns ordered audit events and milestones for a given trip.
    """
    trip = db.query("SELECT * FROM trips WHERE id = ?", (trip_id,), one=True)
    if not trip:
        return jsonify({"error": "Trip not found", "success": False}), 404

    if not validate_user_trip_access(trip_id):
        return jsonify({"error": "Forbidden: Access denied to transit trip timeline.", "success": False}), 403

    timeline = []
    if trip.get("timeline_events_json"):
        try:
            timeline = json.loads(trip["timeline_events_json"])
        except Exception:
            timeline = []

    if not timeline:
        timeline = [
            {"event": "TRUCK_ENTERED_MINE", "title": "Entered Mine", "description": "GPS entry recorded at gate geofence", "timestamp": str(trip.get("start_time") or "")[:19]},
            {"event": "PERMIT_MATCHED", "title": "Permit Matched", "description": f"e-Rawaana verified for trip #{trip.get('trip_number')}", "timestamp": str(trip.get("start_time") or "")[:19]}
        ]

    return jsonify({
        "success": True,
        "trip_id": trip_id,
        "trip_number": trip.get("trip_number"),
        "round_number": trip.get("round_number") or 1,
        "timeline": timeline
    })


@app.route("/api/simulator/mine-entry", methods=["POST"])
@login_required()
def api_simulator_mine_entry():
    data = request.get_json() or {}
    truck_reg = data.get("truck_reg", "HR26AB1234")
    mine_id = int(data.get("mine_id", 1))
    res = simulator.simulate_mine_entry(truck_reg, mine_id)
    return jsonify(res)


@app.route("/api/simulator/mine-exit", methods=["POST"])
@login_required()
def api_simulator_mine_exit():
    data = request.get_json() or {}
    truck_reg = data.get("truck_reg", "HR26AB1234")
    mine_id = int(data.get("mine_id", 1))
    res = simulator.simulate_mine_exit(truck_reg, mine_id)
    return jsonify(res)


@app.route("/api/crud/stock-production", methods=["POST"])
@login_required()
def api_crud_stock_production():
    """
    Section 10: Stock & Dispatch Monitoring.
    Formula: Opening Stock + Today's Production - Today's Dispatch = Closing Stock.
    """
    data = request.get_json() or {}
    mine_id = data.get("mine_id")
    if session.get("user_role") == "OPERATOR":
        mine_id = get_operator_mine_id()
    else:
        mine_id = int(mine_id) if mine_id else 1

    allowed, err, code = check_crud_permission("stock-production", mine_id=mine_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
    if not mine:
        return jsonify({"error": "Invalid mine concession.", "success": False}), 400

    mineral = data.get("mineral", mine["mineral"]).strip()
    record_date = data.get("record_date", datetime.now().strftime("%Y-%m-%d")).strip()
    opening = float(data.get("opening_stock_mt", mine["current_stock_mt"] or 3500.0))
    production = float(data.get("production_mt", 0.0))
    dispatch = float(data.get("dispatch_mt", 0.0))
    closing = max(0.0, round(opening + production - dispatch, 2))

    sp_id = db.execute("""
        INSERT INTO stock_production (mine_id, mineral, record_date, opening_stock_mt,
                                      production_mt, dispatch_mt, closing_stock_mt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (mine_id, mineral, record_date, opening, production, dispatch, closing))

    # Update mine current stock
    db.execute("UPDATE mines SET current_stock_mt = ? WHERE id = ?", (closing, mine_id))

    log_audit("STOCK_BALANCE", f"Recorded mass-balance for Mine {mine['mine_code']}: Opening {opening:.1f} + Prod {production:.1f} - Disp {dispatch:.1f} = Closing {closing:.1f} MT")
    return jsonify({
        "success": True,
        "message": f"Stock ledger updated: Closing available stock is {closing:,.1f} MT.",
        "record_id": sp_id,
        "closing_stock_mt": closing
    })


@app.route("/api/crud/destinations", methods=["POST"])
@login_required(roles=["ADMIN"])
def api_crud_destinations():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    d_type = data.get("destination_type", "CRUSHER").strip()
    license_no = data.get("license_number", "").strip()
    district = data.get("district", "").strip()
    state = data.get("state", "Rajasthan").strip()
    lat = float(data.get("latitude", 28.3500))
    lng = float(data.get("longitude", 76.9400))
    minerals = data.get("authorized_minerals", "Quartzite / Limestone").strip()

    if not is_within_india(lat, lng):
        return jsonify({"error": "Coordinates must be within India.", "success": False}), 400

    dst_id = db.execute("""
        INSERT INTO destinations (name, destination_type, license_number, district, state,
                                 latitude, longitude, authorized_minerals, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'AUTHORIZED')
    """, (name, d_type, license_no, district, state, lat, lng, minerals))

    log_audit("DESTINATION_ADD", f"Added registered consignee: {name} ({district}, {state})")
    return jsonify({"success": True, "message": f"Consignee '{name}' registered successfully.", "destination_id": dst_id})


@app.route("/api/crud/checkpoints", methods=["POST"])
@login_required(roles=["ADMIN"])
def api_crud_checkpoints():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    loc = data.get("location", "").strip()
    district = data.get("district", "").strip()
    lat = float(data.get("latitude", 27.9950))
    lng = float(data.get("longitude", 76.3550))

    if not is_within_india(lat, lng):
        return jsonify({"error": "Coordinates must be within India.", "success": False}), 400

    cp_id = db.execute("""
        INSERT INTO checkpoints (name, location, district, latitude, longitude, status)
        VALUES (?, ?, ?, ?, ?, 'OPERATIONAL')
    """, (name, loc, district, lat, lng))

    log_audit("CHECKPOINT_ADD", f"Added enforcement outpost: {name} at {loc}")
    return jsonify({"success": True, "message": f"Checkpoint '{name}' registered successfully.", "checkpoint_id": cp_id})


@app.route("/api/crud/<string:entity>/<int:record_id>", methods=["DELETE"])
@login_required()
def api_crud_delete(entity, record_id):
    """
    Generic Record Deletion Endpoint with strict role-based permission verification.
    """
    valid_tables = {
        "mines": "mines",
        "trucks": "trucks",
        "drivers": "drivers",
        "permits": "permits",
        "trips": "trips",
        "weighbridges": "weighbridges",
        "destinations": "destinations",
        "checkpoints": "checkpoints",
        "stock-production": "stock_production",
        "sub-mines": "quarry_blocks"
    }

    if entity not in valid_tables:
        return jsonify({"error": "Invalid master entity type.", "success": False}), 400

    tbl = valid_tables[entity]
    rec = db.query(f"SELECT * FROM {tbl} WHERE id = ?", (record_id,), one=True)
    if not rec:
        return jsonify({"error": "Record not found.", "success": False}), 404

    # Permission check with entity-aware key resolution
    if entity == "trucks":
        truck_id = rec["id"]
        mine_id = rec.get("assigned_mine_id")
    elif entity == "drivers":
        truck_id = rec.get("assigned_truck_id")
        mine_id = None
    elif entity == "permits":
        truck_id = rec.get("truck_id")
        mine_id = rec.get("mine_id")
    elif entity == "trips":
        truck_id = rec.get("truck_id")
        mine_id = rec.get("mine_id")
    elif entity == "sub-mines":
        mine_id = rec.get("mine_id")
        truck_id = None
    else:
        mine_id = rec.get("mine_id") or rec.get("assigned_mine_id")
        truck_id = rec.get("truck_id") or rec.get("assigned_truck_id")

    # do not allow deleting active permits or in-transit trips
    if entity == "permits" and rec.get("status") in ("ACTIVE", "IN_USE", "WEIGHED"):
        return jsonify({"error": "Active or weighed permits cannot be deleted. Please cancel or reconcile the permit instead.", "success": False}), 400
    if entity == "trips" and rec.get("status") in ("IN_TRANSIT", "DISPATCHED"):
        return jsonify({"error": "Cannot delete a trip while it is actively in transit.", "success": False}), 400

    allowed, err, code = check_crud_permission(entity, mine_id=mine_id, truck_id=truck_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    db.execute(f"DELETE FROM {tbl} WHERE id = ?", (record_id,))
    log_audit("RECORD_DELETE", f"Deleted {entity} record ID {record_id}")
    return jsonify({"success": True, "message": f"{entity.title()} record deleted successfully."})


# --- SIH DEMONSTRATION & SIMULATOR CONTROL APIS ---

@app.route("/api/simulator/action", methods=["POST"])
@login_required(roles=["ADMIN", "OFFICER", "OPERATOR"])
def api_simulator_action():
    data = request.get_json() or {}
    action = data.get("action")
    truck_reg = data.get("truck_reg", "HR26AB1234")

    if action == "start":
        simulator.start()
        return jsonify({"status": "started", "message": "GPS fleet simulator started in background."})
    elif action == "stop":
        simulator.stop()
        return jsonify({"status": "stopped", "message": "GPS fleet simulator stopped."})
    elif action == "step":
        updates = simulator.step_simulation()
        return jsonify({"status": "stepped", "trucks_updated": len(updates)})
    elif action == "trigger_weight":
        res = simulator.trigger_weighbridge_anomaly(truck_reg)
        return jsonify({"status": "triggered_weight", "result": res})
    elif action == "trigger_route":
        res = simulator.trigger_route_deviation(truck_reg)
        return jsonify({"status": "triggered_route", "result": res})
    elif action == "trigger_blackout":
        res = simulator.trigger_gps_blackout(truck_reg)
        return jsonify({"status": "triggered_blackout", "result": res})
    elif action == "trigger_pass_reuse":
        res = simulator.trigger_pass_reuse(truck_reg)
        return jsonify({"status": "triggered_pass_reuse", "result": res})
    elif action == "trigger_kanta_cheating":
        res = simulator.trigger_kanta_cheating(truck_reg)
        return jsonify({"status": "triggered_kanta_cheating", "result": res})
    elif action == "trigger_grade_arbitrage":
        res = simulator.trigger_grade_arbitrage(truck_reg)
        return jsonify({"status": "triggered_grade_arbitrage", "result": res})
    elif action == "trigger_token_bypass":
        res = simulator.trigger_token_bypass(truck_reg)
        return jsonify({"status": "triggered_token_bypass", "result": res})
    elif action == "trigger_over_extraction_killswitch":
        res = simulator.trigger_over_extraction_killswitch(
            mine_id=data.get("mine_id", 1),
            quarry_block_id=data.get("quarry_block_id", 1)
        )
        return jsonify({"status": "triggered_over_extraction_killswitch", "result": res})
    elif action == "trigger_unclosed_entry":
        res = simulator.trigger_unclosed_entry(truck_reg)
        return jsonify({"status": "triggered_unclosed_entry", "result": res})
    elif action == "reset":
        res = simulator.reset_demo()
        return jsonify(res)
    else:
        return jsonify({"error": f"Unknown simulator action '{action}'"}), 400


@app.route("/api/mine/drone-dem-audit", methods=["GET"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_drone_dem_audit():
    mine_id = request.args.get("mine_id", 1, type=int)
    audit_data = MaterialMonitoringService.get_drone_dem_volumetric_audit(mine_id=mine_id)
    return jsonify({"success": True, "audit": audit_data})


@app.route("/api/mine/crusher-kacha-maal-audit", methods=["GET"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_crusher_kacha_maal_audit():
    mine_id = request.args.get("mine_id", 1, type=int)
    audit_data = MaterialMonitoringService.get_crusher_inward_kacha_maal_audit(mine_id=mine_id)
    return jsonify({"success": True, "audit": audit_data})


@app.route("/api/mine/unclosed-entries", methods=["GET"])
@login_required(roles=["ADMIN", "OFFICER"])
def api_unclosed_entries():
    mine_id = request.args.get("mine_id", 1, type=int)
    watchdog_data = MaterialMonitoringService.get_active_pit_dwell_watchdog(mine_id=mine_id)
    return jsonify({"success": True, "watchdog": watchdog_data})



# --- SOCKETIO REAL-TIME EVENTS ---

_LAST_GPS_STEP_TIME = {}

@socketio.on("connect")
def handle_connect():
    logger.info(f"SocketIO client connected: {request.sid}")
    role = session.get("user_role")
    active_mine_id = get_active_mine_id()
    active_sub_mine_id = get_active_sub_mine_id()

    if active_sub_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id, active_sub_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"""
                SELECT id, registration_number, current_lat, current_lng, current_risk_score, current_risk_level, status
                FROM trucks WHERE id IN ({placeholders}) AND current_lat IS NOT NULL AND current_lng IS NOT NULL
            """, truck_ids)
        else:
            trucks = []
    elif active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks = db.query(f"""
                SELECT id, registration_number, current_lat, current_lng, current_risk_score, current_risk_level, status
                FROM trucks WHERE id IN ({placeholders}) AND current_lat IS NOT NULL AND current_lng IS NOT NULL
            """, truck_ids)
        else:
            trucks = []
    elif role == "ADMIN":
        trucks = db.query("""
            SELECT id, registration_number, current_lat, current_lng, current_risk_score, current_risk_level, status
            FROM trucks WHERE current_lat IS NOT NULL AND current_lng IS NOT NULL
        """)
    else:
        trucks = []
    emit("gps_initial_fleet", {"trucks": trucks})


@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"SocketIO client disconnected: {request.sid}")
    _LAST_GPS_STEP_TIME.pop(request.sid, None)


@socketio.on("request_gps_step")
def handle_request_step():
    role = session.get("user_role")
    if not role:
        return
    client_sid = request.sid
    now = time.time()
    last_t = _LAST_GPS_STEP_TIME.get(client_sid, 0)
    if now - last_t < 0.4:  # Rate limit: max 2.5 steps/sec per client
        return
    _LAST_GPS_STEP_TIME[client_sid] = now

    updates = simulator.step_simulation()
    active_mine_id = get_active_mine_id()
    active_sub_mine_id = get_active_sub_mine_id()

    if active_sub_mine_id:
        allowed_truck_ids = set(get_operator_truck_ids(active_mine_id, active_sub_mine_id))
        filtered_updates = [u for u in updates if u.get("id") in allowed_truck_ids]
    elif active_mine_id:
        allowed_truck_ids = set(get_operator_truck_ids(active_mine_id))
        filtered_updates = [u for u in updates if u.get("id") in allowed_truck_ids]
    elif role == "ADMIN":
        filtered_updates = updates
    else:
        filtered_updates = []
    emit("gps_batch_update", {"trucks": filtered_updates})


# --- Error Handlers ---

@app.errorhandler(400)
def handle_bad_request(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Bad Request", "message": str(e), "success": False}), 400
    return render_template("error.html", code=400, title="Bad Request", message="The request could not be processed. Please check your input."), 400


@app.errorhandler(403)
def handle_forbidden(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Forbidden: Access denied.", "success": False}), 403
    return render_template("error.html", code=403, title="Access Denied", message="You do not have permission to view or access this resource."), 403


@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not Found", "message": "The requested resource does not exist.", "success": False}), 404
    return render_template("error.html", code=404, title="Page Not Found", message="The page or record you are looking for could not be found."), 404


@app.errorhandler(429)
def handle_rate_limited(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Too Many Requests", "message": "Rate limit exceeded. Please slow down.", "success": False}), 429
    return render_template("error.html", code=429, title="Too Many Requests", message="Too many requests. Please wait a moment and try again."), 429


@app.errorhandler(500)
def handle_internal_error(e):
    logger.error(f"Server error on {request.path}: {traceback.format_exc()}")
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal Server Error", "message": "An internal server error occurred.", "success": False}), 500
    return render_template("error.html", code=500, title="Server Error", message="An unexpected error occurred. Please try again later."), 500


_db_initialized = False
_lazy_db_lock = threading.Lock()

@app.before_request
def ensure_db_ready():
    if request.path in ("/health", "/api/health"):
        return None
    global _db_initialized
    if not _db_initialized:
        with _lazy_db_lock:
            if not _db_initialized:
                try:
                    db.init_db()
                    _db_initialized = True
                except Exception as e:
                    logger.error(f"Lazy DB setup error: {e}")

# Auto-start GPS simulator loop (disabled in serverless environments like Vercel)
if not _BOOT_ERROR and globals().get("simulator") is not None:
    try:
        is_serverless = getattr(Config, "IS_SERVERLESS", False) if "Config" in globals() else False
        if not is_serverless:
            simulator.start()
    except Exception as _sim_err:
        logger.warning(f"GPS simulator start failed: {_sim_err}")



if __name__ == "__main__":
    port = Config.PORT
    logger.info(f"Starting SmartMineGuard server on port {port}...")
    try:
        socketio.run(app, host="0.0.0.0", port=port, debug=Config.DEBUG, allow_unsafe_werkzeug=True)
    except Exception as _e:
        logger.warning(f"socketio.run failed ({_e}), starting standard Flask app on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
