"""
Unit Tests for SmartMineGuard Deterministic Detection & Risk Scoring Engines
Ensures 100% deterministic rule enforcement with NO AI/ML dependencies.
"""
import unittest
from datetime import datetime, timedelta
from services.detection import DetectionEngine
from services.risk_engine import RiskEngine


class TestDetectionEngine(unittest.TestCase):

    def test_weight_anomaly_normal(self):
        """Test compliant payload within 5% tolerance."""
        res = DetectionEngine.check_weight_anomaly(permitted_weight_mt=20.0, actual_net_weight_mt=20.8)
        self.assertFalse(res["is_violation"])
        self.assertEqual(res["risk_contribution"], 0)

    def test_weight_anomaly_overload(self):
        """Test significant overload (+11 MT as in demo vehicle HR26AB1234)."""
        res = DetectionEngine.check_weight_anomaly(
            permitted_weight_mt=20.0, 
            actual_net_weight_mt=31.0, 
            max_capacity_mt=28.0
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 30)
        self.assertIn("+11.0 MT", res["explanation"])
        self.assertTrue(res["metrics"]["is_capacity_exceeded"])

    def test_route_corridor_within_buffer(self):
        """Test truck traveling within allowed 350m corridor."""
        waypoints = [[27.5624, 76.6121], [27.7500, 76.5100], [28.2100, 76.8600]]
        # Point right on the line
        res = DetectionEngine.check_route_deviation(27.5624, 76.6121, waypoints, threshold_meters=350)
        self.assertFalse(res["is_violation"])
        self.assertEqual(res["risk_contribution"], 0)

    def test_route_corridor_deviation(self):
        """Test vehicle drifting far away from allowed highway corridor."""
        waypoints = [[27.5624, 76.6121], [27.7500, 76.5100], [28.2100, 76.8600]]
        # Point deviated substantially (~1.4km away)
        res = DetectionEngine.check_route_deviation(27.8520, 76.4530, waypoints, threshold_meters=350)
        self.assertTrue(res["is_violation"])
        self.assertIn(res["severity"], ["HIGH", "CRITICAL"])
        self.assertEqual(res["risk_contribution"], 20)
        self.assertIn("ROUTE DEVIATION DETECTED", res["explanation"])

    def test_gps_blackout_healthy(self):
        """Test recent GPS ping."""
        recent_time = datetime.now() - timedelta(seconds=15)
        res = DetectionEngine.check_gps_blackout(recent_time)
        self.assertFalse(res["is_violation"])
        self.assertEqual(res["risk_contribution"], 0)

    def test_gps_blackout_near_sensitive_zone(self):
        """Test prolonged blackout near restricted riverbed zone."""
        stale_time = datetime.now() - timedelta(minutes=15)
        res = DetectionEngine.check_gps_blackout(
            stale_time, 
            near_sensitive_zone=True, 
            zone_name="Sabi Riverbed Restricted Mining Zone"
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 35)  # 20 + 15 extra risk
        self.assertIn("SUSPICIOUS GPS BLACKOUT", res["explanation"])

    def test_impossible_transit(self):
        """Test physically impossible transit time (300 km in 30 min = 600 km/h)."""
        res = DetectionEngine.check_impossible_transit(distance_km=300.0, duration_minutes=30.0, max_legal_speed_kmh=85.0)
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 30)
        self.assertIn("IMPOSSIBLE TRANSIT DETECTED", res["explanation"])

    def test_production_dispatch_mismatch(self):
        """Test mine dispatch exceeding authorized environmental clearance quota."""
        # Mine 4 (Khetri Zone) has 60,000 MT quota and 64,200 MT dispatch in seed data
        res = DetectionEngine.check_production_dispatch_mismatch(mine_id=4)
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["risk_contribution"], 30)
        self.assertIn("PRODUCTION-DISPATCH MISMATCH", res["explanation"])

    def test_risk_score_normalization_and_breakdown(self):
        """Test risk score calculation, capping at 100, and factor explainability."""
        simulated_violations = [
            {"violation_type": "WEIGHT_ANOMALY", "risk_contribution": 30, "explanation": "Overweight +11 MT", "severity": "CRITICAL"},
            {"violation_type": "ROUTE_DEVIATION", "risk_contribution": 20, "explanation": "Deviated 1.4km", "severity": "HIGH"},
            {"violation_type": "GPS_BLACKOUT", "risk_contribution": 20, "explanation": "14 min blackout", "severity": "HIGH"},
            {"violation_type": "PERMIT_REUSE", "risk_contribution": 30, "explanation": "Re-presented consumed permit", "severity": "CRITICAL"},
            {"violation_type": "IMPOSSIBLE_TRANSIT", "risk_contribution": 30, "explanation": "Speed 120 km/h", "severity": "CRITICAL"}
        ]
        res = RiskEngine.calculate_risk(simulated_violations)
        self.assertEqual(res["score"], 100)  # Capped at 100 (raw was 130)
        self.assertEqual(res["level"], "CRITICAL")
        self.assertEqual(len(res["breakdown"]), 5)
        self.assertEqual(res["breakdown"][0]["rule"], "Weight Anomaly")
        self.assertEqual(res["breakdown"][0]["points"], 30)


if __name__ == "__main__":
    unittest.main()
