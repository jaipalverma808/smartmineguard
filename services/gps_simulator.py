"""
SmartMineGuard - Real-time Python GPS Simulator & Telemetry Engine
Simulates multi-truck fleets and controlled SIH hackathon demonstration scenarios.
Broadcasts telemetry via Flask-SocketIO.
"""
import time
import threading
import json
import logging
import random
import uuid
from datetime import datetime, timedelta
from services.db import db, haversine_distance_km
from services.detection import DetectionEngine
from services.risk_engine import RiskEngine

logger = logging.getLogger("smartmineguard.gps_simulator")


def is_within_india(lat, lng):
    """
    Validates that a GPS coordinate is strictly located within Indian territory.
    Mainland India bounding box: Lat 8.0° to 35.5°N, Lng 68.0° to 97.0°E.
    Additional northern and western boundary clamping prevents drift into China, Tibet, Pakistan, or Nepal.
    """
    if not (8.0 <= lat <= 35.5 and 68.0 <= lng <= 97.0):
        return False
    # Himalayan/Tibet/China northern limit: beyond lat 31.0, longitude shouldn't exceed 78.5
    if lat > 31.0 and lng > 78.5:
        return False
    # Nepal/China northern boundary: between lng 80.0 and 88.5, lat shouldn't exceed 30.0
    if 80.0 <= lng <= 88.5 and lat > 30.0:
        return False
    # Bhutan/China northern boundary: between lng 88.5 and 92.0, lat shouldn't exceed 28.0
    if 88.5 <= lng <= 92.0 and lat > 28.0:
        return False
    # Pakistan western border clamping: between lat 23.5 and 32.5, longitude must be >= 74.5
    if 23.5 <= lat <= 32.5 and lng < 74.5:
        return False
    return True



class GPSSimulator:
    def __init__(self, socketio=None):
        self.socketio = socketio
        self.is_running = False
        self._thread = None
        self._step_counter = 0

        # Pre-calculated waypoints for HR26AB1234 (Alwar Quarry to Bhiwadi via NH-48)
        # Normal Route
        self.normal_route = [
            (27.5624, 76.6121),  # Alwar Quarry Gate
            (27.6100, 76.6000),
            (27.6800, 76.5600),
            (27.7500, 76.5100),  # NH-48 junction
            (27.8500, 76.5800),
            (27.9800, 76.6800),
            (28.0900, 76.7700),
            (28.2100, 76.8600)   # Bhiwadi Crushing Zone
        ]

        # Deviated Unpermitted Route for HR26AB1234 (veers West toward Sabi Riverbed)
        self.deviated_route = [
            (27.7500, 76.5100),
            (27.7900, 76.4700),
            (27.8300, 76.4400),
            (27.8520, 76.4530)   # Sabi Riverbed edge (Blackout point)
        ]

        # Pre-defined Indian Corridors for Fleet Trucks
        self.fleet_corridors = {
            "RJ14GA5521": [  # Kotputli to Neemrana via NH-48
                (27.7052, 76.2023), (27.7800, 76.2600), (27.8600, 76.3200), (27.9850, 76.3850)
            ],
            "OD02BA8812": [  # Alwar Quarry to Manesar via NH-48
                (27.5624, 76.6121), (27.7200, 76.5400), (27.8900, 76.7200), (28.1200, 76.8300), (28.3500, 76.9400)
            ],
            "HR38EF9012": [  # Rewari Khol Pit toward Jaipur via NH-48
                (28.1884, 76.6210), (27.8000, 76.3000), (27.4500, 76.1000), (27.2000, 75.9000), (26.9124, 75.7873)
            ],
            "UP16BT4055": [  # Kotputli to Shahpura corridor
                (27.7052, 76.2023), (27.6000, 76.1000), (27.5000, 76.0200), (27.3900, 75.9600)
            ],
            "RJ02CB7811": [  # Tijara to Alwar Bypass
                (27.9300, 76.8500), (27.8200, 76.7400), (27.7100, 76.6100), (27.6300, 76.5200)
            ]
        }

        self.current_step_hr26 = 0
        self.is_hr26_deviating = True
        self.is_hr26_blackout = False

    def set_socketio(self, socketio):
        self.socketio = socketio

    def start(self):
        """Start simulator background loop."""
        if not self.is_running:
            self.is_running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            logger.info("GPS Simulator service started.")

    def stop(self):
        """Stop simulator."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=2)
            logger.info("GPS Simulator service stopped.")

    def _run_loop(self):
        while self.is_running:
            try:
                self.step_simulation()
            except Exception as e:
                logger.error(f"Simulator step error: {e}")
            time.sleep(10.0)

    def step_simulation(self):
        """Execute a single simulation cycle for all active fleet trucks."""
        self._step_counter += 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Fetch active transit trucks
        trucks = db.query("""
            SELECT t.id, t.registration_number, t.current_lat, t.current_lng, 
                   t.current_risk_score, t.current_risk_level, t.status,
                   t.assigned_mine_id, t.is_inside_mine, t.completed_rounds_today,
                   t.current_round_number,
                   p.id as permit_id, p.permit_number, p.permitted_weight_mt,
                   p.route_waypoints_json, tr.id as trip_id
            FROM trucks t
            LEFT JOIN permits p ON p.truck_id = t.id AND p.status IN ('ACTIVE', 'TRUCK_ARRIVED', 'LOADING', 'WEIGHED', 'DISPATCHED')
            LEFT JOIN trips tr ON tr.truck_id = t.id AND tr.status IN ('IN_TRANSIT', 'SUSPICIOUS', 'LOADING', 'DISPATCHED')
            WHERE t.status IN ('IN_TRANSIT', 'SUSPICIOUS', 'LOADING', 'IDLE')
        """)

        updates = []

        for truck in trucks:
            t_id = truck["id"]
            reg = truck["registration_number"]
            trip_id = truck["trip_id"]

            # Scenario 1: Target Demo Vehicle HR26AB1234
            if reg == "HR26AB1234":
                if self.is_hr26_blackout:
                    # Do not broadcast new location to simulate signal loss!
                    continue

                if self.is_hr26_deviating:
                    idx = min(self.current_step_hr26, len(self.deviated_route) - 1)
                    new_lat, new_lng = self.deviated_route[idx]
                    speed = 46.0
                    heading = 310.0
                    if idx < len(self.deviated_route) - 1:
                        self.current_step_hr26 += 1
                    else:
                        # Reached sensitive riverbed point; trigger blackout after arrival
                        self.is_hr26_blackout = True
                else:
                    idx = min(self.current_step_hr26, len(self.normal_route) - 1)
                    new_lat, new_lng = self.normal_route[idx]
                    speed = 52.0
                    heading = 35.0
                    self.current_step_hr26 = (self.current_step_hr26 + 1) % len(self.normal_route)

            # Scenario 2: Other Fleet Vehicles Following Realistic Indian Corridors
            elif reg in self.fleet_corridors:
                pts = self.fleet_corridors[reg]
                n_pts = len(pts)
                # Cycle smoothly through corridor points
                step_idx = (self._step_counter // 2) % (2 * (n_pts - 1))
                if step_idx >= n_pts - 1:
                    step_idx = 2 * (n_pts - 1) - step_idx
                p1 = pts[step_idx]
                p2 = pts[min(step_idx + 1, n_pts - 1)]
                progress = ((self._step_counter % 2) / 2.0)
                new_lat = p1[0] + (p2[0] - p1[0]) * progress
                new_lng = p1[1] + (p2[1] - p1[1]) * progress
                speed = round(random.uniform(42.0, 56.0), 1)
                heading = 45.0

            # Default movement for other trucks: realistic oscillation within Indian mining region
            else:
                lat = truck["current_lat"] or 27.6000
                lng = truck["current_lng"] or 76.5000
                # Bounded oscillation around base point to prevent drift
                base_lat = 27.6500 + ((t_id * 7) % 50) * 0.01
                base_lng = 76.4500 + ((t_id * 11) % 40) * 0.01
                offset_lat = 0.015 * (random.uniform(-1, 1))
                offset_lng = 0.02 * (random.uniform(-1, 1))
                new_lat = round(base_lat + offset_lat, 5)
                new_lng = round(base_lng + offset_lng, 5)
                speed = round(random.uniform(35.0, 52.0), 1)
                heading = round(random.uniform(0.0, 360.0), 1)

            # Strict India Geofence Validation: never allow coordinates outside India!
            if not is_within_india(new_lat, new_lng):
                new_lat, new_lng = 27.5624, 76.6121  # Fallback to Alwar Mining Zone

            # Record in DB
            db.execute("""
                UPDATE trucks 
                SET current_lat = ?, current_lng = ?, last_gps_time = ?
                WHERE id = ?
            """, (new_lat, new_lng, now_str, t_id))

            if trip_id:
                db.execute("""
                    INSERT INTO gps_positions (trip_id, truck_id, latitude, longitude, speed_kmh, heading)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (trip_id, t_id, new_lat, new_lng, speed, heading))

            # Geofence Mine Entry / Exit automated detection
            try:
                assigned_mid = truck.get("assigned_mine_id") or 1
                mine = db.query("SELECT * FROM mines WHERE id = ?", (assigned_mid,), one=True)
                if mine and mine.get("latitude") and mine.get("longitude"):
                    dist_km = haversine_distance_km(new_lat, new_lng, mine["latitude"], mine["longitude"])
                    geofence_km = float(mine.get("geofence_radius_m") or 1200.0) / 1000.0
                    is_inside = bool(truck.get("is_inside_mine"))
                    if not is_inside and dist_km <= geofence_km:
                        self.handle_mine_entry(truck, mine, new_lat, new_lng)
                    elif is_inside and dist_km > (geofence_km + 0.3):
                        self.handle_mine_exit(truck, mine, new_lat, new_lng)
            except Exception as geo_err:
                logger.warning(f"Geofence processing exception for truck {reg}: {geo_err}")

            # Automated Destination Arrival Detection & Permit Auto-Burn (Idea 1: Pass Recycling Trap)
            try:
                p_id = truck.get("permit_id")
                if p_id:
                    p_curr = db.query("SELECT * FROM permits WHERE id = ? AND status IN ('ACTIVE', 'IN_TRANSIT', 'DISPATCHED')", (p_id,), one=True)
                    if p_curr and p_curr.get("destination_lat") and p_curr.get("destination_lng"):
                        d_dest_km = haversine_distance_km(new_lat, new_lng, p_curr["destination_lat"], p_curr["destination_lng"])
                        if d_dest_km <= 0.8:
                            db.execute("UPDATE permits SET status = 'CONSUMED', consumed_at = ? WHERE id = ?", (now_str, p_curr["id"]))
                            if trip_id:
                                db.execute("UPDATE trips SET status = 'DELIVERED', end_time = ? WHERE id = ?", (now_str, trip_id))
                                db.append_trip_timeline(trip_id, "DELIVERY_COMPLETED", f"Arrived at {p_curr['destination_name']}", f"Permit {p_curr['permit_number']} consumed upon arrival")
                            if self.socketio:
                                self.socketio.emit("permit_consumed", {
                                    "permit_id": p_curr["id"],
                                    "permit_number": p_curr["permit_number"],
                                    "destination": p_curr["destination_name"],
                                    "consumed_at": now_str
                                })
            except Exception as dest_err:
                logger.warning(f"Destination geofence exception for truck {reg}: {dest_err}")

            # Automated Inter-State Border Crossing Check & Targeted Intercept Beacon (Idea 5)
            try:
                istp_res = DetectionEngine.check_interstate_transit_authorization(t_id, new_lat, new_lng)
                if istp_res["is_violation"]:
                    existing_border_alt = db.query("""
                        SELECT id FROM alerts 
                        WHERE truck_id = ? AND alert_type = 'UNAUTHORIZED_INTERSTATE_TRANSIT' 
                        AND status IN ('NEW', 'ACKNOWLEDGED')
                    """, (t_id,), one=True)
                    if not existing_border_alt:
                        self._create_alert_from_violation(istp_res, trip_id, t_id, truck.get("permit_id"), reg)
                    if self.socketio:
                        self.socketio.emit("targeted_intercept_beacon", {
                            "truck_id": t_id,
                            "registration_number": reg,
                            "violation": "UNAUTHORIZED_INTERSTATE_TRANSIT",
                            "checkpoint": "Bawal Toll Monitoring Checkpoint",
                            "latitude": new_lat,
                            "longitude": new_lng,
                            "eta_minutes": 4,
                            "timestamp": now_str
                        })
            except Exception as istp_err:
                logger.warning(f"Interstate transit check exception for truck {reg}: {istp_err}")

            payload = {
                "truck_id": t_id,
                "registration_number": reg,
                "latitude": round(new_lat, 5),
                "longitude": round(new_lng, 5),
                "speed_kmh": speed,
                "heading": heading,
                "risk_score": truck["current_risk_score"],
                "risk_level": truck["current_risk_level"],
                "status": truck["status"],
                "permit_number": truck["permit_number"] or "N/A",
                "timestamp": now_str
            }
            updates.append(payload)

        # Broadcast via Flask-SocketIO if available
        if self.socketio and updates:
            self.socketio.emit("gps_batch_update", {"trucks": updates, "timestamp": now_str})

        return updates

    def handle_mine_entry(self, truck, mine, lat=None, lng=None):
        """
        Requirements 1, 2, 3:
        GPS-Based Mine Entry Detection & Smart e-Rawaana Reconciliation.
        Authoritatively records:
        - Truck registration number
        - Mine ID
        - Entry timestamp
        - GPS lat/lng
        - Active permit associated with the truck
        - Current trip status
        - Round number
        Creates event: TRUCK ENTERED MINE
        Auto-matches valid unused permit and transitions to ARRIVED / DISPATCH CYCLE STARTED.
        If permit is missing/expired/used/mismatched, immediately creates alert.
        """
        t_id = truck["id"]
        m_id = mine["id"]
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        reg = truck["registration_number"]

        t_curr = db.query("SELECT is_inside_mine, completed_rounds_today, current_round_number FROM trucks WHERE id = ?", (t_id,), one=True)
        if t_curr and t_curr.get("is_inside_mine"):
            return

        round_num = int(t_curr.get("current_round_number") or (int(t_curr.get("completed_rounds_today") or 0) + 1))

        db.execute("""
            UPDATE trucks 
            SET is_inside_mine = 1, current_mine_id = ?, last_mine_entry = ?, status = 'LOADING'
            WHERE id = ?
        """, (m_id, now_str, t_id))

        permit = db.query("""
            SELECT * FROM permits 
            WHERE truck_id = ? AND status IN ('ACTIVE', 'ISSUED')
            ORDER BY id DESC LIMIT 1
        """, (t_id,), one=True)

        trip = db.query("""
            SELECT * FROM trips 
            WHERE truck_id = ? AND status IN ('IN_TRANSIT', 'LOADING', 'DISPATCHED', 'SUSPICIOUS')
            ORDER BY id DESC LIMIT 1
        """, (t_id,), one=True)

        if not trip:
            t_seq = db.query("SELECT COUNT(*) as c FROM trips", one=True)["c"] + 520
            trip_num = f"TRIP-2026-{t_seq:05d}"
            p_id = permit["id"] if permit else None
            trip_id = db.execute("""
                INSERT INTO trips (trip_number, permit_id, truck_id, mine_id, status, start_time,
                                  round_number, planned_distance_km, actual_distance_km, risk_score, risk_level)
                VALUES (?, ?, ?, ?, 'LOADING', CURRENT_TIMESTAMP, ?, 45.0, 0.0, 0, 'LOW')
            """, (trip_num, p_id, t_id, m_id, round_num))
            trip = db.query("SELECT * FROM trips WHERE id = ?", (trip_id,), one=True)
        else:
            db.execute("UPDATE trips SET status = 'LOADING', round_number = ? WHERE id = ?", (round_num, trip["id"]))

        geo_coords = f"({lat:.4f}, {lng:.4f})" if (lat and lng) else "Geofence boundary"
        db.append_trip_timeline(trip["id"], "TRUCK_ENTERED_MINE", f"Entered Mine {mine['name']}", f"GPS Entry recorded at {geo_coords}")

        if permit:
            is_valid = True
            invalid_reason = None
            if permit.get("expires_at") and str(permit["expires_at"]) < now_str:
                is_valid = False
                invalid_reason = f"Permit {permit['permit_number']} expired on {permit['expires_at']}"
            elif permit.get("mine_id") and permit["mine_id"] != m_id:
                is_valid = False
                invalid_reason = f"Permit {permit['permit_number']} assigned to Mine #{permit['mine_id']}, but truck entered Mine #{m_id}"

            if is_valid:
                db.execute("UPDATE permits SET status = 'TRUCK_ARRIVED' WHERE id = ?", (permit["id"],))
                db.append_trip_timeline(trip["id"], "PERMIT_MATCHED", f"Permit matched: {permit['permit_number']}", f"Permitted {permit['permitted_weight_mt']} MT {permit['mineral']}")
                db.log_audit("TRUCK_ENTERED_MINE", "trucks", t_id, "OUTSIDE_MINE", "INSIDE_MINE", f"Truck {reg} entered Mine {mine['name']} with active permit {permit['permit_number']}")
            else:
                db.execute("UPDATE permits SET status = 'RECONCILIATION_REQUIRED', reconciliation_reason = ? WHERE id = ?", (invalid_reason, permit["id"]))
                v = DetectionEngine.check_unauthorized_mine_entry(t_id, m_id, permit)
                if v["is_violation"]:
                    self._create_alert_from_violation(v, trip["id"], t_id, permit["id"], reg)
                db.append_trip_timeline(trip["id"], "PERMIT_RECONCILIATION_REQUIRED", "Permit Reconciliation Required", invalid_reason)
                db.log_audit("PERMIT_RECONCILIATION_REQUIRED", "permits", permit["id"], permit["status"], "RECONCILIATION_REQUIRED", invalid_reason)
        else:
            v = DetectionEngine.check_unauthorized_mine_entry(t_id, m_id, None)
            if v["is_violation"]:
                self._create_alert_from_violation(v, trip["id"], t_id, None, reg)
            db.append_trip_timeline(trip["id"], "UNAUTHORIZED_ENTRY", "Unauthorized Mine Entry Detected", f"Truck entered {mine['name']} with no active statutory e-Rawaana permit")
            db.log_audit("UNAUTHORIZED_MINE_ENTRY", "trucks", t_id, "OUTSIDE_MINE", "INSIDE_MINE", f"Truck {reg} entered {mine['name']} without active permit")

        if self.socketio:
            self.socketio.emit("truck_entered_mine", {
                "truck_id": t_id,
                "registration_number": reg,
                "mine_id": m_id,
                "mine_name": mine["name"],
                "round_number": round_num,
                "timestamp": now_str
            })

    def handle_mine_exit(self, truck, mine, lat=None, lng=None):
        """
        Requirements 6, 7:
        Automatic Truck Round & Trip Counter & Excessive Trip Detection.
        Authoritatively increments completed rounds upon geofence exit and checks ceiling.
        """
        t_id = truck["id"]
        m_id = mine["id"]
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        reg = truck["registration_number"]

        t_curr = db.query("SELECT is_inside_mine, completed_rounds_today, current_round_number FROM trucks WHERE id = ?", (t_id,), one=True)
        if not t_curr or not t_curr.get("is_inside_mine"):
            return

        completed = int(t_curr.get("completed_rounds_today") or 0) + 1
        next_round = completed + 1

        db.execute("""
            UPDATE trucks 
            SET is_inside_mine = 0, completed_rounds_today = ?, current_round_number = ?,
                last_mine_exit = ?, status = 'IN_TRANSIT'
            WHERE id = ?
        """, (completed, next_round, now_str, t_id))

        db.execute("""
            UPDATE drivers 
            SET completed_rounds_today = completed_rounds_today + 1 
            WHERE assigned_truck_id = ?
        """, (t_id,))

        trip = db.query("""
            SELECT * FROM trips 
            WHERE truck_id = ? AND status IN ('LOADING', 'DISPATCHED', 'IN_TRANSIT', 'SUSPICIOUS')
            ORDER BY id DESC LIMIT 1
        """, (t_id,), one=True)

        if trip:
            db.execute("UPDATE trips SET status = 'IN_TRANSIT', round_number = ? WHERE id = ?", (completed, trip["id"]))
            db.append_trip_timeline(trip["id"], "TRUCK_EXITED_MINE", f"Exited Mine {mine['name']}", f"Trip #{completed} dispatched onto corridor")
            db.append_trip_timeline(trip["id"], "ROUND_COMPLETED", f"Trip #{completed} Dispatched", f"Daily progress: {completed} trips completed today (Unrestricted commercial fleet)")

        db.log_audit("TRUCK_EXITED_MINE", "trucks", t_id, "INSIDE_MINE", "IN_TRANSIT", f"Truck {reg} completed trip #{completed} at Mine {mine['name']}")

        if self.socketio:
            self.socketio.emit("truck_exited_mine", {
                "truck_id": t_id,
                "registration_number": reg,
                "completed_rounds": completed,
                "timestamp": now_str
            })

    def simulate_mine_entry(self, truck_reg="HR26AB1234", mine_id=1):
        """Simulate programmatic or sensor-triggered mine entry."""
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        if not truck or not mine:
            return {"success": False, "error": "Truck or mine not found"}
        self.handle_mine_entry(truck, mine, mine["latitude"], mine["longitude"])
        return {"success": True, "message": f"Truck {truck_reg} entered Mine {mine['name']}"}

    def simulate_mine_exit(self, truck_reg="HR26AB1234", mine_id=1):
        """Simulate programmatic or sensor-triggered mine exit."""
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        if not truck or not mine:
            return {"success": False, "error": "Truck or mine not found"}
        self.handle_mine_exit(truck, mine, mine["latitude"] + 0.05, mine["longitude"] + 0.05)
        return {"success": True, "message": f"Truck {truck_reg} exited Mine {mine['name']}"}

    def _create_alert_from_violation(self, v, trip_id, truck_id, permit_id, reg):
        """Creates alert, logs audit, updates trip risk, and broadcasts via SocketIO."""
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{v['violation_type'][:3]}-{uuid.uuid4().hex[:4].upper()}"
        is_crit = v.get("severity") in ("CRITICAL", "HIGH")
        escalated = 1 if is_crit else 0
        admin_status = "PENDING_VIGILANCE_REVIEW" if is_crit else "NONE"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', 2, ?, ?)
        """, (
            alert_code, trip_id, truck_id, permit_id,
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"]),
            escalated, admin_status
        ))
        if trip_id:
            RiskEngine.evaluate_and_update_trip_risk(trip_id)
        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })


    def trigger_weighbridge_anomaly(self, truck_reg="HR26AB1234"):
        """Simulates recording of 31 MT overweight record on weighbridge."""
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return None

        permit = db.query("SELECT * FROM permits WHERE truck_id = ? AND status = 'ACTIVE'", (truck["id"],), one=True)
        trip = db.query("SELECT * FROM trips WHERE truck_id = ? AND status IN ('IN_TRANSIT', 'SUSPICIOUS')", (truck["id"],), one=True)

        if not permit or not trip:
            return None

        # Insert / Update weighment to 31.0 MT (Permitted: 20.0 MT)
        gross = 42.5
        tare = 11.5
        net = 31.0
        diff = 11.0

        db.execute("""
            INSERT INTO weighments (trip_id, permit_id, truck_id, weighbridge_code, weighbridge_name, gross_weight_mt, tare_weight_mt, net_weight_mt, permitted_weight_mt, difference_mt, is_overweight)
            VALUES (?, ?, ?, 'WB-ALW-01', 'Alwar Mining Exit Weighbridge #1', ?, ?, ?, ?, ?, 1)
        """, (trip["id"], permit["id"], truck["id"], gross, tare, net, permit["permitted_weight_mt"], diff))

        # Run detection engine
        v = DetectionEngine.check_weight_anomaly(permit["permitted_weight_mt"], net, truck["max_capacity_mt"])
        
        # Create or update alert
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        is_crit = v.get("severity") in ("CRITICAL", "HIGH")
        escalated = 1 if is_crit else 0
        admin_status = "PENDING_VIGILANCE_REVIEW" if is_crit else "NONE"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', 2, ?, ?)
        """, (
            alert_code, trip["id"], truck["id"], permit["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"]),
            escalated, admin_status
        ))

        # Re-evaluate trip risk
        risk_res = RiskEngine.evaluate_and_update_trip_risk(trip["id"])

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"],
                "risk_score": risk_res["score"]
            })

        return {"violation": v, "risk": risk_res}

    def trigger_route_deviation(self, truck_reg="HR26AB1234"):
        """Triggers vehicle deviating into unpermitted corridor."""
        self.is_hr26_deviating = True
        self.is_hr26_blackout = False
        self.current_step_hr26 = len(self.deviated_route) - 1

        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        trip = db.query("SELECT * FROM trips WHERE truck_id = ?", (truck["id"],), one=True)
        permit = db.query("SELECT * FROM permits WHERE truck_id = ?", (truck["id"],), one=True)

        lat, lng = self.deviated_route[-1]
        db.execute("UPDATE trucks SET current_lat = ?, current_lng = ? WHERE id = ?", (lat, lng, truck["id"]))

        waypoints = json.loads(permit["route_waypoints_json"]) if permit else []
        v = DetectionEngine.check_route_deviation(lat, lng, waypoints)

        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-DEV-{uuid.uuid4().hex[:4].upper()}"
        is_crit = v.get("severity") in ("CRITICAL", "HIGH")
        escalated = 1 if is_crit else 0
        admin_status = "PENDING_VIGILANCE_REVIEW" if is_crit else "NONE"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', 2, ?, ?)
        """, (
            alert_code, trip["id"], truck["id"], permit["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"]),
            escalated, admin_status
        ))

        risk_res = RiskEngine.evaluate_and_update_trip_risk(trip["id"])
        
        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"],
                "risk_score": risk_res["score"]
            })

        return {"violation": v, "risk": risk_res}

    def trigger_gps_blackout(self, truck_reg="HR26AB1234"):
        """Triggers blackout near sensitive zone."""
        self.is_hr26_blackout = True
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        trip = db.query("SELECT * FROM trips WHERE truck_id = ?", (truck["id"],), one=True)
        permit = db.query("SELECT * FROM permits WHERE truck_id = ?", (truck["id"],), one=True)

        v = DetectionEngine.check_gps_blackout(
            datetime.now() - timedelta(minutes=18), 
            near_sensitive_zone=True, 
            zone_name="Sabi Riverbed Restricted Mining Zone"
        )

        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-BLK-{uuid.uuid4().hex[:4].upper()}"
        is_crit = v.get("severity") in ("CRITICAL", "HIGH")
        escalated = 1 if is_crit else 0
        admin_status = "PENDING_VIGILANCE_REVIEW" if is_crit else "NONE"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW', 2, ?, ?)
        """, (
            alert_code, trip["id"], truck["id"], permit["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"]),
            escalated, admin_status
        ))

        risk_res = RiskEngine.evaluate_and_update_trip_risk(trip["id"])

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"],
                "risk_score": risk_res["score"]
            })

        return {"violation": v, "risk": risk_res}

    def trigger_gps_jammer(self, truck_reg="HR26AB1234"):
        """
        Simulates driver activating an illegal RF GPS Jammer ('Gamer') device.
        Satellites drop instantly to 0, C/N0 collapses, while cellular heartbeat persists.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}
        
        trip = db.query("SELECT * FROM trips WHERE truck_id = ? ORDER BY id DESC LIMIT 1", (truck["id"],), one=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.execute("""
            UPDATE trucks 
            SET gps_status = 'JAMMER_DETECTED', 
                jammer_detected_count = jammer_detected_count + 1,
                satellite_count = 0,
                carrier_noise_ratio_cno = 12.8,
                last_tamper_time = ?,
                last_tamper_type = 'GPS_JAMMER_RF'
            WHERE id = ?
        """, (now_str, truck["id"]))

        # Log to gps_tamper_events
        event_id = db.execute("""
            INSERT INTO gps_tamper_events 
            (truck_id, trip_id, event_type, severity, latitude, longitude, location_name,
             satellite_count, external_power_volts, battery_level_pct, duration_seconds,
             detection_method, evidence_notes, action_taken, status, created_at)
            VALUES (?, ?, 'GPS_JAMMER_DETECTED', 'CRITICAL', ?, ?, ?, 0, ?, 100, 480,
                    'RF C/N0 Collapse to 12.8 dB-Hz with active GSM ping',
                    'Deliberate high-power GNSS Jammer detected. GSM heartbeat continued while GNSS satellite lock collapsed to 0 in under 2 seconds.',
                    'Auto-Alert triggered; Flying Squad notification queued', 'ACTIVE', ?)
        """, (truck["id"], trip["id"] if trip else None, truck["current_lat"], truck["current_lng"],
              "Sabi Riverbed Outskirts (Behror-Kotputli)", truck.get("external_power_volts", 24.2), now_str))

        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-JAM-{uuid.uuid4().hex[:4].upper()}"
        if trip:
            db.execute("""
                INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
                VALUES (?, ?, ?, ?, 'GPS_BLACKOUT', 'CRITICAL', 30, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
            """, (
                alert_code, trip["id"], truck["id"], trip.get("permit_id"),
                f"ILLEGAL GPS JAMMER DETECTED: Transponder C/N0 noise ratio collapsed to 12.8 dB-Hz on vehicle {truck_reg}. Zero satellite lock.",
                json.dumps({"event_id": event_id, "jammer_active": True, "cno_db_hz": 12.8, "satellites": 0})
            ))
            RiskEngine.evaluate_and_update_trip_risk(trip["id"])

        if self.socketio:
            self.socketio.emit("gps_tamper_alert", {
                "event_type": "GPS_JAMMER_DETECTED",
                "truck_reg": truck_reg,
                "severity": "CRITICAL",
                "lat": truck["current_lat"],
                "lng": truck["current_lng"],
                "timestamp": now_str
            })

        return {"status": "success", "event": "GPS_JAMMER_DETECTED", "truck": truck_reg, "event_id": event_id}

    def trigger_hardware_tamper(self, truck_reg="HR26AB1234"):
        """
        Simulates physical power line wire-cut / enclosure opening on AIS-140 unit.
        External power drops from 24V to 0.0V, engaging emergency internal backup battery.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}
        
        trip = db.query("SELECT * FROM trips WHERE truck_id = ? ORDER BY id DESC LIMIT 1", (truck["id"],), one=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.execute("""
            UPDATE trucks 
            SET gps_status = 'TAMPERED', 
                tamper_count = tamper_count + 1,
                external_power_volts = 0.0,
                backup_battery_pct = 82,
                last_tamper_time = ?,
                last_tamper_type = 'POWER_LINE_SEVERED'
            WHERE id = ?
        """, (now_str, truck["id"]))

        event_id = db.execute("""
            INSERT INTO gps_tamper_events 
            (truck_id, trip_id, event_type, severity, latitude, longitude, location_name,
             satellite_count, external_power_volts, battery_level_pct, duration_seconds,
             detection_method, evidence_notes, action_taken, status, created_at)
            VALUES (?, ?, 'HARDWARE_TAMPER_WIRE_CUT', 'HIGH', ?, ?, ?, ?, 0.0, 82, 300,
                    'Main 24V Power Bus Severed (Internal 3.7V LiPo engaged)',
                    'Chassis optical sensor tripped and vehicle main battery voltage dropped to 0.0V.',
                    'Notice dispatched to registered transport owner', 'ACTIVE', ?)
        """, (truck["id"], trip["id"] if trip else None, truck["current_lat"], truck["current_lng"],
              "Kotputli Bypass Industrial Link", truck.get("satellite_count", 11), now_str))

        if self.socketio:
            self.socketio.emit("gps_tamper_alert", {
                "event_type": "HARDWARE_TAMPER_WIRE_CUT",
                "truck_reg": truck_reg,
                "severity": "HIGH",
                "lat": truck["current_lat"],
                "lng": truck["current_lng"],
                "timestamp": now_str
            })

        return {"status": "success", "event": "HARDWARE_TAMPER_WIRE_CUT", "truck": truck_reg, "event_id": event_id}

    def trigger_network_blindspot(self, truck_reg="HR26AB1234"):
        """
        Simulates legitimate cellular dead-zone (mountain valley shadow).
        GNSS satellite lock remains healthy, but GSM signal drops.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}
        
        trip = db.query("SELECT * FROM trips WHERE truck_id = ? ORDER BY id DESC LIMIT 1", (truck["id"],), one=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.execute("""
            UPDATE trucks 
            SET gps_status = 'BLINDSPOT', 
                network_blindspot_count = network_blindspot_count + 1,
                signal_strength_dbm = -118,
                last_tamper_time = ?,
                last_tamper_type = 'GSM_CELL_TOWER_LOSS'
            WHERE id = ?
        """, (now_str, truck["id"]))

        event_id = db.execute("""
            INSERT INTO gps_tamper_events 
            (truck_id, trip_id, event_type, severity, latitude, longitude, location_name,
             satellite_count, external_power_volts, battery_level_pct, duration_seconds,
             detection_method, evidence_notes, action_taken, status, created_at)
            VALUES (?, ?, 'NETWORK_BLINDSPOT', 'LOW', ?, ?, ?, 10, ?, 100, 180,
                    'Cellular Tower Handover Delay in Canyon Ridge',
                    'Standard GSM shadow zone. GNSS satellite geometry is compliant with 10 satellites visible.',
                    'Logged as terrain coverage shadow', 'RESOLVED', ?)
        """, (truck["id"], trip["id"] if trip else None, truck["current_lat"], truck["current_lng"],
              "Alwar South Ridge Canyon Passage", truck.get("external_power_volts", 24.2), now_str))

        return {"status": "success", "event": "NETWORK_BLINDSPOT", "truck": truck_reg, "event_id": event_id}

    def trigger_prohibited_incursion(self, truck_reg="HR26AB1234"):
        """
        Simulates vehicle crossing geofence into illegal mining zone (Sabi Riverbed).
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}
        
        trip = db.query("SELECT * FROM trips WHERE truck_id = ? ORDER BY id DESC LIMIT 1", (truck["id"],), one=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Set location deep in Sabi Riverbed restricted zone
        riverbed_lat, riverbed_lng = 27.8525, 76.4535

        db.execute("""
            UPDATE trucks 
            SET gps_status = 'PROHIBITED_ZONE', 
                prohibited_zone_count = prohibited_zone_count + 1,
                current_lat = ?,
                current_lng = ?,
                last_tamper_time = ?,
                last_tamper_type = 'GEOFENCE_SABI_RIVERBED'
            WHERE id = ?
        """, (riverbed_lat, riverbed_lng, now_str, truck["id"]))

        event_id = db.execute("""
            INSERT INTO gps_tamper_events 
            (truck_id, trip_id, event_type, severity, latitude, longitude, location_name,
             satellite_count, external_power_volts, battery_level_pct, duration_seconds,
             detection_method, evidence_notes, action_taken, status, created_at)
            VALUES (?, ?, 'PROHIBITED_ZONE_INCURSION', 'CRITICAL', ?, ?, 'Sabi Riverbed Restricted Mining Exclusion Zone', 11, 24.2, 100, 600,
                    'Real-time Geofence Boundary Intersection',
                    'Vehicle breached boundary coordinates into protected riverbed without authorized mining lease.',
                    'Case opened; Enforcement team alerted for immediate intercept', 'ACTIVE', ?)
        """, (truck["id"], trip["id"] if trip else None, riverbed_lat, riverbed_lng, now_str))

        return {"status": "success", "event": "PROHIBITED_ZONE_INCURSION", "truck": truck_reg, "event_id": event_id}

    def restore_truck_telemetry(self, truck_reg="HR26AB1234"):
        """
        Restores truck GPS telemetry to healthy online status with 12 satellites and 24V power.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        db.execute("""
            UPDATE trucks 
            SET gps_status = 'HEALTHY',
                satellite_count = 12,
                carrier_noise_ratio_cno = 44.5,
                external_power_volts = 24.2,
                backup_battery_pct = 100,
                signal_strength_dbm = -65,
                last_tamper_type = NULL
            WHERE id = ?
        """, (truck["id"],))

        db.execute("""
            UPDATE gps_tamper_events 
            SET status = 'RESOLVED' 
            WHERE truck_id = ? AND status = 'ACTIVE'
        """, (truck["id"],))

        return {"status": "success", "message": f"Telemetry restored for {truck_reg}."}

    def trigger_interstate_border_breach(self, truck_reg="RJ14GA5521"):
        """
        Simulates commercial vehicle crossing Rajasthan-Haryana border without valid ISTP.
        GPS engine detects border crossing and emits targeted intercept beacon to Bawal checkpoint.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        bawal_lat, bawal_lng = 28.0800, 76.5900
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("UPDATE trucks SET current_lat = ?, current_lng = ?, last_gps_time = ? WHERE id = ?", (bawal_lat, bawal_lng, now_str, truck["id"]))

        istp_v = DetectionEngine.check_interstate_transit_authorization(truck["id"], bawal_lat, bawal_lng)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-ISTP-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"],
            istp_v["violation_type"], istp_v["severity"], istp_v["risk_contribution"],
            istp_v["explanation"], json.dumps(istp_v["metrics"])
        ))

        beacon_payload = {
            "truck_id": truck["id"],
            "registration_number": truck_reg,
            "violation": "UNAUTHORIZED_INTERSTATE_TRANSIT",
            "checkpoint": "Bawal Toll Monitoring Checkpoint",
            "latitude": bawal_lat,
            "longitude": bawal_lng,
            "eta_minutes": 4,
            "alert_code": alert_code,
            "timestamp": now_str
        }

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": istp_v["violation_type"],
                "severity": istp_v["severity"],
                "description": istp_v["explanation"]
            })
            self.socketio.emit("targeted_intercept_beacon", beacon_payload)

        return {"status": "success", "violation": istp_v, "beacon": beacon_payload}

    def trigger_tare_tampering(self, truck_reg="HR26AB1234"):
        """
        Simulates Tare-Weight Inflation tampering (+6.5 MT discrepancy vs RTO baseline).
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        recorded_tare = 18.0
        v = DetectionEngine.check_tare_weight_integrity(truck_id=truck["id"], recorded_tare_mt=recorded_tare)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-TARE-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v}

    def trigger_pass_reuse(self, truck_reg="HR26AB1234"):
        """
        Scenario 1: Pass Recycling / Short-Looping Simulation.
        Simulates driver attempting a 2nd unbilled trip using an unexpired but already consumed e-Ravanna pass.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        # Find or create a consumed permit
        permit = db.query("SELECT * FROM permits WHERE truck_id = ? ORDER BY id DESC LIMIT 1", (truck["id"],), one=True)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not permit:
            p_code = f"RAW-2026-REUSE-{uuid.uuid4().hex[:4].upper()}"
            pid = db.execute("""
                INSERT INTO permits (permit_number, qr_code_hash, truck_id, mine_id, mineral, permitted_weight_mt,
                                    source_name, destination_name, destination_lat, destination_lng, buyer_name,
                                    status, issued_at, expires_at, consumed_at)
                VALUES (?, ?, ?, 1, 'Quartzite', 24.0, 'Aravalli Quartzite Quarry Block A', 'Bhiwadi Aggregates Hub',
                        28.2100, 76.8500, 'DLF ReadyMix Hub', 'CONSUMED',
                        datetime('now', '-2 hours'), datetime('now', '+2 hours'), datetime('now', '-10 minutes'))
            """, (p_code, f"QR-{p_code}", truck["id"]))
            permit = db.query("SELECT * FROM permits WHERE id = ?", (pid,), one=True)
        else:
            db.execute("UPDATE permits SET status = 'CONSUMED', consumed_at = datetime('now', '-10 minutes') WHERE id = ?", (permit["id"],))
            permit = db.query("SELECT * FROM permits WHERE id = ?", (permit["id"],), one=True)

        v = DetectionEngine.check_pass_recycling_and_short_looping(truck["id"], permit["id"], mine_id=1)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-REUSE-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"], permit["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        db.execute("UPDATE trucks SET current_risk_score = MIN(100, current_risk_score + 35), current_risk_level = 'HIGH' WHERE id = ?", (truck["id"],))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v, "alert_code": alert_code}

    def trigger_kanta_cheating(self, truck_reg="HR26AB1234"):
        """
        Scenario 2: Weighbridge Manipulation / Kanta Cheating Simulation.
        Simulates driver stopping with tires partially resting on approach ramp (Gross 38.0 MT vs actual 42.0 MT).
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        # Optical IR beam interrupted / tires on ramp
        v = DetectionEngine.check_weighbridge_kanta_cheating(gross_weight_mt=38.0, tare_weight_mt=11.5, bed_volume_m3=20.0, axle_beam_aligned=False)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-KANTA-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        db.execute("UPDATE trucks SET current_risk_score = MIN(100, current_risk_score + 35), current_risk_level = 'CRITICAL' WHERE id = ?", (truck["id"],))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v, "alert_code": alert_code}

    def trigger_grade_arbitrage(self, truck_reg="HR26AB1234"):
        """
        Scenario 3: Material Quality Fraud / Grade Arbitrage Simulation.
        High-grade Neela Maal (statutory tariff ₹375/MT) declared as cheap Laal Maal (₹300/MT).
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        # Sub-plot 1 (Block 1A - Northern Quartzite Pit) certified for Neela Maal
        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 1 LIMIT 1", one=True)
        q_id = qb["id"] if qb else 1
        v = DetectionEngine.check_mineral_grade_arbitrage(quarry_block_id=q_id, declared_tariff=300.0, declared_mineral="Red Quartzite Grit (Laal Maal)")
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-GRADE-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        db.execute("UPDATE trucks SET current_risk_score = MIN(100, current_risk_score + 25), current_risk_level = 'HIGH' WHERE id = ?", (truck["id"],))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v, "alert_code": alert_code}

    def trigger_token_bypass(self, truck_reg="RJ02GA9901"):
        """
        Scenario 4: Off-Record Token System & Cash Bypass Simulation.
        Truck detected by boundary RFID reader with no valid digital e-Ravanna on portal.
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            # Create temporary record if truck registration doesn't exist yet
            db.execute("INSERT OR IGNORE INTO trucks (registration_number, status, current_mine_id) VALUES (?, 'IN_TRANSIT', 1)", (truck_reg,))
            truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)

        v = DetectionEngine.check_token_system_bypass(truck_reg=truck_reg, rfid_detected=True, has_valid_permit=False, mine_id=1)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-TOKEN-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"] if truck else None,
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        if truck:
            db.execute("UPDATE trucks SET current_risk_score = MIN(100, current_risk_score + 40), current_risk_level = 'CRITICAL' WHERE id = ?", (truck["id"],))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v, "alert_code": alert_code}

    def trigger_over_extraction_killswitch(self, mine_id=1, quarry_block_id=None):
        """
        Scenario 5: Pit Over-Extraction Beyond Sanctioned Environmental Limits.
        Simulates concession quota reaching 101.2% capacity and triggers automated kill-switch lock.
        """
        # Resolve quarry block
        qb = None
        if quarry_block_id:
            qb = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (quarry_block_id,), one=True)
        if not qb:
            qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = ? LIMIT 1", (mine_id,), one=True)

        target_block_id = qb["id"] if qb else 1

        # Set dispatched to exceed allocated quota for target block
        db.execute("""
            UPDATE quarry_blocks 
            SET dispatched_mt = allocated_quota_mt + 180.0, status = 'QUOTA_EXHAUSTED_LOCKED'
            WHERE id = ?
        """, (target_block_id,))

        v = DetectionEngine.check_pit_over_extraction(quarry_block_id=target_block_id, mine_id=mine_id)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-OVEREXT-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, NULL, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code,
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": "MINE CONCESSION 1A",
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v, "alert_code": alert_code}

    def trigger_unclosed_entry(self, truck_reg="HR26AB1234"):
        """
        Scenario 6: Unclosed Vehicle Entries & Ghost Truck Simulation.
        Simulates truck inside pit whose loading dwell has exceeded 120 minutes (statutory threshold: 90 mins).
        """
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
        if not truck:
            return {"error": f"Truck {truck_reg} not found"}

        # Simulate mine entry 130 minutes ago
        past_entry = (datetime.now() - timedelta(minutes=130)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute("""
            UPDATE trucks 
            SET is_inside_mine = 1, current_mine_id = 1, last_mine_entry = ?, status = 'LOADING'
            WHERE id = ?
        """, (past_entry, truck["id"]))

        v = DetectionEngine.check_unclosed_vehicle_entries(mine_id=1, max_dwell_minutes=90)
        alert_code = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-GHOST-{uuid.uuid4().hex[:4].upper()}"
        db.execute("""
            INSERT INTO alerts (alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id, escalated_to_admin, admin_review_status)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, ?, ?, 'NEW', 2, 1, 'PENDING_VIGILANCE_REVIEW')
        """, (
            alert_code, truck["id"],
            v["violation_type"], v["severity"], v["risk_contribution"],
            v["explanation"], json.dumps(v["metrics"])
        ))

        db.execute("UPDATE trucks SET current_risk_score = MIN(100, current_risk_score + 30), current_risk_level = 'HIGH' WHERE id = ?", (truck["id"],))

        if self.socketio:
            self.socketio.emit("new_alert", {
                "alert_code": alert_code,
                "truck": truck_reg,
                "alert_type": v["violation_type"],
                "severity": v["severity"],
                "description": v["explanation"]
            })

        return {"status": "success", "violation": v, "alert_code": alert_code}

    def reset_demo(self):
        """Resets the SIH demo state to initial conditions."""
        self.is_hr26_deviating = False
        self.is_hr26_blackout = False
        self.current_step_hr26 = 0
        db.init_sqlite(force=True)
        return {"status": "success", "message": "Demo data and simulator reset to initial state."}



# Singleton simulator instance
simulator = GPSSimulator()
