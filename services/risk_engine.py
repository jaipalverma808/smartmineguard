"""
SmartMineGuard - Explainable Rule-Based Risk Engine
STRICTLY PURE SOFTWARE — NO AI / NO ML.
Calculates 0-100 normalized risk score with transparent itemized reasons.
"""
import logging
from config import Config
from services.db import db

logger = logging.getLogger("smartmineguard.risk")


class RiskEngine:
    """
    Computes explainable, rule-based risk scores for mineral transport trips and vehicles.
    Risk Bands:
        0  - 30  : LOW (Green)
        31 - 60  : MEDIUM (Amber/Yellow)
        61 - 80  : HIGH (Orange)
        81 - 100 : CRITICAL (Red)
    """

    @staticmethod
    def calculate_risk(violations):
        """
        Takes a list of violation dicts (from DetectionEngine) and computes:
            - score (int: 0-100)
            - level (str: LOW, MEDIUM, HIGH, CRITICAL)
            - breakdown (list of dicts with rule, points, reason)
        """
        raw_score = 0
        breakdown = []

        for v in violations:
            points = v.get("risk_contribution", 0)
            v_type = v.get("violation_type", "VIOLATION")
            explanation = v.get("explanation", "")

            # Format human-readable rule title
            rule_title = v_type.replace("_", " ").title()
            
            raw_score += points
            breakdown.append({
                "rule": rule_title,
                "points": points,
                "reason": explanation,
                "severity": v.get("severity", "MEDIUM")
            })

        # Cap score at 100
        final_score = min(100, max(0, raw_score))

        # Categorize
        if final_score <= 30:
            level = "LOW"
        elif final_score <= 60:
            level = "MEDIUM"
        elif final_score <= 80:
            level = "HIGH"
        else:
            level = "CRITICAL"

        return {
            "score": final_score,
            "level": level,
            "raw_score": raw_score,
            "breakdown": breakdown,
            "factors_count": len(breakdown)
        }

    @classmethod
    def evaluate_and_update_trip_risk(cls, trip_id):
        """
        Evaluates active alerts and detections for a trip, computes new risk, and updates DB.
        If latest weighment is within legal limits (<= permitted), auto-resolves any open overweight alerts.
        Deduplicates active alerts by alert_type so identical repeated alerts don't falsely inflate risk.
        """
        # Check latest weighment for this trip
        latest_wb = db.query(
            "SELECT * FROM weighments WHERE trip_id = ? ORDER BY id DESC LIMIT 1",
            (trip_id,), one=True
        )
        if latest_wb:
            net_wt = latest_wb.get("net_weight_mt") or 0.0
            perm_wt = latest_wb.get("permitted_weight_mt") or 0.0
            is_manual = bool(latest_wb.get("is_manual_override"))
            if net_wt > 0 and perm_wt > 0 and net_wt <= perm_wt and not is_manual:
                db.execute(
                    "UPDATE alerts SET status = 'RESOLVED' WHERE trip_id = ? AND alert_type IN ('WEIGHT_ANOMALY', 'OVERWEIGHT_DISPATCH')",
                    (trip_id,)
                )

        alerts = db.query(
            "SELECT * FROM alerts WHERE trip_id = ? AND status NOT IN ('DISMISSED', 'RESOLVED', 'CLOSED') ORDER BY id DESC", 
            (trip_id,)
        )

        seen_types = set()
        violations = []
        for a in alerts:
            atype = a["alert_type"]
            if atype in seen_types:
                continue
            seen_types.add(atype)
            violations.append({
                "violation_type": atype,
                "risk_contribution": a["risk_score"],
                "explanation": a["description"],
                "severity": a["severity"]
            })

        risk_res = cls.calculate_risk(violations)
        
        # Update trip in database
        db.execute(
            "UPDATE trips SET risk_score = ?, risk_level = ? WHERE id = ?",
            (risk_res["score"], risk_res["level"], trip_id)
        )

        # Update associated truck
        trip = db.query("SELECT truck_id FROM trips WHERE id = ?", (trip_id,), one=True)
        if trip and trip["truck_id"]:
            db.execute(
                "UPDATE trucks SET current_risk_score = ?, current_risk_level = ? WHERE id = ?",
                (risk_res["score"], risk_res["level"], trip["truck_id"])
            )

        return risk_res
