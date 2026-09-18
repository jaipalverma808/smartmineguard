"""
SmartMineGuard - Comprehensive Verification Test Suite
Tests all 22 verification requirements from Section 22 of the final correction specification.
"""
import unittest
import json
import time
from app import app
from services.db import db
from services.gps_simulator import is_within_india, simulator
from services.detection import DetectionEngine
from services.risk_engine import RiskEngine


class TestSmartMineGuardFinalEnhancements(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    # 1. Open / -> Public landing page appears without login
    def test_01_public_landing_page_accessible_without_login(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("SmartMineGuard", html)
        self.assertIn("Mining &amp; Mineral Transport Monitoring System", html)
        self.assertIn("Deterministic &amp; Rule-Based Verification System", html)

    # 2. Confirm no security/enforcement information is visible publicly
    def test_02_no_security_enforcement_info_visible_publicly(self):
        res = self.client.get("/")
        html = res.data.decode("utf-8")
        # Ensure sensitive operational terms are not leaked
        self.assertNotIn("ALT-2026-", html)
        self.assertNotIn("risk_score", html)
        self.assertNotIn("GPS Blackout", html)
        self.assertNotIn("investigations", html.lower())
        self.assertNotIn("officer notes", html.lower())
        self.assertNotIn("suspicious truck", html.lower())

    # 3. Confirm public search works for Vehicle Number, e-Rawaana, ISTP
    def test_03_public_search_functionality(self):
        # By Vehicle Number
        res = self.client.get("/api/public/search?search_type=Vehicle Number&q=DL1LA9022")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertEqual(data["record"]["vehicle_number"], "DL1LA9022")
        self.assertNotIn("risk_score", data["record"])
        self.assertNotIn("current_lat", data["record"])

        # By e-Rawaana Number
        res = self.client.get("/api/public/search?search_type=e-Rawaana Number&q=SMG-2026-00125")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertEqual(data["record"]["pass_number"], "SMG-2026-00125")

        # By ISTP Number
        res = self.client.get("/api/public/search?search_type=ISTP Number&q=TRP-2026-00124")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])

    # 4 & 5. Mine selector and public statistics
    def test_04_05_mine_selector_and_public_statistics(self):
        res = self.client.get("/api/public/mine-stats?mine_id=1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["mine_id"], 1)
        self.assertIn("Aravalli", data["name"])
        self.assertIn("active_trucks", data)
        self.assertIn("active_permits", data)
        self.assertIn("today_dispatch_mt", data)
        # Verify no sensitive enforcement data
        self.assertNotIn("risk_score", data)
        self.assertNotIn("alerts", data)

    # 6. Open /login -> NO demo usernames/passwords displayed
    def test_06_login_page_has_no_credentials_displayed(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertNotIn("admin123", html)
        self.assertNotIn("officer123", html)
        self.assertNotIn("operator123", html)
        self.assertNotIn("demo credentials", html.lower())

    # 7. Login as ADMIN -> Admin Command Center
    def test_07_login_as_admin(self):
        login_res = self.login("admin", "admin123")
        self.assertEqual(login_res.status_code, 302)
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Admin Command Center", html)
        self.assertIn("Master Data Registry", html)
        self.client.get("/logout")

    # 8. Login as OFFICER -> Enforcement Command Center
    def test_08_login_as_officer(self):
        login_res = self.login("officer1", "officer123")
        self.assertEqual(login_res.status_code, 302)
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Enforcement Command", html)
        self.client.get("/logout")

    # 9. Login as OPERATOR -> Mining Operations Dashboard
    def test_09_login_as_operator(self):
        login_res = self.login("operator1", "operator123")
        self.assertEqual(login_res.status_code, 302)
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Mine Operations", html)
        self.client.get("/logout")

    # 10. Verify operator cannot access another operator's truck by changing URL ID (403 Forbidden)
    def test_10_operator_cross_tenant_truck_access_forbidden(self):
        self.login("operator1", "operator123")
        # Truck 2 (RJ14GA5521) belongs to Mine 2 (Kotputli / Shree Cement), while operator1 owns Mine 1
        res = self.client.get("/trucks/2")
        self.assertEqual(res.status_code, 403)
        # API check also returns 403
        res_api = self.client.get("/api/trucks/2")
        self.assertEqual(res_api.status_code, 403)
        self.client.get("/logout")

    # 11. Verify officer cannot access user management or master data creation
    def test_11_officer_cannot_manage_users_or_master_data(self):
        self.login("officer1", "officer123")
        # User management web route redirects / blocks officer
        res = self.client.get("/admin/users", follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        # CRUD post returns 403
        res_crud = self.client.post("/api/crud/mines", json={"name": "Illegal Mine"}, headers={"Content-Type": "application/json"})
        self.assertEqual(res_crud.status_code, 403)
        self.client.get("/logout")

    # 12. Verify admin can access system-wide data
    def test_12_admin_system_wide_data_management_access(self):
        self.login("admin", "admin123")
        res = self.client.get("/admin/data")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Master Data &amp; Regulatory Registry Management", html)
        self.assertIn("Mines &amp; Leases", html)
        self.assertIn("Trucks Fleet", html)
        self.client.get("/logout")

    # 13. Open Live GIS Map -> All simulated trucks must be inside India
    def test_13_india_only_gps_coordinates(self):
        self.login("admin", "admin123")
        res = self.client.get("/api/trucks")
        self.assertEqual(res.status_code, 200)
        trucks = res.get_json()
        for t in trucks:
            lat = t.get("current_lat")
            lng = t.get("current_lng")
            if lat and lng:
                self.assertTrue(
                    is_within_india(lat, lng),
                    f"Truck {t['registration_number']} coordinates ({lat}, {lng}) are OUTSIDE India!"
                )
        self.client.get("/logout")

    # 14. Select truck -> planned route, travelled route, route points, and metrics
    def test_14_truck_trip_route_visualization_api(self):
        self.login("admin", "admin123")
        res = self.client.get("/api/trucks/1/route")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("source_mine", data)
        self.assertIn("destination", data)
        self.assertIn("weighbridge", data)
        self.assertIn("travelled_route", data)
        self.assertIn("remaining_route", data)
        self.assertIn("metrics", data)
        m = data["metrics"]
        self.assertEqual(m["truck_number"], "HR26AB1234")
        self.assertGreater(m["route_distance_km"], 0)
        self.assertGreater(m["distance_travelled_km"], 0)
        self.client.get("/logout")

    # 15. Create a new truck via CRUD -> appears in fleet
    def test_15_create_new_truck_crud(self):
        self.login("admin", "admin123")
        reg_test = f"HR26ZZ{int(time.time()) % 10000:04d}"
        payload = {
            "registration_number": reg_test,
            "vehicle_type": "10-Wheeler Tipper Truck",
            "registered_owner": "Haryana Trans Logistics",
            "driver_name": "Deepak Yadav",
            "driver_phone": "+91 98123 99999",
            "tare_weight_mt": 11.5,
            "max_capacity_mt": 28.0,
            "assigned_mine_id": 1
        }
        res = self.client.post("/api/crud/trucks", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Verify truck exists in database
        truck = db.query("SELECT * FROM trucks WHERE registration_number = ?", (reg_test,), one=True)
        self.assertIsNotNone(truck)
        self.assertEqual(truck["registered_owner"], "Haryana Trans Logistics")
        # Clean up test truck & assigned driver so they do not pollute the database
        db.execute("DELETE FROM drivers WHERE assigned_truck_id = ?", (truck["id"],))
        db.execute("DELETE FROM trucks WHERE id = ?", (truck["id"],))
        self.client.get("/logout")

    # 16. Create a new permit via CRUD
    def test_16_create_new_permit_crud(self):
        self.login("admin", "admin123")
        payload = {
            "mine_id": 1,
            "truck_id": 1,
            "mineral": "Quartzite Aggregate",
            "permitted_weight_mt": 24.0,
            "destination_name": "Bhiwadi Industrial Crushing Zone",
            "buyer_name": "National Highway Authority Infra",
            "valid_hours": 12
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        permit_num = data["permit_number"]

        permit = db.query("SELECT * FROM permits WHERE permit_number = ?", (permit_num,), one=True)
        self.assertIsNotNone(permit)
        self.assertEqual(permit["permitted_weight_mt"], 24.0)
        self.client.get("/logout")

    # 17. Create a new trip via CRUD
    def test_17_create_new_trip_crud(self):
        self.login("admin", "admin123")
        # Fetch active permit (latest created in test 16)
        p = db.query("SELECT id FROM permits WHERE status = 'ACTIVE' ORDER BY id DESC LIMIT 1", one=True)
        payload = {
            "permit_id": p["id"],
            "planned_distance_km": 52.0
        }
        res = self.client.post("/api/crud/trips", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.client.get("/logout")

    # 18 & 19. Add weighment and trigger overweight detection
    def test_18_19_weighment_and_overload_detection(self):
        self.login("admin", "admin123")
        trip = db.query("SELECT tr.*, p.permitted_weight_mt FROM trips tr JOIN permits p ON p.id = tr.permit_id LIMIT 1", one=True)
        
        # Test legal weighment
        permitted = trip["permitted_weight_mt"]
        gross_legal = 11.5 + (permitted - 2.0)
        res_legal = self.client.post("/api/crud/weighments", json={
            "trip_id": trip["id"],
            "weighbridge_code": "WB-ALW-01",
            "gross_weight_mt": gross_legal,
            "tare_weight_mt": 11.5
        })
        self.assertEqual(res_legal.status_code, 200)
        self.assertFalse(res_legal.get_json()["is_overweight"])

        # Test OVERWEIGHT weighment (Net = 36.0 MT vs Permitted 20.0 MT -> +16.0 MT overload)
        gross_over = 11.5 + permitted + 10.0
        res_over = self.client.post("/api/crud/weighments", json={
            "trip_id": trip["id"],
            "weighbridge_code": "WB-ALW-01",
            "gross_weight_mt": gross_over,
            "tare_weight_mt": 11.5
        })
        self.assertEqual(res_over.status_code, 200)
        data_over = res_over.get_json()
        self.assertTrue(data_over["is_overweight"])
        self.assertTrue(data_over["alert_created"])

        # Verify alert was inserted into alerts table
        alert = db.query("SELECT * FROM alerts WHERE trip_id = ? AND alert_type = 'WEIGHT_ANOMALY' ORDER BY id DESC LIMIT 1", (trip["id"],), one=True)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["severity"], "CRITICAL")
        self.client.get("/logout")

    # 20 & 21. Add production and dispatch -> Opening + Production - Dispatch = Current Stock
    def test_20_21_stock_mass_balance_reconciliation(self):
        self.login("admin", "admin123")
        mine_id = 1
        opening = 4200.0
        prod = 500.0
        disp = 300.0
        expected_closing = opening + prod - disp  # 4400.0

        payload = {
            "mine_id": mine_id,
            "mineral": "Quartzite",
            "record_date": "2026-09-12",
            "opening_stock_mt": opening,
            "production_mt": prod,
            "dispatch_mt": disp
        }
        res = self.client.post("/api/crud/stock-production", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["closing_stock_mt"], expected_closing)

        # Check mine current stock in database
        mine = db.query("SELECT current_stock_mt FROM mines WHERE id = ?", (mine_id,), one=True)
        self.assertEqual(mine["current_stock_mt"], expected_closing)
        
        # Clean up created record so other tests are unaffected
        if "record_id" in data:
            db.execute("DELETE FROM stock_production WHERE id = ?", (data["record_id"],))
        self.client.get("/logout")

    # 22. Existing engines (detection, risk, simulator, reports)
    def test_22_existing_engines_operational(self):
        # Detection Engine
        res_det = DetectionEngine.check_weight_anomaly(20.0, 31.0, 28.0)
        self.assertTrue(res_det["is_violation"])
        self.assertEqual(res_det["violation_type"], "WEIGHT_ANOMALY")

        # Risk Engine
        risk = RiskEngine.calculate_risk([res_det])
        self.assertGreater(risk["score"], 0)

        # Simulator step
        step_res = simulator.step_simulation()
        self.assertIsInstance(step_res, list)

        # Evidence dossier generation
        from services.report_generator import generate_evidence_pdf
        pdf_path = generate_evidence_pdf(1, "SMG-2026-00041")
        self.assertIsNotNone(pdf_path)


if __name__ == "__main__":
    unittest.main()
