"""
SmartMineGuard - Flask Web Application & Real-Time Monitoring Server
Mining & Mineral Transport Monitoring System
STRICTLY PURE SOFTWARE — NO AI / NO MACHINE LEARNING / NO NODE.JS.
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
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, 
    session, jsonify, send_file, flash, abort, Response
)

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
            get_enriched_permit_data
        )
    except Exception as _e:
        generate_evidence_pdf = None
        generate_erawana_pdf = None
        generate_seizure_notice_pdf = None
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
            body = f"SmartMineGuard Runtime Exception:\n\n{tb}".encode("utf-8")
            start_response("200 OK", [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body)))
            ])
            return [body]

app.wsgi_app = ErrorLoggingMiddleware(app.wsgi_app)


@app.before_request
def check_boot_error_on_request():
    if _BOOT_ERROR:
        return Response(f"SmartMineGuard Boot Error:\n\n{_BOOT_ERROR}\n\nSys.path:\n{sys.path}", mimetype="text/plain", status=200)


socketio = SocketIO()
try:
    if not os.getenv("VERCEL") and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")
    if 'simulator' in locals():
        simulator.set_socketio(socketio)
except Exception as _e:
    logger.warning(f"SocketIO initialization deferred: {_e}")





# ============================================================
# AUTHENTICATION & ACCESS CONTROL
# ============================================================

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
    mine = db.query("SELECT id FROM mines WHERE operator_name = ? OR name LIKE ? OR ? LIKE '%' || operator_name || '%'", 
                    (user_dept, f"%{user_dept}%", user_dept), one=True)
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
    """Returns list of truck IDs strictly associated with the operator's sub-mine/contractor (or mine)."""
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
    truck_ids = [r["truck_id"] for r in rows if r["truck_id"] is not None]
    if mine_id == 1:
        for tid in [1, 3, 5]:
            if tid not in truck_ids:
                truck_ids.append(tid)
    return truck_ids


def validate_operator_truck_access(truck_id):
    """Returns True if the current user can access this truck, False otherwise."""
    if session.get("user_role") != "OPERATOR":
        return True
    allowed_trucks = get_operator_truck_ids()
    return truck_id in allowed_trucks


def validate_operator_permit_access(permit_id):
    """Returns True if the current user can access this permit, False otherwise."""
    if session.get("user_role") != "OPERATOR":
        return True
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


def validate_operator_trip_access(trip_id):
    """Returns True if the current user can access this trip, False otherwise."""
    if session.get("user_role") != "OPERATOR":
        return True
    allowed_trucks = get_operator_truck_ids()
    tr = db.query("SELECT truck_id FROM trips WHERE id = ?", (trip_id,), one=True)
    if not tr:
        return False
    return tr["truck_id"] in allowed_trucks


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
    """Injects user session, active mine filter, and real-time alert badge count into all templates."""
    pending_alerts_count = 0
    role = session.get("user_role")
    active_mine_id = get_active_mine_id()
    active_mine = None
    all_mines = []
    try:
        if role == "OFFICER":
            active_mine_id = get_officer_mine_id()
            active_mine = db.query("SELECT id, mine_code, name, district, state, mineral FROM mines WHERE id = ?", (active_mine_id,), one=True)
            all_mines = [active_mine] if active_mine else []
        elif role == "OPERATOR":
            active_mine_id = get_operator_mine_id()
            active_mine = db.query("SELECT id, mine_code, name, district, state, mineral FROM mines WHERE id = ?", (active_mine_id,), one=True)
            all_mines = [active_mine] if active_mine else []
        else:
            all_mines = db.query("SELECT id, mine_code, name, district, state, mineral FROM mines ORDER BY id ASC")
            if active_mine_id:
                active_mine = next((m for m in all_mines if m["id"] == active_mine_id), None)
                if not active_mine:
                    active_mine = db.query("SELECT id, mine_code, name, district, state, mineral FROM mines WHERE id = ?", (active_mine_id,), one=True)
    except Exception:
        pass

    if role in ("ADMIN", "OFFICER"):
        try:
            if active_mine_id:
                row = db.query("""
                    SELECT COUNT(*) as count FROM alerts a
                    LEFT JOIN trips tr ON tr.id = a.trip_id
                    LEFT JOIN permits p ON p.id = a.permit_id
                    WHERE a.status IN ('NEW', 'UNDER_REVIEW')
                      AND (tr.mine_id = ? OR p.mine_id = ?)
                """, (active_mine_id, active_mine_id), one=True)
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
            "assigned_mine_id": active_mine_id
        } if "user_id" in session else None,
        "pending_alerts_count": pending_alerts_count,
        "active_mine_id": active_mine_id,
        "active_mine": active_mine,
        "all_mines": all_mines,
        "current_year": datetime.now().year
    }


@app.route("/set-mine-filter", methods=["GET", "POST"])
@login_required()
def set_mine_filter():
    """
    Sets or clears the persistent mine filter across the whole website for ADMIN ONLY.
    Field Officers and Operators are strictly locked to their assigned concession and cannot switch mines.
    """
    role = session.get("user_role")
    if role != "ADMIN":
        flash("Access Denied: Field Officers are restricted to their assigned mine concession and cannot switch mines.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    mine_id = request.values.get("mine_id")
    if not mine_id or str(mine_id).lower() in ("all", "0", "", "none"):
        session.pop("selected_mine_id", None)
        flash("Displaying statewide grid for all mining leaseholds.", "info")
    else:
        try:
            m_id = int(mine_id)
            mine = db.query("SELECT * FROM mines WHERE id = ?", (m_id,), one=True)
            if mine:
                session["selected_mine_id"] = m_id
                flash(f"Global site filter applied: {mine['name']} ({mine['district']}).", "success")
            else:
                session.pop("selected_mine_id", None)
        except Exception:
            session.pop("selected_mine_id", None)

    next_url = request.values.get("next") or request.referrer or url_for("dashboard")
    return redirect(next_url)


# ============================================================
# PAGE ROUTES (HTML + JINJA2)
# ============================================================

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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = db.query("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
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
            return redirect(next_url or url_for("dashboard"))
        else:
            flash("Invalid credentials. Please verify your officer username and password.", "error")

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
    if role == "ADMIN":
        if "mine_id" in request.args:
            m_param = request.args.get("mine_id")
            if m_param and m_param.isdigit() and int(m_param) > 0:
                session["selected_mine_id"] = int(m_param)
            else:
                session.pop("selected_mine_id", None)
    else:
        session.pop("selected_mine_id", None)  # Strictly disallowed for OFFICER/OPERATOR

    selected_mine_id = get_active_mine_id()

    if role == "ADMIN":
        if selected_mine_id:
            total_mines = 1
            truck_ids = get_operator_truck_ids(selected_mine_id)
            if truck_ids:
                placeholders = ",".join("?" for _ in truck_ids)
                total_trucks = len(truck_ids)
                active_trucks = db.query(f"SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT' AND id IN ({placeholders})", truck_ids, one=True)["c"]
            else:
                total_trucks = 0
                active_trucks = 0
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
        else:
            total_mines = db.query("SELECT COUNT(*) as c FROM mines", one=True)["c"]
            total_trucks = db.query("SELECT COUNT(*) as c FROM trucks", one=True)["c"]
            active_trucks = db.query("SELECT COUNT(*) as c FROM trucks WHERE status = 'IN_TRANSIT'", one=True)["c"]
            active_permits = db.query("SELECT COUNT(*) as c FROM permits WHERE status = 'ACTIVE'", one=True)["c"]
            total_trips = db.query("SELECT COUNT(*) as c FROM trips", one=True)["c"]
            pending_alerts = db.query("SELECT COUNT(*) as c FROM alerts WHERE status = 'NEW'", one=True)["c"]
            critical_cases = db.query("SELECT COUNT(*) as c FROM alerts WHERE severity = 'CRITICAL' AND status != 'DISMISSED'", one=True)["c"]

        mines = db.query("SELECT * FROM mines ORDER BY id ASC")
        users = db.query("SELECT id, username, full_name, role, department, badge_number, is_active FROM users ORDER BY id ASC")
        audit_logs = db.query("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 8")

        # Material & Operational Dispatch Monitoring Data
        daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=selected_mine_id)
        dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=selected_mine_id)
        mismatch_check = DetectionEngine.check_production_dispatch_reconciliation(mine_id=selected_mine_id)
        stock_recon = MaterialMonitoringService.get_stock_reconciliation(mine_id=selected_mine_id)
        mine_wise_summary = MaterialMonitoringService.get_mine_wise_material_summary()
        truck_material_ledger = MaterialMonitoringService.get_truck_wise_material_ledger(mine_id=selected_mine_id)
        top_rankings = MaterialMonitoringService.get_top_material_rankings(mine_id=selected_mine_id)
        mineral_summary = MaterialMonitoringService.get_mineral_wise_summary(mine_id=selected_mine_id)

        # Supervisory Vigilance Audit: High-risk detections and officer actions
        officer_audits = db.query("""
            SELECT a.*, t.registration_number, p.permit_number,
                   u_handled.full_name as officer_name, u_handled.badge_number as officer_badge
            FROM alerts a
            LEFT JOIN trucks t ON t.id = a.truck_id
            LEFT JOIN permits p ON p.id = a.permit_id
            LEFT JOIN users u_handled ON u_handled.id = a.handled_by_user_id
            WHERE a.escalated_to_admin = 1 OR a.handled_by_user_id IS NOT NULL OR a.severity IN ('CRITICAL', 'HIGH')
            ORDER BY a.id DESC
            LIMIT 6
        """)

        all_quarry_blocks = db.query("""
            SELECT qb.*, m.name as mine_name, m.district as mine_district
            FROM quarry_blocks qb
            LEFT JOIN mines m ON m.id = qb.mine_id
            ORDER BY qb.mine_id ASC, qb.id ASC
        """)
        all_trucks = db.query("SELECT id, registration_number, vehicle_type, max_capacity_mt FROM trucks ORDER BY registration_number ASC")

        total_sub_mines = len(all_quarry_blocks)
        escalated_cases = db.query("SELECT COUNT(*) as c FROM alerts WHERE escalated_to_admin = 1 OR severity = 'CRITICAL'", one=True)["c"]
        high_risk_trucks_count = db.query("SELECT COUNT(*) as c FROM trucks WHERE current_risk_score >= 50", one=True)["c"]
        investigations_count = db.query("SELECT COUNT(*) as c FROM investigations WHERE status != 'CLOSED'", one=True)["c"]
        officer_actions_count = db.query("SELECT COUNT(*) as c FROM alerts WHERE handled_by_user_id IS NOT NULL", one=True)["c"]

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
            all_trucks=all_trucks
        )

    elif role == "OFFICER":
        officer_mine_id = get_officer_mine_id()
        selected_mine_id = officer_mine_id  # Enforce strict single-mine isolation

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

        # High-risk trucks strictly restricted to officer's mine
        high_risk_trucks = db.query("""
            SELECT t.*, p.permit_number, p.mineral, p.source_name, p.destination_name
            FROM trucks t
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
            WHERE (t.assigned_mine_id = ? OR p.mine_id = ?)
              AND (t.current_risk_score >= 50 OR t.status = 'IN_TRANSIT')
            ORDER BY t.current_risk_score DESC LIMIT 6
        """, (officer_mine_id, officer_mine_id))

        # Recent alerts strictly restricted to officer's mine
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

        # Investigations strictly restricted to officer's mine
        investigations = db.query("""
            SELECT inv.*, t.registration_number 
            FROM investigations inv
            LEFT JOIN trucks t ON t.id = inv.truck_id
            LEFT JOIN permits p ON p.truck_id = t.id
            LEFT JOIN trips tr ON tr.id = inv.trip_id
            WHERE p.mine_id = ? OR tr.mine_id = ? OR t.assigned_mine_id = ?
            ORDER BY inv.id DESC LIMIT 4
        """, (officer_mine_id, officer_mine_id, officer_mine_id))

        mines = db.query("SELECT id, name, mineral, district, state FROM mines WHERE id = ?", (officer_mine_id,))
        daily_summary = MaterialMonitoringService.get_daily_dispatch_summary(mine_id=officer_mine_id)
        dispatch_control = MaterialMonitoringService.get_dispatch_control_planning(mine_id=officer_mine_id)
        mismatch_check = DetectionEngine.check_production_dispatch_reconciliation(mine_id=officer_mine_id)
        quantity_anomalies = MaterialMonitoringService.get_quantity_anomalies(mine_id=officer_mine_id)
        truck_material_ledger = MaterialMonitoringService.get_truck_wise_material_ledger(mine_id=officer_mine_id)

        # Mine Sub-Locations / Leaseholder Businessmen Concessions strictly for officer's mine
        quarry_blocks = db.query("""
            SELECT qb.*, m.name as mine_name, m.district as mine_district
            FROM quarry_blocks qb
            LEFT JOIN mines m ON m.id = qb.mine_id
            WHERE qb.mine_id = ?
            ORDER BY qb.id ASC
        """, (officer_mine_id,))

        for qb in quarry_blocks:
            qb_id = qb["id"]
            qb["active_trucks_count"] = db.query("SELECT COUNT(*) as c FROM trucks WHERE sub_mine_id = ?", (qb_id,), one=True)["c"]
            qb["trips_today"] = db.query("SELECT COUNT(*) as c FROM trips WHERE truck_id IN (SELECT id FROM trucks WHERE sub_mine_id = ?)", (qb_id,), one=True)["c"]
            qb["alerts_count"] = db.query("""
                SELECT COUNT(*) as c FROM alerts a
                LEFT JOIN trucks t ON t.id = a.truck_id
                WHERE t.sub_mine_id = ? AND a.status IN ('NEW', 'UNDER_REVIEW')
            """, (qb_id,), one=True)["c"]
            qb["high_risk_count"] = db.query("SELECT COUNT(*) as c FROM trucks WHERE sub_mine_id = ? AND current_risk_score >= 50", (qb_id,), one=True)["c"]
            qb["critical_count"] = db.query("SELECT COUNT(*) as c FROM trucks WHERE sub_mine_id = ? AND current_risk_score >= 80", (qb_id,), one=True)["c"]

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
    if active_mine_id:
        mines = db.query("SELECT * FROM mines WHERE id = ?", (active_mine_id,))
        geofences = db.query("SELECT * FROM geofences")
        truck_ids = get_operator_truck_ids(active_mine_id)
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
    else:
        mines = db.query("SELECT * FROM mines")
        geofences = db.query("SELECT * FROM geofences")
        trucks = db.query("""
            SELECT t.*, p.permit_number, p.mineral, p.permitted_weight_mt, 
                   p.source_name, p.destination_name, tr.id as trip_id
            FROM trucks t
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status = 'ACTIVE'
            LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS')
            ORDER BY t.current_risk_score DESC
        """)
    return render_template("map.html", mines=mines, geofences=geofences, trucks=trucks)


# ============================================================
# GPS & ANTI-TAMPER TELEMETRY SURVEILLANCE
# ============================================================

@app.route("/gps-telemetry")
@login_required()
def gps_telemetry():
    """
    GPS Anti-Tamper & Telemetry Intelligence Center.
    Tracks network blindspots vs deliberate GPS Jammers ('gamers'),
    hardware wire cuts, and prohibited riverbed incursions.
    """
    active_mine_id = get_active_mine_id()
    
    if active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks_list = db.query(f"""
                SELECT t.*, m.name as assigned_mine_name, m.district as mine_district,
                       p.permit_number, p.mineral, tr.trip_number, tr.id as active_trip_id
                FROM trucks t
                LEFT JOIN mines m ON m.id = t.assigned_mine_id
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
                   p.permit_number, p.mineral, tr.trip_number, tr.id as active_trip_id
            FROM trucks t
            LEFT JOIN mines m ON m.id = t.assigned_mine_id
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
        geofences=geofences
    )


@app.route("/api/gps/trucks", methods=["GET"])
@login_required()
def api_gps_trucks():
    """Returns real-time fleet telemetry JSON for live map and dynamic polling."""
    active_mine_id = get_active_mine_id()
    if active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            trucks_data = db.query(f"SELECT * FROM trucks WHERE id IN ({placeholders})", truck_ids)
        else:
            trucks_data = []
    else:
        trucks_data = db.query("SELECT * FROM trucks")
    return jsonify({"success": True, "trucks": trucks_data})


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

    if not validate_operator_permit_access(permit_id):
        abort(403)

    rel_path = generate_erawana_pdf(permit_id, doc_type=doc_type)
    if not rel_path:
        flash("Could not generate e-Rawana PDF for this permit.", "error")
        return redirect(url_for("permits"))

    abs_path = os.path.join(Config.BASE_DIR, rel_path)
    if not os.path.exists(abs_path):
        flash("Generated PDF artifact not found on server.", "error")
        return redirect(url_for("permits"))

    permit = db.query("SELECT permit_number FROM permits WHERE id = ?", (permit_id,), one=True)
    p_clean = (permit["permit_number"] if permit else f"permit_{permit_id}").replace("/", "_").replace(" ", "_")
    download_name = f"{doc_type}_{p_clean}.pdf"

    return send_file(abs_path, as_attachment=True, download_name=download_name, mimetype="application/pdf")


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
    active_mine_id = get_active_mine_id()

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
    if active_mine_id:
        sql += " AND (tr.mine_id = ? OR p.mine_id = ?)"
        params.extend([active_mine_id, active_mine_id])

    # Role & View separation:
    if view_mode == "vigilance":
        # Admin Vigilance & Supervisory Audit View:
        # Prioritize alerts handled/overridden by officers, critical anomalies, and escalated fraud
        sql += " AND (a.escalated_to_admin = 1 OR a.handled_by_user_id IS NOT NULL OR a.severity IN ('CRITICAL', 'HIGH') OR a.admin_review_status != 'NONE')"
    elif view_mode == "operational":
        # Field Officer Operational Triage View:
        # Active detections awaiting field inspection/verification
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

    # Vigilance and operational count badges for tabs
    vigilance_pending_count = db.query("""
        SELECT COUNT(*) as c FROM alerts 
        WHERE admin_review_status = 'PENDING_VIGILANCE_REVIEW' 
           OR (escalated_to_admin = 1 AND admin_review_status = 'NONE')
           OR (handled_by_user_id IS NOT NULL AND severity IN ('CRITICAL', 'HIGH') AND admin_review_status = 'NONE')
    """, one=True)["c"]

    operational_pending_count = db.query("""
        SELECT COUNT(*) as c FROM alerts WHERE status = 'NEW'
    """, one=True)["c"]

    total_alerts_count = db.query("SELECT COUNT(*) as c FROM alerts", one=True)["c"]

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
    active_mine_id = get_active_mine_id()
    if active_mine_id:
        inv_list = db.query("""
            SELECT inv.*, a.alert_code, a.alert_type, t.registration_number, p.permit_number, u.full_name as lead_officer
            FROM investigations inv
            LEFT JOIN alerts a ON a.id = inv.alert_id
            LEFT JOIN trucks t ON t.id = inv.truck_id
            LEFT JOIN permits p ON p.id = inv.permit_id
            LEFT JOIN trips tr ON tr.id = inv.trip_id
            LEFT JOIN users u ON u.id = inv.lead_officer_id
            WHERE tr.mine_id = ? OR p.mine_id = ?
            ORDER BY inv.id DESC
        """, (active_mine_id, active_mine_id))
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
    active_mine_id = get_active_mine_id()
    if active_mine_id:
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
    active_mine_id = get_active_mine_id()
    if active_mine_id:
        truck_ids = get_operator_truck_ids(active_mine_id)
        if truck_ids:
            placeholders = ",".join("?" for _ in truck_ids)
            inv_list = db.query(f"""
                SELECT inv.*, t.registration_number, p.permit_number, u.full_name as officer_name
                FROM investigations inv
                LEFT JOIN trucks t ON t.id = inv.truck_id
                LEFT JOIN permits p ON p.id = inv.permit_id
                LEFT JOIN users u ON u.id = inv.lead_officer_id
                WHERE inv.truck_id IN ({placeholders})
                ORDER BY inv.id DESC
            """, truck_ids)
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


# ============================================================
# ADMINISTRATOR USER & ROLE MANAGEMENT
# ============================================================

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
        new_status = 0 if user["is_active"] else 1
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
        status_text = "activated" if new_status else "deactivated"
        log_audit("USER_STATUS_CHANGE", f"Admin {status_text} account: {user['username']}")
        flash(f"User '{user['username']}' {status_text}.", "info")
    return redirect(url_for("admin_users"))


# ============================================================
# MASTER DATA MANAGEMENT & OPERATOR OPERATIONAL VIEWS
# ============================================================

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
@login_required()
def download_mine_seizure_notice(mine_id):
    """
    Downloads official Section 21 MMDR Statutory Seizure Notice PDF
    triggered when a mine hits 100% of its annual environmental concession quota.
    """
    mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
    if not mine:
        flash("Mine record not found.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    pdf_rel_path = generate_seizure_notice_pdf(mine_id)
    if not pdf_rel_path:
        flash("Unable to build seizure order document.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    abs_path = os.path.join(app.root_path, pdf_rel_path.replace("/", os.sep))
    if not os.path.exists(abs_path):
        flash("Seizure document file not found.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    filename = f"MMDR_Section21_Seizure_Order_{mine['mine_code']}.pdf"
    return send_file(abs_path, as_attachment=True, download_name=filename)


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


# ============================================================
# PUBLIC REST API ENDPOINTS (UNAUTHENTICATED & WHITELISTED)
# ============================================================

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
        "active_trucks": active_trucks,
        "active_permits": active_permits,
        "weighbridges": weighbridges_count,
        "weighbridge_status": wb_status,
        "today_dispatch_mt": f"{today_dispatch_mt:.1f} MT"
    })


# ============================================================
# AUTHENTICATED REST API ENDPOINTS
# ============================================================

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
    if not validate_operator_truck_access(truck_id):
        return jsonify({"error": "Forbidden: Access denied to another operator's vehicle record", "success": False}), 403

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
    if not validate_operator_truck_access(truck_id):
        return jsonify({"error": "Forbidden: Access denied to another operator's vehicle record", "success": False}), 403

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

        log_audit("VIGILANCE_AUDIT_CONFIRMED",
                  f"Admin {admin_name} confirmed field clearance on Alert {alert['alert_code']} (Vehicle {alert['registration_number']}). Remarks: '{notes}'")
        return jsonify({"success": True, "status": "CONFIRMED_BY_ADMIN", "message": "Officer action successfully audited and confirmed."})

    elif decision == "FLAG_INQUIRY":
        # Elevated to Formal Anti-Corruption Inquiry
        case_num = db.query("SELECT COUNT(*) as c FROM investigations", one=True)["c"] + 42
        case_id = f"SMG-2026-{case_num:05d}"
        
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
            "investigation_id": inv_id,
            "case_id": case_id,
            "pdf_path": pdf_path,
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
    inv = db.query("SELECT * FROM investigations WHERE case_id = ?", (case_id,), one=True)
    if not inv:
        abort(404)

    pdf_rel_path = generate_evidence_pdf(inv["id"], case_id)
    full_path = Config.BASE_DIR / pdf_rel_path
    
    if not full_path.exists():
        abort(404)

    return send_file(
        str(full_path),
        as_attachment=True,
        download_name=f"Evidence_Dossier_{case_id}.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# MASTER DATA CRUD API ENDPOINTS (STRICT ROLE-BASED ACCESS CONTROL)
# ============================================================

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
        quarry_name = f"{qb['block_name']} ({qb['leaseholder_name']})"
        contractor_name = qb["leaseholder_name"]
        db.execute("UPDATE quarry_blocks SET dispatched_mt = dispatched_mt + ? WHERE id = ?", (weight, qb["id"]))
    else:
        quarry_name = mine.get("operator_name") or f"{mine['name']} Leasehold"
        contractor_name = mine.get("operator_name") or f"{mine['name']} Leasehold"

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

    data = request.get_json() or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "A valid statutory reason is mandatory for manual weight override.", "success": False}), 400

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

    role = session.get("user_role")
    if role == "OPERATOR":
        mine_id = get_operator_mine_id()
        if p["mine_id"] != mine_id:
            return jsonify({"error": "Forbidden: Cannot reconcile permit for another concession.", "success": False}), 403

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

    # Permission check
    mine_id = rec.get("mine_id") or rec.get("assigned_mine_id")
    truck_id = rec.get("truck_id") or rec.get("assigned_truck_id")
    allowed, err, code = check_crud_permission(entity, mine_id=mine_id, truck_id=truck_id)
    if not allowed:
        return jsonify({"error": err, "success": False}), code

    db.execute(f"DELETE FROM {tbl} WHERE id = ?", (record_id,))
    log_audit("RECORD_DELETE", f"Deleted {entity} record ID {record_id}")
    return jsonify({"success": True, "message": f"{entity.title()} record deleted successfully."})


# ============================================================
# SIH DEMONSTRATION & SIMULATOR CONTROL APIS
# ============================================================

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



# ============================================================
# SOCKETIO REAL-TIME EVENTS
# ============================================================

@socketio.on("connect")
def handle_connect():
    logger.info(f"SocketIO client connected: {request.sid}")
    # Send initial fleet locations to connected client
    trucks = db.query("""
        SELECT id, registration_number, current_lat, current_lng, current_risk_score, current_risk_level, status
        FROM trucks WHERE current_lat IS NOT NULL AND current_lng IS NOT NULL
    """)
    emit("gps_initial_fleet", {"trucks": trucks})


@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"SocketIO client disconnected: {request.sid}")


@socketio.on("request_gps_step")
def handle_request_step():
    updates = simulator.step_simulation()
    emit("gps_batch_update", {"trucks": updates})


_db_initialized = False

@app.before_request
def ensure_db_ready():
    global _db_initialized
    if not _db_initialized:
        try:
            db.init_db()
            _db_initialized = True
        except Exception as e:
            logger.error(f"Lazy DB setup error: {e}")

# Auto-start GPS simulator loop (disabled in serverless environments like Vercel)
if not Config.IS_SERVERLESS:
    simulator.start()



if __name__ == "__main__":
    port = Config.PORT
    logger.info(f"Starting SmartMineGuard server on port {port}...")
    try:
        socketio.run(app, host="0.0.0.0", port=port, debug=Config.DEBUG, allow_unsafe_werkzeug=True)
    except Exception as _e:
        logger.warning(f"socketio.run failed ({_e}), starting standard Flask app on port {port}...")
        app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
