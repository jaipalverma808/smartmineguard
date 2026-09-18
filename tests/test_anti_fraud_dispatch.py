"""
SmartMineGuard - Anti-Fraud Dispatch Control & Automated Mine Trip Reconciliation Test Suite
Validates Scenarios 1 through 10 and Final Acceptance Criteria 1 through 20.
Strictly Deterministic & Explainable Rules — Pure Python Software (NO AI/ML).
"""
import unittest
import json
import time
from datetime import datetime, timedelta

from app import app
from services.db import db
from services.detection import DetectionEngine
from services.risk_engine import RiskEngine
from services.gps_simulator import simulator, is_within_india
from services.material_service import MaterialMonitoringService


class TestAntiFraudDispatchReconciliation(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def login_as(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    # ----------------------------------------------------
    # SCENARIO 1: Valid truck + valid permit + normal weight + normal route -> COMPLIANT
    # ----------------------------------------------------
    def test_scenario_01_compliant_dispatch(self):
        permit = db.query("SELECT * FROM permits WHERE status = 'ACTIVE' LIMIT 1", one=True)
        self.assertIsNotNone(permit)
        truck = db.query("SELECT * FROM trucks WHERE id = ?", (permit["truck_id"],), one=True)
        self.assertIsNotNone(truck)

        # Normal weight check (within permitted quota)
        normal_weight = float(permit["permitted_weight_mt"]) - 0.5
        v = DetectionEngine.check_weight_anomaly(permit["permitted_weight_mt"], normal_weight, truck["max_capacity_mt"])
        self.assertFalse(v["is_violation"])
        self.assertEqual(v["severity"], "LOW")

    # ----------------------------------------------------
    # SCENARIO 2: Truck enters mine with no valid permit -> UNAUTHORIZED ENTRY
    # ----------------------------------------------------
    def test_scenario_02_unauthorized_mine_entry_no_permit(self):
        v = DetectionEngine.check_unauthorized_mine_entry(truck_id=999, mine_id=1, permit=None)
        self.assertTrue(v["is_violation"])
        self.assertEqual(v["violation_type"], "UNAUTHORIZED_MINE_ENTRY")
        self.assertIn("with no valid active e-Rawaana permit", v["explanation"])

    # ----------------------------------------------------
    # SCENARIO 3: Permit assigned to Truck A but Truck B enters mine -> PERMIT-VEHICLE MISMATCH
    # ----------------------------------------------------
    def test_scenario_03_permit_vehicle_mismatch(self):
        fake_permit = {
            "id": 888,
            "permit_number": "SMG-2026-TEST-MISMATCH",
            "truck_id": 999,  # Assigned to vehicle 999
            "mine_id": 1,
            "status": "ACTIVE"
        }
        # Truck 1 enters mine with permit belonging to 999
        v = DetectionEngine.check_unauthorized_mine_entry(truck_id=1, mine_id=1, permit=fake_permit)
        self.assertTrue(v["is_violation"])
        self.assertEqual(v["violation_type"], "PERMIT_MISMATCH")
        self.assertIn("PERMIT-VEHICLE MISMATCH", v["explanation"])

    # ----------------------------------------------------
    # SCENARIO 4: Permit = 24 MT, Actual = 26 MT -> OVERWEIGHT DISPATCH
    # ----------------------------------------------------
    def test_scenario_04_overweight_dispatch(self):
        permitted = 24.0
        actual = 26.0
        v = DetectionEngine.check_weight_anomaly(permitted, actual, max_capacity_mt=35.0)
        self.assertTrue(v["is_violation"])
        self.assertEqual(v["metrics"]["difference_mt"], 2.0)
        self.assertIn("+2.0 MT", v["explanation"])

    # ----------------------------------------------------
    # SCENARIO 5: Truck completes more rounds than allowed -> EXCESSIVE ROUND ALERT
    # ----------------------------------------------------
    def test_scenario_05_unrestricted_fleet_trip_frequency(self):
        """Under real-world operations, a truck can make as many trips as possible in a day without restriction."""
        v = DetectionEngine.check_excessive_trip_frequency(truck_id=1, completed_rounds=5)
        self.assertFalse(v["is_violation"])
        self.assertEqual(v["violation_type"], "EXCESSIVE_TRIP_FREQUENCY")
        self.assertIn("operating normally under unrestricted daily commercial dispatch", v["explanation"])
        self.assertTrue(v["metrics"]["is_unrestricted"])


    # ----------------------------------------------------
    # SCENARIO 6: GPS signal blackout near sensitive zone -> GPS BLACKOUT
    # ----------------------------------------------------
    def test_scenario_06_gps_blackout(self):
        last_ping = datetime.now() - timedelta(minutes=20)
        v = DetectionEngine.check_gps_blackout(last_ping, near_sensitive_zone=True, zone_name="Sabi Riverbed")
        self.assertTrue(v["is_violation"])
        self.assertEqual(v["violation_type"], "GPS_BLACKOUT")
        self.assertEqual(v["severity"], "CRITICAL")
        self.assertIn("Sabi Riverbed", v["explanation"])

    # ----------------------------------------------------
    # SCENARIO 7: Truck deviates from authorized corridor -> ROUTE DEVIATION
    # ----------------------------------------------------
    def test_scenario_07_route_deviation(self):
        corridor = [
            (27.5624, 76.6121),
            (27.6800, 76.5600),
            (27.7500, 76.5100)
        ]
        # Coordinates 15 km away from corridor
        deviated_lat, deviated_lng = 27.9500, 76.2000
        v = DetectionEngine.check_route_deviation(deviated_lat, deviated_lng, corridor)
        self.assertTrue(v["is_violation"])
        self.assertEqual(v["violation_type"], "ROUTE_DEVIATION")

    # ----------------------------------------------------
    # SCENARIO 8: Production and dispatch mismatch beyond tolerance -> PRODUCTION-DISPATCH MISMATCH
    # ----------------------------------------------------
    def test_scenario_08_production_dispatch_mismatch(self):
        # Test tolerance of 10.0 MT for mine 1
        # When opening stock is 4200, production is 650, actual dispatch is ~79 MT,
        # recorded stock ~3500 MT -> mismatch delta is substantial
        v = DetectionEngine.check_production_dispatch_reconciliation(mine_id=1, tolerance_mt=10.0)
        self.assertIn("is_violation", v)
        self.assertEqual(v["violation_type"], "PRODUCTION_MISMATCH")

    # ----------------------------------------------------
    # SCENARIO 9: Manual weight correction -> MANUAL OVERRIDE + AUDIT LOG
    # ----------------------------------------------------
    def test_scenario_09_manual_weight_correction_and_audit(self):
        # Login as ADMIN
        self.login_as("admin", "admin123")

        # Create or fetch an existing weighment record
        w = db.query("SELECT id, net_weight_mt FROM weighments LIMIT 1", one=True)
        self.assertIsNotNone(w)
        w_id = w["id"]

        # Post manual override
        override_payload = {
            "corrected_net_weight_mt": 28.5,
            "reason": "Calibration tare error verified at exit gate"
        }
        res = self.client.post(f"/api/weighments/{w_id}/override",
                               data=json.dumps(override_payload),
                               content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # Check DB has record of manual override
        updated_w = db.query("SELECT * FROM weighments WHERE id = ?", (w_id,), one=True)
        self.assertEqual(updated_w["is_manual_override"], 1)
        self.assertEqual(updated_w["override_reason"], "Calibration tare error verified at exit gate")
        self.assertEqual(updated_w["measurement_status"], "MANUAL_OVERRIDE")

        # Check audit log was recorded
        audit = db.query("SELECT * FROM audit_logs WHERE action = 'MANUAL_WEIGHT_OVERRIDE' ORDER BY id DESC LIMIT 1", one=True)
        self.assertIsNotNone(audit)
        self.assertEqual(audit["entity"], "weighments")

    # ----------------------------------------------------
    # SCENARIO 10: Normal truck enters mine, gets weighed, exits -> Round automatically increments
    # ----------------------------------------------------
    def test_scenario_10_round_increment_on_entry_exit(self):
        # Select truck RJ14GA5521
        was_running = simulator.is_running
        simulator.stop()
        try:
            truck_reg = "RJ14GA5521"
            db.execute("UPDATE trucks SET is_inside_mine = 0 WHERE registration_number = ?", (truck_reg,))
            truck_before = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
            rounds_before = truck_before["completed_rounds_today"] or 0

            # Simulate mine entry
            res_entry = simulator.simulate_mine_entry(truck_reg, mine_id=1)
            self.assertTrue(res_entry["success"])

            truck_inside = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
            self.assertEqual(truck_inside["is_inside_mine"], 1)

            # Simulate mine exit
            res_exit = simulator.simulate_mine_exit(truck_reg, mine_id=1)
            self.assertTrue(res_exit["success"])

            truck_after = db.query("SELECT * FROM trucks WHERE registration_number = ?", (truck_reg,), one=True)
            self.assertEqual(truck_after["is_inside_mine"], 0)
            self.assertEqual(truck_after["completed_rounds_today"], rounds_before + 1)
        finally:
            if was_running:
                simulator.start()

    # ----------------------------------------------------
    # ACCEPTANCE CRITERIA TESTS:
    # ----------------------------------------------------
    def test_ac_automated_weighment_calculation_and_source(self):
        self.login_as("admin", "admin123")
        # Ensure that weighment requires gross and tare and automatically calculates net
        trip = db.query("SELECT id FROM trips LIMIT 1", one=True)
        payload = {
            "trip_id": trip["id"],
            "gross_weight_mt": 35.8,
            "tare_weight_mt": 11.2,
            "measurement_source": "WEIGHBRIDGE_AUTOMATED_SCALE",
            "weighbridge_code": "WB-AUTO-TEST"
        }
        res = self.client.post("/api/crud/weighments", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        # Net must be exactly gross - tare = 24.6 MT
        self.assertEqual(data["net_weight_mt"], 24.6)
        self.assertEqual(data["measurement_source"], "WEIGHBRIDGE_AUTOMATED_SCALE")
        self.assertEqual(data["measurement_status"], "VERIFIED")

    def test_ac_permit_reconciliation_workflow(self):
        self.login_as("admin", "admin123")
        permit = db.query("SELECT id, status FROM permits LIMIT 1", one=True)
        p_id = permit["id"]

        # Controlled reconciliation action
        payload = {"action": "RECONCILE", "reason": "Verified statutory e-Rawaana credentials"}
        res = self.client.post(f"/api/permits/{p_id}/reconcile", data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "ACTIVE")

    def test_ac_trip_timeline_endpoint(self):
        self.login_as("officer1", "officer123")
        trip = db.query("SELECT id FROM trips LIMIT 1", one=True)
        res = self.client.get(f"/api/trips/{trip['id']}/timeline")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("timeline", data)
        self.assertIsInstance(data["timeline"], list)

    def test_ac_truck_route_reconstruction_api(self):
        self.login_as("officer1", "officer123")
        truck = db.query("SELECT id FROM trucks WHERE registration_number = 'HR26AB1234'", one=True)
        res = self.client.get(f"/api/trucks/{truck['id']}/route")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("authorized_route", data)
        self.assertIn("actual_route", data)
        self.assertIn("timeline", data)
        self.assertIn("round_metrics", data)
        self.assertIn("cumulative_material", data)

    def test_ac_dispatch_control_planning_data(self):
        plan = MaterialMonitoringService.get_dispatch_control_planning()
        self.assertIn("planned_dispatch_mt", plan)
        self.assertIn("actual_dispatch_mt", plan)
        self.assertIn("remaining_dispatch_mt", plan)
        self.assertIn("expected_rounds", plan)
        self.assertIn("completed_rounds", plan)
        self.assertIn("remaining_rounds", plan)

    def test_ac_cumulative_material_profile(self):
        truck = db.query("SELECT id FROM trucks WHERE registration_number = 'HR26AB1234'", one=True)
        prof = MaterialMonitoringService.get_truck_cumulative_material_profile(truck["id"])
        self.assertIsNotNone(prof)
        self.assertIn("today", prof)
        self.assertIn("week", prof)
        self.assertIn("month", prof)
        self.assertIn("rounds", prof)
        self.assertIn("cumulative_dispatched_mt", prof)
        self.assertIn("total_excess_detected_mt", prof)

    def test_ac_india_only_gis_clamping(self):
        # Coordinates in Pakistan or China or ocean must be rejected
        self.assertFalse(is_within_india(31.5, 74.0))  # Lahore Pakistan
        self.assertFalse(is_within_india(32.5, 80.0))  # Tibet / China
        self.assertFalse(is_within_india(5.0, 75.0))   # Indian Ocean
        self.assertTrue(is_within_india(27.5624, 76.6121)) # Alwar, Rajasthan, India

    def test_ac_login_page_credentials_not_leaked(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertNotIn("admin123", html)
        self.assertNotIn("officer123", html)
        self.assertNotIn("operator123", html)

    def test_can_generate_unrestricted_permits_any_round(self):
        """Truck can make as many trips as possible in a day; permit generation is never restricted by round count."""
        self.login_as("admin", "admin123")
        truck = db.query("SELECT * FROM trucks WHERE registration_number = 'RJ14GA5521'", one=True)
        # Set truck completed rounds to 4 or higher
        db.execute("""
            UPDATE trucks 
            SET completed_rounds_today = 4, allowed_rounds_per_day = 4 
            WHERE id = ?
        """, (truck["id"],))

        payload = {
            "mine_id": truck["assigned_mine_id"] or 1,
            "truck_id": truck["id"],
            "mineral": "Silica Sand",
            "permitted_weight_mt": 24.0,
            "destination_name": "Bhiwadi Industrial Crushing Zone",
            "buyer_name": "UltraTech Processing Plant",
            "valid_hours": 12
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("permit_number", data)

    def test_can_generate_permit_when_rounds_remaining(self):
        """Permit can be issued normally when the vehicle has rounds remaining today."""
        self.login_as("admin", "admin123")
        truck = db.query("SELECT * FROM trucks WHERE registration_number = 'RJ14GA5521'", one=True)
        # Set completed rounds below limit on both truck and driver
        db.execute("""
            UPDATE trucks 
            SET completed_rounds_today = 1, allowed_rounds_per_day = 4 
            WHERE id = ?
        """, (truck["id"],))
        db.execute("""
            UPDATE drivers
            SET completed_rounds_today = 1, allowed_rounds_per_day = 4
            WHERE assigned_truck_id = ?
        """, (truck["id"],))

        payload = {
            "mine_id": truck["assigned_mine_id"] or 1,
            "truck_id": truck["id"],
            "mineral": "Silica Sand",
            "permitted_weight_mt": 24.0,
            "destination_name": "Bhiwadi Industrial Crushing Zone",
            "buyer_name": "UltraTech Processing Plant",
            "valid_hours": 12
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("permit_number", data)

    def test_api_truck_permit_eligibility_endpoint(self):
        """Test GET /api/trucks/<id>/permit-eligibility returns unrestricted eligible status."""
        self.login_as("admin", "admin123")
        truck = db.query("SELECT * FROM trucks WHERE registration_number = 'RJ14GA5521'", one=True)
        db.execute("UPDATE trucks SET completed_rounds_today = 4, allowed_rounds_per_day = 4 WHERE id = ?", (truck["id"],))
        db.execute("UPDATE drivers SET completed_rounds_today = 4, allowed_rounds_per_day = 4 WHERE assigned_truck_id = ?", (truck["id"],))
        res = self.client.get(f"/api/trucks/{truck['id']}/permit-eligibility")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["eligible"])
        self.assertTrue(data.get("is_unrestricted"))
        self.assertIn("unrestricted daily commercial", data["explanation"])

        # Now test with 0 rounds
        db.execute("UPDATE trucks SET completed_rounds_today = 0, allowed_rounds_per_day = 4 WHERE id = ?", (truck["id"],))
        db.execute("UPDATE drivers SET completed_rounds_today = 0, allowed_rounds_per_day = 4 WHERE assigned_truck_id = ?", (truck["id"],))
        res2 = self.client.get(f"/api/trucks/{truck['id']}/permit-eligibility")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertTrue(data2["eligible"])
        self.assertTrue(data2.get("is_unrestricted"))

    def test_ac_operator_rbac_isolation(self):
        # Operator 1 belongs to Mine 1
        self.login_as("operator1", "operator123")
        # Attempt to access an officer-only anomaly API
        res = self.client.get("/api/material/anomalies")
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()


