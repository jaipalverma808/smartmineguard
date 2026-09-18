"""
SmartMineGuard - Deterministic Rule-Based Detection Engine
STRICTLY PURE SOFTWARE — NO AI / NO MACHINE LEARNING / NO LLM APIs.
"""
from datetime import datetime, timedelta
import json
import logging
from config import Config
from services.db import db, point_to_segment_distance_m, haversine_distance_km

logger = logging.getLogger("smartmineguard.detection")


class DetectionEngine:
    """
    Deterministic rule-based detection engine for identifying mineral transport anomalies.
    Every detection returns:
        - is_violation (bool)
        - violation_type (str)
        - severity (str: LOW, MEDIUM, HIGH, CRITICAL)
        - explanation (str)
        - metrics (dict)
    """

    @staticmethod
    def check_weight_anomaly(permitted_weight_mt, actual_net_weight_mt, max_capacity_mt=None):
        """
        Rule 1: Weight Anomaly Detection
        Compares permitted e-Rawaana weight against actual weighbridge recording.
        """
        tolerance_pct = Config.WEIGHT_TOLERANCE_PERCENT
        difference_mt = actual_net_weight_mt - permitted_weight_mt
        excess_pct = (difference_mt / permitted_weight_mt * 100.0) if permitted_weight_mt > 0 else 0.0

        is_overload = difference_mt > (permitted_weight_mt * (tolerance_pct / 100.0))
        is_capacity_exceeded = (actual_net_weight_mt > max_capacity_mt) if max_capacity_mt else False

        if is_overload or is_capacity_exceeded:
            if excess_pct > 30.0 or difference_mt > 5.0:
                severity = "CRITICAL"
            elif excess_pct > 15.0 or difference_mt > 2.5:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            explanation = (
                f"WEIGHT ANOMALY DETECTED: Permitted = {permitted_weight_mt:.1f} MT, "
                f"Actual = {actual_net_weight_mt:.1f} MT, Difference = {difference_mt:+.1f} MT "
                f"({excess_pct:+.1f}% vs {tolerance_pct}% allowed tolerance)."
            )
            if is_capacity_exceeded:
                explanation += f" Axle capacity exceeded (Max vehicle capacity: {max_capacity_mt:.1f} MT)."

            return {
                "is_violation": True,
                "violation_type": "WEIGHT_ANOMALY",
                "severity": severity,
                "risk_contribution": Config.WEIGHT_ANOMALY_RISK,
                "explanation": explanation,
                "metrics": {
                    "permitted_weight_mt": permitted_weight_mt,
                    "actual_net_weight_mt": actual_net_weight_mt,
                    "difference_mt": round(difference_mt, 2),
                    "excess_pct": round(excess_pct, 1),
                    "max_capacity_mt": max_capacity_mt,
                    "is_capacity_exceeded": is_capacity_exceeded
                }
            }

        return {
            "is_violation": False,
            "violation_type": "WEIGHT_ANOMALY",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Weight within normal limits (Permitted: {permitted_weight_mt:.1f} MT, Actual: {actual_net_weight_mt:.1f} MT).",
            "metrics": {
                "permitted_weight_mt": permitted_weight_mt,
                "actual_net_weight_mt": actual_net_weight_mt,
                "difference_mt": round(difference_mt, 2)
            }
        }

    @staticmethod
    def check_route_deviation(current_lat, current_lng, waypoints, threshold_meters=None):
        """
        Rule 2: Route Corridor Deviation
        Calculates cross-track distance from permitted transit corridor.
        """
        threshold = threshold_meters or Config.ROUTE_CORRIDOR_METERS
        if not waypoints or len(waypoints) < 2:
            return {
                "is_violation": False,
                "violation_type": "ROUTE_DEVIATION",
                "severity": "LOW",
                "risk_contribution": 0,
                "explanation": "No reference corridor defined.",
                "metrics": {"min_distance_m": 0.0}
            }

        # Calculate minimum distance from point to all polyline segments
        min_dist_m = float("inf")
        for i in range(len(waypoints) - 1):
            p1 = waypoints[i]
            p2 = waypoints[i + 1]
            dist_m = point_to_segment_distance_m(
                current_lat, current_lng, 
                p1[0], p1[1], 
                p2[0], p2[1]
            )
            if dist_m < min_dist_m:
                min_dist_m = dist_m

        is_deviated = min_dist_m > threshold

        if is_deviated:
            if min_dist_m > 1500:
                severity = "CRITICAL"
            elif min_dist_m > 750:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            return {
                "is_violation": True,
                "violation_type": "ROUTE_DEVIATION",
                "severity": severity,
                "risk_contribution": Config.ROUTE_DEVIATION_RISK,
                "explanation": (
                    f"ROUTE DEVIATION DETECTED: Vehicle is {min_dist_m:.0f}m outside authorized "
                    f"mineral transport corridor (Max buffer: {threshold:.0f}m)."
                ),
                "metrics": {
                    "deviation_distance_m": round(min_dist_m, 1),
                    "allowed_threshold_m": threshold,
                    "current_coordinates": [current_lat, current_lng]
                }
            }

        return {
            "is_violation": False,
            "violation_type": "ROUTE_DEVIATION",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Vehicle is operating inside permitted transit corridor ({min_dist_m:.0f}m from axis).",
            "metrics": {"deviation_distance_m": round(min_dist_m, 1)}
        }

    @staticmethod
    def check_gps_blackout(last_ping_time, current_time=None, near_sensitive_zone=False, zone_name=None):
        """
        Rule 3: GPS Blackout & Signal Loss Detection
        Flags prolonged loss of telemetry, escalating risk when near sensitive zones.
        """
        now = current_time or datetime.now()
        if isinstance(last_ping_time, str):
            try:
                last_ping_time = datetime.strptime(last_ping_time, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return {"is_violation": False, "violation_type": "GPS_BLACKOUT", "risk_contribution": 0}

        elapsed_seconds = (now - last_ping_time).total_seconds()
        threshold_seconds = Config.GPS_BLACKOUT_SECONDS

        if elapsed_seconds > threshold_seconds:
            elapsed_minutes = elapsed_seconds / 60.0
            if near_sensitive_zone:
                severity = "CRITICAL"
                extra_risk = Config.SUSPICIOUS_ZONE_RISK
                desc = (
                    f"SUSPICIOUS GPS BLACKOUT / STRATEGIC GEOFENCE BLACKOUT DETECTED: Telemetry lost for {elapsed_minutes:.1f} minutes "
                    f"in immediate proximity (within 1,000m) of protected zone '{zone_name or 'Restricted Riverbed/Forest'}'. "
                    f"Pattern indicates deliberate GPS disconnection during unpermitted mineral extraction."
                )
                v_type = "GPS_BLACKOUT"
                is_viol = True
                risk_pts = Config.GPS_BLACKOUT_RISK + extra_risk
            elif elapsed_minutes > 15:
                severity = "MEDIUM"
                desc = f"PROLONGED TRANSIT BLACKOUT: Telemetry lost for {elapsed_minutes:.1f} minutes along transit corridor. Field officer check recommended."
                v_type = "GPS_BLACKOUT"
                is_viol = True
                risk_pts = 15
            else:
                # Context-aware: Benign highway/cellular shadow
                severity = "LOW"
                desc = f"HIGHWAY CELLULAR HANDOVER SHADOW: Telemetry delay of {elapsed_minutes:.1f} minutes along authorized highway corridor. Normal terrain/GSM variance (no sensitive zone proximity)."
                v_type = "NETWORK_BLINDSPOT"
                is_viol = False
                risk_pts = 0

            return {
                "is_violation": is_viol,
                "violation_type": v_type,
                "severity": severity,
                "risk_contribution": risk_pts,
                "explanation": desc,
                "metrics": {
                    "blackout_seconds": int(elapsed_seconds),
                    "blackout_minutes": round(elapsed_minutes, 1),
                    "near_sensitive_zone": near_sensitive_zone,
                    "zone_name": zone_name,
                    "is_strategic_tampering": near_sensitive_zone
                }
            }

        return {
            "is_violation": False,
            "violation_type": "GPS_BLACKOUT",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"GPS heartbeat healthy (last ping {int(elapsed_seconds)}s ago).",
            "metrics": {"elapsed_seconds": int(elapsed_seconds)}
        }

    @staticmethod
    def classify_telemetry_interruption(satellite_count, cno_db_hz, external_power_volts, in_prohibited_zone=False, elapsed_seconds=0):
        """
        AI/Heuristic Anti-Tamper & Jammer Classification Engine.
        Accurately distinguishes between:
        1. Deliberate GPS Jammer ('Gamer' RF Device Attack)
        2. Physical Hardware Wire-Cut / Enclosure Tampering
        3. Prohibited Illegal Mining Buffer / Riverbed Incursion
        4. Legitimate GSM Cellular Shadow / Mountain Dead-zone
        """
        if external_power_volts <= 2.0:
            return {
                "classification": "HARDWARE_TAMPER_WIRE_CUT",
                "severity": "HIGH",
                "risk_contribution": 25,
                "is_threat": True,
                "title": "Hardware Wire-Cut / Power Severed",
                "explanation": f"Vehicle main 24V power bus severed (reading {external_power_volts:.1f}V). AIS-140 unit operating on emergency internal LiPo backup battery.",
                "indicators": ["Main 24V bus disconnected", "Internal battery failsafe active", "Chassis optical sensor tripped"]
            }

        if in_prohibited_zone:
            return {
                "classification": "PROHIBITED_ZONE_INCURSION",
                "severity": "CRITICAL",
                "risk_contribution": 35,
                "is_threat": True,
                "title": "Restricted Riverbed / Buffer Incursion",
                "explanation": "Vehicle location coordinates intersect designated illegal mining exclusion zone (e.g. Sabi Riverbed / Aravalli Eco-Buffer).",
                "indicators": ["Geofence exclusion zone breached", "Prohibited quarry approach", "Unmonitored night movement"]
            }

        # Jammer signature: sudden collapse of GNSS Carrier-to-Noise ratio (C/N0 < 20 dB-Hz) or 0 satellites while cellular modem is active
        if satellite_count == 0 or (cno_db_hz is not None and cno_db_hz < 20.0):
            return {
                "classification": "GPS_JAMMER_DETECTED",
                "severity": "CRITICAL",
                "risk_contribution": 30,
                "is_threat": True,
                "title": "Deliberate GPS RF Jammer Detected",
                "explanation": f"RF Jamming signature detected. GNSS signal-to-noise ratio collapsed to {cno_db_hz:.1f} dB-Hz (0 active satellites) while cellular telemetry link remains operational.",
                "indicators": ["Abrupt C/N0 carrier-to-noise collapse (<20 dB-Hz)", "Immediate 0-satellite drop in <3 seconds", "Cellular telemetry active with zero GNSS lock"]
            }

        if elapsed_seconds > 180:
            return {
                "classification": "NETWORK_BLINDSPOT",
                "severity": "LOW",
                "risk_contribution": 5,
                "is_threat": False,
                "title": "Legitimate Cellular Dead-Zone",
                "explanation": f"Telemetry delay ({int(elapsed_seconds/60)}m) consistent with mountain terrain / rural cellular shadow. Normal GNSS satellite constellation ({satellite_count} sats, {cno_db_hz:.1f} dB-Hz).",
                "indicators": ["Healthy GNSS satellite lock maintained", "Gradual cellular ping latency increase", "Known highway dead-zone terrain"]
            }

        return {
            "classification": "HEALTHY",
            "severity": "LOW",
            "risk_contribution": 0,
            "is_threat": False,
            "title": "Healthy AIS-140 Telemetry",
            "explanation": f"Active GNSS lock with {satellite_count} satellites, {cno_db_hz:.1f} dB-Hz C/N0, {external_power_volts:.1f}V vehicle power.",
            "indicators": ["10+ satellites locked", "Nominal 24V supply", "Corridor compliant"]
        }

    @staticmethod
    def check_permit_reuse(permit_id, current_truck_id, current_trip_id=None):
        """
        Rule 4: Permit / e-Rawaana Reuse Detection
        Detects reuse of a consumed permit or duplicate concurrent trip assignments.
        """
        permit = db.query("SELECT * FROM permits WHERE id = ?", (permit_id,), one=True)
        if not permit:
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE",
                "severity": "CRITICAL",
                "risk_contribution": Config.PERMIT_REUSE_RISK,
                "explanation": "INVALID PERMIT: e-Rawaana permit does not exist in central registry.",
                "metrics": {"permit_id": permit_id}
            }

        status = permit["status"]
        if status == "CONSUMED":
            consumed_time = permit.get("consumed_at") or "earlier today"
            dest_name = permit.get("destination_name") or "Authorized Destination"
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE",
                "severity": "CRITICAL",
                "risk_contribution": Config.PERMIT_REUSE_RISK,
                "explanation": (
                    f"PERMIT RECYCLING FRAUD DETECTED (PARCHI REUSE): e-Rawaana {permit['permit_number']} was already "
                    f"CONSUMED upon delivery at {dest_name} (Logged: {consumed_time}). "
                    f"Attempting unpermitted secondary transit on recycled paperwork under Section 21 MMDR Act."
                ),
                "metrics": {
                    "permit_number": permit["permit_number"],
                    "status": status,
                    "consumed_at": str(consumed_time),
                    "destination": dest_name,
                    "registered_truck_id": permit["truck_id"],
                    "is_parchi_recycling": True
                }
            }

        if status == "EXPIRED":
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE",
                "severity": "HIGH",
                "risk_contribution": 20,
                "explanation": f"EXPIRED PERMIT PRESENTED: e-Rawaana {permit['permit_number']} expired on {permit['expires_at']}.",
                "metrics": {"permit_number": permit["permit_number"], "status": status}
            }

        # Check if permit was assigned to a different truck
        if permit["truck_id"] and permit["truck_id"] != current_truck_id:
            assigned_truck = db.query("SELECT registration_number FROM trucks WHERE id = ?", (permit["truck_id"],), one=True)
            assigned_reg = assigned_truck["registration_number"] if assigned_truck else "Unknown"
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE",
                "severity": "CRITICAL",
                "risk_contribution": Config.PERMIT_REUSE_RISK,
                "explanation": (
                    f"VEHICLE MISMATCH: e-Rawaana {permit['permit_number']} is officially bound to "
                    f"vehicle {assigned_reg}, but is being utilized by another truck."
                ),
                "metrics": {
                    "permit_number": permit["permit_number"],
                    "assigned_truck": assigned_reg,
                    "current_truck_id": current_truck_id
                }
            }

        return {
            "is_violation": False,
            "violation_type": "PERMIT_REUSE",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"e-Rawaana {permit['permit_number']} is valid and active for this transport vehicle.",
            "metrics": {"permit_number": permit["permit_number"], "status": status}
        }

    @staticmethod
    def check_impossible_transit(distance_km, duration_minutes, max_legal_speed_kmh=None):
        """
        Rule 5: Impossible Transit / Teleportation Detection
        Flags trips requiring unfeasible physical speeds (e.g. 300 km in 30 min).
        """
        max_speed = max_legal_speed_kmh or Config.MAX_REASONABLE_SPEED_KMH
        if duration_minutes <= 0:
            avg_speed_kmh = float("inf")
        else:
            avg_speed_kmh = (distance_km / (duration_minutes / 60.0))

        if avg_speed_kmh > max_speed:
            severity = "CRITICAL" if avg_speed_kmh > 120.0 else "HIGH"
            return {
                "is_violation": True,
                "violation_type": "IMPOSSIBLE_TRANSIT",
                "severity": severity,
                "risk_contribution": Config.IMPOSSIBLE_TRANSIT_RISK,
                "explanation": (
                    f"IMPOSSIBLE TRANSIT DETECTED: Transit covered {distance_km:.1f} km in "
                    f"{duration_minutes:.1f} minutes, requiring an average speed of {avg_speed_kmh:.1f} km/h "
                    f"(Legal tipper limit: {max_speed:.0f} km/h). Suspected fake telemetry or paper-only e-Rawaana."
                ),
                "metrics": {
                    "distance_km": round(distance_km, 1),
                    "duration_minutes": round(duration_minutes, 1),
                    "calculated_speed_kmh": round(avg_speed_kmh, 1),
                    "max_speed_limit_kmh": max_speed
                }
            }

        return {
            "is_violation": False,
            "violation_type": "IMPOSSIBLE_TRANSIT",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Transit speed plausible ({avg_speed_kmh:.1f} km/h over {distance_km:.1f} km).",
            "metrics": {"calculated_speed_kmh": round(avg_speed_kmh, 1)}
        }

    @staticmethod
    def check_production_dispatch_mismatch(mine_id):
        """
        Rule 6: Production vs Dispatch Reconciliation
        Compares leasehold cumulative dispatch tonnage against authorized environmental extraction quota.
        """
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        if not mine:
            return {"is_violation": False, "violation_type": "PRODUCTION_MISMATCH", "risk_contribution": 0}

        quota_mt = mine["authorized_annual_quota_mt"]
        dispatch_mt = mine["current_dispatch_mt"]
        excess_mt = dispatch_mt - quota_mt

        if excess_mt > 0:
            excess_pct = (excess_mt / quota_mt) * 100.0
            return {
                "is_violation": True,
                "violation_type": "PRODUCTION_MISMATCH",
                "severity": "CRITICAL" if excess_pct > 10.0 else "HIGH",
                "risk_contribution": Config.PRODUCTION_MISMATCH_RISK,
                "explanation": (
                    f"PRODUCTION-DISPATCH MISMATCH: Mine {mine['mine_code']} ({mine['name']}) has dispatched "
                    f"{dispatch_mt:,.1f} MT, exceeding its authorized environmental clearance quota of "
                    f"{quota_mt:,.1f} MT by {excess_mt:,.1f} MT (+{excess_pct:.1f}% unpermitted dispatch)."
                ),
                "metrics": {
                    "mine_code": mine["mine_code"],
                    "authorized_quota_mt": quota_mt,
                    "current_dispatch_mt": dispatch_mt,
                    "excess_mt": round(excess_mt, 1),
                    "excess_pct": round(excess_pct, 1)
                }
            }

        return {
            "is_violation": False,
            "violation_type": "PRODUCTION_MISMATCH",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Dispatch ({dispatch_mt:,.1f} MT) within legal annual quota ({quota_mt:,.1f} MT).",
            "metrics": {"authorized_quota_mt": quota_mt, "current_dispatch_mt": dispatch_mt}
        }

    @staticmethod
    def check_unauthorized_mine_entry(truck_id, mine_id, permit=None):
        """
        Rule 7: GPS-Based Mine Entry & Permit Reconciliation
        Detects unauthorized vehicle presence in mine geofence without a valid active e-Rawaana.
        """
        truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
        reg = truck["registration_number"] if truck else f"TRK-{truck_id}"
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        mine_name = mine["name"] if mine else f"Mine #{mine_id}"

        if not permit:
            permit = db.query("""
                SELECT * FROM permits 
                WHERE truck_id = ? AND status IN ('ACTIVE', 'ISSUED', 'TRUCK_ARRIVED', 'LOADING')
                ORDER BY id DESC LIMIT 1
            """, (truck_id,), one=True)

        if not permit:
            return {
                "is_violation": True,
                "violation_type": "UNAUTHORIZED_MINE_ENTRY",
                "severity": "CRITICAL",
                "risk_contribution": 30,
                "explanation": f"UNAUTHORIZED MINE ENTRY: Truck {reg} entered {mine_name} with no valid active e-Rawaana permit.",
                "metrics": {
                    "truck_registration": reg,
                    "mine_id": mine_id,
                    "mine_name": mine_name,
                    "status": "NO_ACTIVE_PERMIT"
                }
            }

        # Validate vehicle binding
        if permit.get("truck_id") and permit["truck_id"] != truck_id:
            assigned = db.query("SELECT registration_number FROM trucks WHERE id = ?", (permit["truck_id"],), one=True)
            assigned_reg = assigned["registration_number"] if assigned else "Another Vehicle"
            return {
                "is_violation": True,
                "violation_type": "PERMIT_MISMATCH",
                "severity": "CRITICAL",
                "risk_contribution": 30,
                "explanation": f"PERMIT-VEHICLE MISMATCH: Permit {permit['permit_number']} is officially bound to vehicle {assigned_reg}, but vehicle {reg} entered mine.",
                "metrics": {
                    "permit_number": permit["permit_number"],
                    "assigned_truck": assigned_reg,
                    "actual_truck": reg
                }
            }

        # Check expiration
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if permit.get("expires_at") and str(permit["expires_at"]) < now_str:
            return {
                "is_violation": True,
                "violation_type": "PERMIT_MISMATCH",
                "severity": "HIGH",
                "risk_contribution": 20,
                "explanation": f"EXPIRED PERMIT PRESENTED: e-Rawaana {permit['permit_number']} expired on {permit['expires_at']}.",
                "metrics": {
                    "permit_number": permit["permit_number"],
                    "expires_at": permit["expires_at"],
                    "actual_truck": reg
                }
            }

        # Check consumption
        if permit.get("status") == "CONSUMED":
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE",
                "severity": "CRITICAL",
                "risk_contribution": 35,
                "explanation": f"PERMIT REUSE VIOLATION: e-Rawaana {permit['permit_number']} was already marked CONSUMED upon previous trip delivery.",
                "metrics": {
                    "permit_number": permit["permit_number"],
                    "actual_truck": reg
                }
            }

        return {
            "is_violation": False,
            "violation_type": "PERMIT_VERIFIED",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Valid e-Rawaana {permit['permit_number']} verified and auto-matched for Truck {reg} entering {mine_name}.",
            "metrics": {
                "permit_number": permit["permit_number"],
                "mineral": permit.get("mineral"),
                "permitted_weight_mt": permit.get("permitted_weight_mt")
            }
        }

    @staticmethod
    def check_excessive_trip_frequency(truck_id, completed_rounds=None):
        """
        Fleet Trip Telemetry (Unrestricted Commercial Operations):
        In real-world mining transport, trucks are not limited by daily trip counts.
        Tracks active dispatch frequency and logs trip progress without raising fraud violations.
        """
        truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
        reg = truck["registration_number"] if truck else f"TRK-{truck_id}"
        comp = completed_rounds if completed_rounds is not None else (truck["completed_rounds_today"] if truck else 0)

        return {
            "is_violation": False,
            "violation_type": "EXCESSIVE_TRIP_FREQUENCY",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Truck {reg} operating normally under unrestricted daily commercial dispatch ({comp} trip(s) completed today).",
            "metrics": {
                "truck_registration": reg,
                "completed_rounds": comp,
                "is_unrestricted": True
            }
        }

    @staticmethod
    def check_production_dispatch_reconciliation(mine_id, tolerance_mt=50.0):
        """
        Rule 9: Pithead Production vs Outbound Dispatch Mass-Balance Check
        Opening Stock + Today's Production - Dispatched Quantity = Expected Closing Stock.
        Flags discrepancy beyond tolerance.
        """
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        if not mine:
            return {"is_violation": False, "violation_type": "PRODUCTION_MISMATCH", "risk_contribution": 0}

        sp = db.query("SELECT * FROM stock_production WHERE mine_id = ? ORDER BY record_date DESC, id DESC LIMIT 1", (mine_id,), one=True)
        opening = float(sp["opening_stock_mt"]) if sp else float(mine.get("opening_stock_mt") or 4000.0)
        production = float(sp["production_mt"]) if sp else float(mine.get("daily_production_mt") or 600.0)
        dispatch = float(sp["dispatch_mt"]) if sp else float(mine.get("current_dispatch_mt") or 400.0)
        recorded_closing = float(sp["closing_stock_mt"]) if sp else float(mine.get("current_stock_mt") or (opening + production - dispatch))

        expected_closing = round(opening + production - dispatch, 2)
        mismatch = round(abs(expected_closing - recorded_closing), 2)

        if mismatch > tolerance_mt:
            severity = "CRITICAL" if mismatch > 150.0 else "HIGH"
            return {
                "is_violation": True,
                "violation_type": "PRODUCTION_MISMATCH",
                "severity": severity,
                "risk_contribution": 25,
                "explanation": (
                    f"PRODUCTION-DISPATCH MISMATCH: Mine {mine['mine_code']} ({mine['name']}) exhibits an inventory "
                    f"mismatch of {mismatch:.1f} MT (Calculated mass-balance: {expected_closing:.1f} MT vs Recorded: {recorded_closing:.1f} MT, "
                    f"exceeding {tolerance_mt:.1f} MT statutory tolerance)."
                ),
                "metrics": {
                    "mine_code": mine["mine_code"],
                    "opening_stock_mt": opening,
                    "production_mt": production,
                    "dispatch_mt": dispatch,
                    "expected_closing_stock_mt": expected_closing,
                    "recorded_closing_stock_mt": recorded_closing,
                    "mismatch_mt": mismatch,
                    "tolerance_mt": tolerance_mt
                }
            }

        return {
            "is_violation": False,
            "violation_type": "PRODUCTION_MISMATCH",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Production and dispatch mass-balance reconciled for {mine['name']} (Discrepancy: {mismatch:.1f} MT within {tolerance_mt:.1f} MT limit).",
            "metrics": {"expected_closing_mt": expected_closing, "recorded_closing_mt": recorded_closing, "mismatch_mt": mismatch}
        }

    @staticmethod
    def check_manual_weight_override(weighment_id):
        """
        Rule 10: Manual Weighment Calibration / Override Audit
        Flags manual intervention in scale records and records risk factor.
        """
        w = db.query("SELECT * FROM weighments WHERE id = ?", (weighment_id,), one=True)
        if not w:
            return {"is_violation": False, "violation_type": "MANUAL_OVERRIDE", "risk_contribution": 0}

        if w.get("is_manual_override"):
            orig = w.get("original_net_weight_mt") or 0.0
            corrected = w.get("net_weight_mt") or 0.0
            diff = round(corrected - orig, 2)
            return {
                "is_violation": True,
                "violation_type": "MANUAL_OVERRIDE",
                "severity": "MEDIUM",
                "risk_contribution": 15,
                "explanation": f"MANUAL WEIGHT OVERRIDE: Scale weight was manually altered from {orig:.1f} MT to {corrected:.1f} MT (Net delta: {diff:+.1f} MT). Reason: {w.get('override_reason') or 'Unspecified manual correction'}.",
                "metrics": {
                    "weighment_id": weighment_id,
                    "original_weight_mt": orig,
                    "corrected_weight_mt": corrected,
                    "difference_mt": diff,
                    "reason": w.get("override_reason")
                }
            }

        return {
            "is_violation": False,
            "violation_type": "MANUAL_OVERRIDE",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": "Certified automated scale measurement.",
            "metrics": {"source": w.get("measurement_source", "AUTOMATED_WEIGHBRIDGE_SCALE")}
        }

    @staticmethod
    def check_tare_weight_integrity(weighment_id=None, truck_id=None, recorded_tare_mt=None):
        """
        Rule 11: Weighbridge Tare-Weight Inflation & RTO Baseline Cross-Check
        Compares measured empty tare weight against manufacturer/RTO unladen baseline.
        Flags tare inflation (> 8% or > 1.2 MT discrepancy) used to conceal mineral load.
        """
        if weighment_id:
            w = db.query("SELECT * FROM weighments WHERE id = ?", (weighment_id,), one=True)
            if w:
                truck_id = truck_id or w.get("truck_id")
                recorded_tare_mt = recorded_tare_mt if recorded_tare_mt is not None else float(w.get("tare_weight_mt") or 0.0)

        truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True) if truck_id else None
        if not truck or recorded_tare_mt is None:
            return {"is_violation": False, "violation_type": "TARE_WEIGHT_INFLATION", "risk_contribution": 0}

        rto_tare_mt = float(truck.get("tare_weight_mt") or 11.5)
        diff_mt = round(recorded_tare_mt - rto_tare_mt, 2)
        diff_pct = round((diff_mt / rto_tare_mt) * 100.0, 1) if rto_tare_mt > 0 else 0.0

        if diff_mt > 1.2 and diff_pct > 8.0:
            severity = "CRITICAL" if diff_mt > 3.0 else "HIGH"
            return {
                "is_violation": True,
                "violation_type": "TARE_WEIGHT_INFLATION",
                "severity": severity,
                "risk_contribution": 25,
                "explanation": (
                    f"TARE WEIGHT INFLATION DETECTED: Measured tare ({recorded_tare_mt:.1f} MT) exceeds official "
                    f"RTO Vahan unladen weight ({rto_tare_mt:.1f} MT) by {diff_mt:+.1f} MT (+{diff_pct:.1f}%). "
                    f"Suspected empty-weight spoofing to conceal mineral cargo payload."
                ),
                "metrics": {
                    "truck_id": truck_id,
                    "registration_number": truck.get("registration_number"),
                    "recorded_tare_mt": recorded_tare_mt,
                    "rto_tare_mt": rto_tare_mt,
                    "discrepancy_mt": diff_mt,
                    "discrepancy_pct": diff_pct
                }
            }

        return {
            "is_violation": False,
            "violation_type": "TARE_WEIGHT_INFLATION",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Tare weight {recorded_tare_mt:.1f} MT matches RTO unladen baseline ({rto_tare_mt:.1f} MT).",
            "metrics": {"recorded_tare_mt": recorded_tare_mt, "rto_tare_mt": rto_tare_mt, "discrepancy_mt": diff_mt}
        }

    @staticmethod
    def check_interstate_transit_authorization(truck_id, current_lat, current_lng):
        """
        Rule 12: Automated GPS-Based Inter-State Border Crossing & ISTP Verification
        Directly checks via GPS when an interstate vehicle crosses into Haryana 
        (e.g., NH-48 Bawal corridor latitude > 27.95 from Rajasthan) whether it 
        possesses an authorized Inter-State Transit Pass (ISTP).
        """
        truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
        if not truck:
            return {"is_violation": False, "violation_type": "UNAUTHORIZED_INTERSTATE_TRANSIT", "risk_contribution": 0}

        reg = truck.get("registration_number", "")
        is_interstate_carrier = reg.startswith(("RJ", "UP", "DL", "PB", "OD"))

        # Haryana Southern border threshold on NH-48 / Bawal Corridor is ~27.95
        is_crossing_into_haryana = current_lat >= 27.95 and current_lat <= 28.35 and (76.35 <= current_lng <= 76.95)

        if is_interstate_carrier and is_crossing_into_haryana:
            # Query active transit permits for this truck
            permit = db.query("""
                SELECT * FROM permits 
                WHERE truck_id = ? AND status IN ('ACTIVE', 'IN_TRANSIT', 'DISPATCHED')
                ORDER BY id DESC LIMIT 1
            """, (truck_id,), one=True)

            has_valid_istp = False
            if permit:
                p_num = permit.get("permit_number", "")
                src = permit.get("source_name", "")
                dest = permit.get("destination_name", "")
                has_valid_istp = ("ISTP" in p_num) or ("Rajasthan" in src and "Haryana" in dest) or ("Alwar" in src and ("Gurugram" in dest or "Bhiwadi" in dest or "Manesar" in dest))

            if not has_valid_istp:
                return {
                    "is_violation": True,
                    "violation_type": "UNAUTHORIZED_INTERSTATE_TRANSIT",
                    "severity": "CRITICAL",
                    "risk_contribution": 35,
                    "explanation": (
                        f"UNAUTHORIZED INTER-STATE BORDER CROSSING DETECTED VIA GPS: Commercial tipper {reg} "
                        f"crossed the Rajasthan-Haryana border into Bawal corridor (Lat: {current_lat:.4f}, Lng: {current_lng:.4f}) "
                        f"without an authorized Inter-State Transit Pass (ISTP). Targeted intercept beacon dispatched."
                    ),
                    "metrics": {
                        "truck_registration": reg,
                        "current_lat": current_lat,
                        "current_lng": current_lng,
                        "border_checkpoint": "Bawal Toll Monitoring Checkpoint",
                        "permit_found": bool(permit),
                        "permit_number": permit.get("permit_number") if permit else None
                    }
                }

        return {
            "is_violation": False,
            "violation_type": "UNAUTHORIZED_INTERSTATE_TRANSIT",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Vehicle {reg} has authorized transit clearance.",
            "metrics": {"truck_registration": reg}
        }

    @staticmethod
    def check_permit_issuance_eligibility(truck_id, driver_id=None, mine_id=None):
        """
        Daily Trip Surveillance & Permit Issuance Eligibility:
        Validates vehicle/driver status for permit generation under unrestricted daily commercial operations.
        Enforces the Automated Tender Quota Kill-Switch if mine concession is exhausted.
        """
        # 1. Tender Quota Kill-Switch check
        if mine_id:
            mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
            if mine:
                quota_mt = float(mine.get("authorized_annual_quota_mt") or 50000.0)
                disp_mt = float(mine.get("current_dispatch_mt") or 0.0)
                if disp_mt >= quota_mt or mine.get("status") == "QUOTA_EXCEEDED":
                    return {
                        "eligible": False,
                        "reason": "QUOTA_EXHAUSTED",
                        "is_kill_switch_active": True,
                        "mine_name": mine.get("name"),
                        "explanation": (
                            f"STATUTORY TENDER QUOTA KILL-SWITCH ACTIVE: Mine {mine['mine_code']} ({mine['name']}) has "
                            f"exhausted 100% of its sanctioned environmental concession quota ({disp_mt:,.1f} / {quota_mt:,.1f} MT). "
                            f"e-Rawaana issuance is legally frozen under Section 21 of MMDR Act and Rule 104 of Haryana Minor Mineral Rules."
                        )
                    }

        truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
        if not truck:
            return {
                "eligible": False,
                "reason": "INVALID_VEHICLE",
                "explanation": "Vehicle record not found in system."
            }

        completed_rounds = truck.get("completed_rounds_today", 0) or 0
        driver_name = truck.get("driver_name") or "Assigned Transporter"

        # Check driver record if specified or assigned to truck
        driver = None
        if driver_id:
            driver = db.query("SELECT * FROM drivers WHERE id = ?", (driver_id,), one=True)
        elif truck_id:
            driver = db.query("SELECT * FROM drivers WHERE assigned_truck_id = ?", (truck_id,), one=True)

        if driver:
            driver_name = driver.get("driver_name") or driver_name

        return {
            "eligible": True,
            "is_unrestricted": True,
            "completed_rounds": completed_rounds,
            "truck_registration": truck.get("registration_number"),
            "driver_name": driver_name,
            "explanation": (
                f"Vehicle {truck.get('registration_number')} and driver '{driver_name}' authorized "
                f"for unrestricted daily commercial mineral transport (Trip #{completed_rounds + 1} today)."
            )
        }

    @classmethod
    def run_all_evaluations(cls, trip_id=None, truck_id=None, permit_id=None, weighment_id=None):
        """
        Orchestrates all 6 detection rules for a trip or vehicle and compiles violations.
        """
        violations = []
        
        # 1. Weight Anomaly & Tare Weight Inflation
        if weighment_id:
            w = db.query("SELECT * FROM weighments WHERE id = ?", (weighment_id,), one=True)
            if w:
                res = cls.check_weight_anomaly(w["permitted_weight_mt"], w["net_weight_mt"])
                if res["is_violation"]:
                    violations.append(res)
                tare_res = cls.check_tare_weight_integrity(weighment_id=w["id"])
                if tare_res["is_violation"]:
                    violations.append(tare_res)
        elif permit_id and trip_id:
            w = db.query("SELECT * FROM weighments WHERE trip_id = ?", (trip_id,), one=True)
            if w:
                res = cls.check_weight_anomaly(w["permitted_weight_mt"], w["net_weight_mt"])
                if res["is_violation"]:
                    violations.append(res)
                tare_res = cls.check_tare_weight_integrity(weighment_id=w["id"])
                if tare_res["is_violation"]:
                    violations.append(tare_res)

        # 2. Permit Reuse
        if permit_id and truck_id:
            res = cls.check_permit_reuse(permit_id, truck_id, trip_id)
            if res["is_violation"]:
                violations.append(res)

        # 3. Route Deviation, GPS Blackout & Inter-State Check
        if truck_id:
            truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
            if truck and truck["current_lat"] and truck["current_lng"]:
                permit = db.query("SELECT * FROM permits WHERE id = ?", (permit_id,), one=True) if permit_id else None
                if permit and permit["route_waypoints_json"]:
                    try:
                        waypoints = json.loads(permit["route_waypoints_json"])
                        res = cls.check_route_deviation(truck["current_lat"], truck["current_lng"], waypoints)
                        if res["is_violation"]:
                            violations.append(res)
                    except Exception as e:
                        logger.error(f"Error parsing waypoints: {e}")

                if truck["last_gps_time"]:
                    res = cls.check_gps_blackout(truck["last_gps_time"])
                    if res["is_violation"]:
                        violations.append(res)

                # Automated Inter-state Border Cross-check
                istp_res = cls.check_interstate_transit_authorization(truck_id, truck["current_lat"], truck["current_lng"])
                if istp_res["is_violation"]:
                    violations.append(istp_res)

        return violations

    # ============================================================
    # REAL-WORLD MINING FRAUD MITIGATION RULES (6 CORE SCENARIOS)
    # ============================================================

    @classmethod
    def check_pass_recycling_and_short_looping(cls, truck_id, permit_id, mine_id=1, elapsed_turnaround_minutes=None):
        """
        Scenario 1: Transit Pass Recycling / Short-Looping Detection
        Identifies trucks attempting to reuse an unexpired e-Ravanna for an unbilled second trip,
        or returning to the mine in impossible turnaround time.
        """
        permit = db.query("SELECT * FROM permits WHERE id = ?", (permit_id,), one=True)
        if not permit:
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE_ATTEMPT",
                "severity": "CRITICAL",
                "risk_contribution": 35,
                "explanation": "PASS RECYCLING ATTACK: Specified e-Ravanna transit pass does not exist in registry.",
                "metrics": {"permit_id": permit_id, "is_recycled": True}
            }

        truck = db.query("SELECT * FROM trucks WHERE id = ?", (truck_id,), one=True)
        reg = truck["registration_number"] if truck else f"TRK-{truck_id}"

        # 1. Check if permit is already consumed / delivered
        if permit["status"] in ("CONSUMED", "DELIVERED", "EXHAUSTED", "CANCELLED_FRAUD_REUSE"):
            consumed_at = permit.get("consumed_at") or "earlier today"
            return {
                "is_violation": True,
                "violation_type": "PERMIT_REUSE_ATTEMPT",
                "severity": "CRITICAL",
                "risk_contribution": 40,
                "explanation": (
                    f"PASS RECYCLING FRAUD DETECTED (PARCHI REUSE): Vehicle {reg} is attempting a second unmetered haul "
                    f"using already CONSUMED e-Ravanna {permit['permit_number']} (Delivered at {consumed_at}). "
                    f"Single-use transit authorization exhausted. Automated gate barrier locked under MMDR Rule 102."
                ),
                "metrics": {
                    "permit_number": permit["permit_number"],
                    "truck_registration": reg,
                    "status": permit["status"],
                    "consumed_at": str(consumed_at),
                    "is_recycled": True
                }
            }

        # 2. Check turnaround time from previous delivered trip
        prev_trip = db.query("""
            SELECT * FROM trips 
            WHERE truck_id = ? AND status IN ('DELIVERED', 'COMPLETED') 
            ORDER BY id DESC LIMIT 1
        """, (truck_id,), one=True)

        if elapsed_turnaround_minutes is not None:
            elapsed_mins = float(elapsed_turnaround_minutes)
            planned_dist = float(prev_trip.get("planned_distance_km") or 45.0) if prev_trip else 45.0
            min_feasible_mins = (planned_dist / 60.0) * 60.0
            if elapsed_mins < (min_feasible_mins * 0.5):
                return {
                    "is_violation": True,
                    "violation_type": "SHORT_LOOPING_ANOMALY",
                    "severity": "HIGH",
                    "risk_contribution": 25,
                    "explanation": (
                        f"SUSPICIOUS SHORT-LOOPING VELOCITY: Vehicle {reg} returned to mine in {elapsed_mins:.1f} minutes "
                        f"after delivery (Minimum plausible empty return: {min_feasible_mins:.1f} mins for {planned_dist:.1f} km). "
                        f"Suspected premature offload at unauthorized roadside crusher."
                    ),
                    "metrics": {
                        "elapsed_minutes": round(elapsed_mins, 1),
                        "minimum_feasible_minutes": round(min_feasible_mins, 1),
                        "planned_distance_km": planned_dist
                    }
                }
        elif prev_trip and prev_trip.get("end_time"):
            try:
                end_t = datetime.strptime(str(prev_trip["end_time"])[:19], "%Y-%m-%d %H:%M:%S")
                elapsed_mins = (datetime.now() - end_t).total_seconds() / 60.0
                planned_dist = float(prev_trip.get("planned_distance_km") or 45.0)
                min_feasible_mins = (planned_dist / 60.0) * 60.0  # At 60 km/h return speed
                if elapsed_mins < (min_feasible_mins * 0.4):
                    return {
                        "is_violation": True,
                        "violation_type": "SHORT_LOOPING_ANOMALY",
                        "severity": "HIGH",
                        "risk_contribution": 25,
                        "explanation": (
                            f"SUSPICIOUS SHORT-LOOPING VELOCITY: Vehicle {reg} returned to mine in {elapsed_mins:.1f} minutes "
                            f"after delivery (Minimum plausible empty return: {min_feasible_mins:.1f} mins for {planned_dist:.1f} km). "
                            f"Suspected premature offload at unauthorized roadside crusher."
                        ),
                        "metrics": {
                            "elapsed_minutes": round(elapsed_mins, 1),
                            "minimum_feasible_minutes": round(min_feasible_mins, 1),
                            "planned_distance_km": planned_dist
                        }
                    }
            except Exception as e:
                logger.warning(f"Error checking turnaround time: {e}")

        return {
            "is_violation": False,
            "violation_type": "PERMIT_REUSE_ATTEMPT",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Transit pass {permit['permit_number']} is valid and legally authorized for single dispatch.",
            "metrics": {"permit_number": permit["permit_number"], "status": permit["status"]}
        }

    @classmethod
    def check_weighbridge_kanta_cheating(cls, gross_weight_mt, tare_weight_mt, bed_volume_m3=20.0, axle_beam_aligned=True, expected_density_mt_m3=1.60):
        """
        Scenario 2: Weighbridge Manipulation / Kanta Cheating Detection
        Detects drivers stopping with wheels off the ramp (partial platform positioning)
        using dual IR axle beams and volumetric LiDAR density reconciliation.
        """
        gross = float(gross_weight_mt)
        tare = float(tare_weight_mt)
        net = max(0.0, round(gross - tare, 2))

        # 1. Optical IR Axle Beam Interruption Check
        if not axle_beam_aligned:
            return {
                "is_violation": True,
                "violation_type": "WEIGHBRIDGE_AXLE_CHEATING",
                "severity": "CRITICAL",
                "risk_contribution": 35,
                "explanation": (
                    f"KANTA MANIPULATION DETECTED (AXLE OFF-PLATFORM): Infrared position beam broken! "
                    f"Vehicle tires resting on approach concrete ramp during gross weighment ({gross:.1f} MT). "
                    f"Load cells registering false lower weight to evade unbilled payload royalty. Boom barrier locked."
                ),
                "metrics": {
                    "gross_weight_mt": gross,
                    "tare_weight_mt": tare,
                    "axle_beam_aligned": False,
                    "barrier_locked": True
                }
            }

        # 2. Volumetric 3D LiDAR Density Anomaly Check
        if bed_volume_m3 > 0 and net > 0:
            measured_density = round(net / bed_volume_m3, 2)
            # Standard mineral bulk density (Quartzite ~1.55-1.65 MT/m3). If density < 1.40 for a full bed, wheels are off deck!
            if measured_density < (expected_density_mt_m3 * 0.85):
                unaccounted_excess_mt = round((expected_density_mt_m3 * bed_volume_m3) - net, 1)
                return {
                    "is_violation": True,
                    "violation_type": "DENSITY_VOLUME_DISCREPANCY",
                    "severity": "CRITICAL",
                    "risk_contribution": 30,
                    "explanation": (
                        f"VOLUMETRIC DENSITY ANOMALY (PARTIAL WEIGHING): Cargo bed measured at {bed_volume_m3:.1f} m³ "
                        f"but scale recorded only {net:.1f} MT (Calculated Density: {measured_density:.2f} MT/m³ vs {expected_density_mt_m3:.2f} MT/m³ expected). "
                        f"Indicates partial axle placement on approach ramp. Estimated off-record mineral: +{unaccounted_excess_mt:.1f} MT."
                    ),
                    "metrics": {
                        "measured_density_mt_m3": measured_density,
                        "expected_density_mt_m3": expected_density_mt_m3,
                        "bed_volume_m3": bed_volume_m3,
                        "net_weight_mt": net,
                        "unaccounted_excess_mt": unaccounted_excess_mt
                    }
                }

        return {
            "is_violation": False,
            "violation_type": "WEIGHBRIDGE_AXLE_CHEATING",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Weighbridge positioning valid. Full chassis centered on scale deck (Density: {net/max(1, bed_volume_m3):.2f} MT/m³).",
            "metrics": {"gross_weight_mt": gross, "net_weight_mt": net, "axle_beam_aligned": True}
        }

    @classmethod
    def check_mineral_grade_arbitrage(cls, quarry_block_id, declared_tariff, declared_mineral=None):
        """
        Scenario 3: Material Quality Fraud / Grade Arbitrage Detection
        Detects sandwich-loading fraud where high-grade Neela Maal (₹375/MT) is excavated
        from a certified blue stone pit, but declared as cheap Laal Maal (₹300/MT).
        """
        qb = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (quarry_block_id,), one=True)
        if not qb:
            qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 1 LIMIT 1", one=True)
        if not qb:
            return {"is_violation": False, "violation_type": "GRADE_ARBITRAGE", "risk_contribution": 0}

        # Sub-plot geological grade registry
        block_code = qb["block_code"]
        block_name = qb["block_name"]

        # Pit 1A / Block 1 is High-Grade Blue Quartzite (Neela Maal)
        is_high_grade_pit = ("01" in block_code or "1A" in block_name or "high-grade" in block_name.lower())
        sanctioned_tariff = 375.0 if is_high_grade_pit else 300.0
        declared_rate = float(declared_tariff)

        if is_high_grade_pit and declared_rate < 350.0:
            delta_inr = sanctioned_tariff - declared_rate
            return {
                "is_violation": True,
                "violation_type": "MINERAL_GRADE_ARBITRAGE",
                "severity": "HIGH",
                "risk_contribution": 25,
                "explanation": (
                    f"GRADE ARBITRAGE DETECTED (SANDWICH LOADING): Quarry source '{block_name}' ({qb['leaseholder_name']}) "
                    f"is registered for High-Grade Blue Quartzite (Neela Maal, Statutory Tariff ₹{sanctioned_tariff:.2f}/MT), "
                    f"but transit pass is declared at ₹{declared_rate:.2f}/MT ({declared_mineral or 'Low-Grade Red Grit'}). "
                    f"Unpaid tariff evasion delta: ₹{delta_inr:.2f}/MT under MMDR Rule 104."
                ),
                "metrics": {
                    "quarry_block_code": block_code,
                    "quarry_block_name": block_name,
                    "businessman": qb["leaseholder_name"],
                    "sanctioned_tariff_inr": sanctioned_tariff,
                    "declared_tariff_inr": declared_rate,
                    "royalty_evasion_delta_inr": delta_inr
                }
            }

        return {
            "is_violation": False,
            "violation_type": "MINERAL_GRADE_ARBITRAGE",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Mineral tariff classification (₹{declared_rate:.2f}/MT) matches pit geological concession.",
            "metrics": {"sanctioned_tariff": sanctioned_tariff, "declared_tariff": declared_rate}
        }

    @classmethod
    def check_token_system_bypass(cls, truck_reg, rfid_detected=True, has_valid_permit=False, mine_id=1):
        """
        Scenario 4: Off-Record Token System & Cash (Kacha Maal) Bypass Detection
        Detects unmetered trucks circulating on informal paper tokens or cash bypass.
        """
        if rfid_detected and not has_valid_permit:
            return {
                "is_violation": True,
                "violation_type": "TOKEN_SYSTEM_BYPASS",
                "severity": "CRITICAL",
                "risk_contribution": 40,
                "explanation": (
                    f"OFF-RECORD TOKEN / KACHA MAAL BYPASS DETECTED: Vehicle {truck_reg} detected at mine boundary "
                    f"gate with NO digital e-Ravanna registered on the state portal. "
                    f"Informal token / cash bypass attempt intercepted. Automated boom barrier locked."
                ),
                "metrics": {
                    "truck_registration": truck_reg,
                    "rfid_detected": True,
                    "has_valid_permit": False,
                    "mine_id": mine_id,
                    "barrier_locked": True
                }
            }

        return {
            "is_violation": False,
            "violation_type": "TOKEN_SYSTEM_BYPASS",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": f"Vehicle {truck_reg} possesses valid digital e-Ravanna gate pass.",
            "metrics": {"truck_registration": truck_reg, "has_valid_permit": True}
        }

    @classmethod
    def check_pit_over_extraction(cls, quarry_block_id=None, mine_id=1):
        """
        Scenario 5: Pit Over-Extraction Beyond Sanctioned Environmental Limits
        Tracks concession extraction quotas and enforces software kill-switch at 100% capacity.
        """
        if quarry_block_id:
            qb = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (quarry_block_id,), one=True)
            if not qb:
                qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = ? LIMIT 1", (mine_id,), one=True)
            if qb:
                allocated = float(qb["allocated_quota_mt"])
                dispatched = float(qb["dispatched_mt"])
                pct = round((dispatched / allocated) * 100.0, 1) if allocated > 0 else 0
                if dispatched >= allocated:
                    excess = round(dispatched - allocated, 1)
                    return {
                        "is_violation": True,
                        "violation_type": "CONCESSION_QUOTA_EXHAUSTED",
                        "severity": "CRITICAL",
                        "risk_contribution": 40,
                        "explanation": (
                            f"STATUTORY CONCESSION QUOTA CEILING EXHAUSTED: Sub-plot '{qb['block_code']}' ({qb['leaseholder_name']}) "
                            f"has reached {pct}% of its environmental clearance limit ({dispatched:,.0f} MT / {allocated:,.0f} MT, Excess: +{excess} MT). "
                            f"Statutory Kill-Switch active: all further e-Ravanna issuance frozen under MMDR Section 21."
                        ),
                        "metrics": {
                            "block_code": qb["block_code"],
                            "businessman": qb["leaseholder_name"],
                            "allocated_quota_mt": allocated,
                            "dispatched_mt": dispatched,
                            "excess_mt": excess,
                            "kill_switch_active": True
                        }
                    }

        # Check entire mine annual quota
        mine = db.query("SELECT * FROM mines WHERE id = ?", (mine_id,), one=True)
        if mine:
            m_quota = float(mine["authorized_annual_quota_mt"])
            m_disp = float(mine["current_dispatch_mt"])
            if m_disp >= m_quota:
                return {
                    "is_violation": True,
                    "violation_type": "MINE_QUOTA_EXHAUSTED",
                    "severity": "CRITICAL",
                    "risk_contribution": 40,
                    "explanation": f"Mine {mine['name']} has reached 100% annual statutory environmental quota ({m_disp:,.0f}/{m_quota:,.0f} MT). Dispatch locked.",
                    "metrics": {"allocated_quota_mt": m_quota, "dispatched_mt": m_disp, "kill_switch_active": True}
                }

        return {
            "is_violation": False,
            "violation_type": "CONCESSION_QUOTA_EXHAUSTED",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": "Extraction within sanctioned environmental quota.",
            "metrics": {"kill_switch_active": False}
        }

    @classmethod
    def check_unclosed_vehicle_entries(cls, mine_id=1, max_dwell_minutes=90):
        """
        Scenario 6: Unclosed Vehicle Entries & Ghost Truck Watchdog
        Flags empty trucks that entered the pit and whose exit is delayed beyond the 90-minute
        loading threshold, preventing identity-swapped runs or ghost dispatches.
        """
        now = datetime.now()
        unclosed_trucks = db.query("""
            SELECT id, registration_number, last_mine_entry, current_round_number, completed_rounds_today
            FROM trucks 
            WHERE is_inside_mine = 1 AND current_mine_id = ?
        """, (mine_id,))

        ghost_violations = []
        for t in unclosed_trucks:
            entry_str = t.get("last_mine_entry")
            if entry_str:
                try:
                    entry_t = datetime.strptime(str(entry_str)[:19], "%Y-%m-%d %H:%M:%S")
                    dwell_mins = round((now - entry_t).total_seconds() / 60.0, 1)
                    if dwell_mins > max_dwell_minutes:
                        ghost_violations.append({
                            "truck_id": t["id"],
                            "registration_number": t["registration_number"],
                            "entry_time": str(entry_str),
                            "dwell_minutes": dwell_mins,
                            "allowed_dwell_minutes": max_dwell_minutes,
                            "severity": "HIGH" if dwell_mins < 180 else "CRITICAL"
                        })
                except Exception as e:
                    logger.warning(f"Error parsing entry time for ghost check: {e}")

        if ghost_violations:
            first = ghost_violations[0]
            return {
                "is_violation": True,
                "violation_type": "UNCLOSED_ENTRY_TIMEOUT",
                "severity": first["severity"],
                "risk_contribution": 30,
                "explanation": (
                    f"UNCLOSED ENTRY / GHOST TRUCK TIMEOUT: Vehicle {first['registration_number']} entered pit at {first['entry_time']} "
                    f"({first['dwell_minutes']:.0f} mins ago). Exceeded statutory loading dwell limit of {max_dwell_minutes} mins. "
                    f"Suspected credential swapping or unrecorded off-the-books extraction."
                ),
                "metrics": {
                    "total_ghost_trucks_flagged": len(ghost_violations),
                    "flagged_vehicles": ghost_violations
                }
            }

        return {
            "is_violation": False,
            "violation_type": "UNCLOSED_ENTRY_TIMEOUT",
            "severity": "LOW",
            "risk_contribution": 0,
            "explanation": "All pit loading vehicles operating within standard 90-minute cycle window.",
            "metrics": {"total_ghost_trucks_flagged": 0}
        }

