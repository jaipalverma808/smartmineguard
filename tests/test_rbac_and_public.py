"""
Test Suite: Role-Based Access Control (RBAC) & Public Home Portal
SmartMineGuard System — Python unittest
"""
import unittest
from app import app
from services.db import db


class TestSmartMineGuardRBAC(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    def test_1_public_home_page_accessible_unauthenticated(self):
        """Test that a logged-out visitor can open / and read public info without login."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("SmartMineGuard", html)
        self.assertIn("Mining &amp; Mineral Transport Monitoring System", html)
        self.assertIn("Public Mineral Transit Verification", html)
        self.assertIn("How It Works", html)
        self.assertIn("About SmartMineGuard", html)
        self.assertIn("Login", html)
        # Ensure sensitive operational records are NOT exposed in raw public home HTML
        self.assertNotIn("ALT-2026-00101", html)
        self.assertNotIn("risk_score", html)
        self.assertNotIn("GPS Blackout", html)

    def test_2_unauthenticated_visitor_blocked_from_protected_routes(self):
        """Test that logged-out visitors cannot access secured routes."""
        for path in ["/dashboard", "/trucks", "/permits", "/trips", "/alerts", "/investigations", "/officer", "/admin/users"]:
            res = self.client.get(path, follow_redirects=False)
            self.assertEqual(res.status_code, 302, f"Expected 302 redirect for {path}")
            self.assertIn("/login", res.headers["Location"])

        # Test secured API unauthenticated returns 401
        res = self.client.get("/api/trucks")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json["error"], "Authentication required")

    def test_3_public_search_api_whitelisting_and_types(self):
        """Test public search endpoint for all 5 search types and strict field whitelisting."""
        # 1. e-Rawaana Number
        res = self.client.get("/api/public/search?search_type=e-Rawaana Number&q=SMG-2026-00125")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        rec = data["record"]
        self.assertEqual(rec["pass_number"], "SMG-2026-00125")
        self.assertEqual(rec["vehicle_number"], "HR26AB1234")
        self.assertIn("Quartzite", rec["mineral"])
        self.assertIn("MT", rec["permitted_quantity_mt"])

        # 2. Vehicle Number
        res = self.client.get("/api/public/search?search_type=Vehicle Number&q=HR26AB1234")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertEqual(data["record"]["vehicle_number"], "HR26AB1234")

        # 3. ISTP Number
        res = self.client.get("/api/public/search?search_type=ISTP Number&q=ISTP-2026-00412")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertIn("ISTP", data["record"]["pass_type"])

        # 4. ROP Number
        res = self.client.get("/api/public/search?search_type=ROP Number&q=ROP-2026-00891")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertIn("ROP", data["record"]["pass_type"])

        # 5. MTP Number
        res = self.client.get("/api/public/search?search_type=MTP Number&q=MTP-2026-00567")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertIn("MTP", data["record"]["pass_type"])

        # 6. Non-Existent Record
        res = self.client.get("/api/public/search?search_type=e-Rawaana Number&q=NON_EXISTENT_99999")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["found"])
        self.assertEqual(data["message"], "No matching public record found.")

        # STRICT WHITELIST VERIFICATION: ensure sensitive fields are NEVER in response
        forbidden_keys = [
            "current_risk_score", "risk_score", "current_risk_level", "risk_reasons",
            "current_lat", "current_lng", "gps_points", "telemetry", "route_deviation",
            "alerts", "investigations", "officer", "password_hash", "driver_phone"
        ]
        for key in forbidden_keys:
            self.assertNotIn(key, rec, f"Forbidden sensitive key '{key}' found in public record!")

    def test_4_public_mine_stats_api(self):
        """Test public mine-stats endpoint returns safe operational data."""
        res = self.client.get("/api/public/mine-stats?mine_id=1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["mine_id"], 1)
        self.assertIn("Aravalli", data["name"])
        self.assertIn("active_trucks", data)
        self.assertIn("active_permits", data)
        self.assertIn("weighbridges", data)
        self.assertIn("weighbridge_status", data)
        self.assertIn("status", data)

        # Forbidden fields in mine stats
        self.assertNotIn("gps", data)
        self.assertNotIn("alerts", data)
        self.assertNotIn("officers", data)

        # Test invalid mine_id
        self.assertEqual(self.client.get("/api/public/mine-stats?mine_id=9999").status_code, 404)
        self.assertEqual(self.client.get("/api/public/mine-stats").status_code, 400)

    def test_5_authenticated_dashboards_do_not_contain_public_home_tab(self):
        """Confirm that 'Public Home' was removed from Admin, Officer, and Operator dashboard navigation."""
        # 1. Check Admin Dashboard Navigation
        self.login("admin", "admin123")
        res_admin = self.client.get("/dashboard")
        self.assertEqual(res_admin.status_code, 200)
        html_admin = res_admin.data.decode("utf-8")
        self.assertNotIn(">Public Home<", html_admin)
        self.assertNotIn(">Public Overview<", html_admin)
        self.assertIn("Admin Command", html_admin)
        self.client.get("/logout")

        # 2. Check Officer Dashboard Navigation
        self.login("officer1", "officer123")
        res_officer = self.client.get("/dashboard")
        self.assertEqual(res_officer.status_code, 200)
        html_officer = res_officer.data.decode("utf-8")
        self.assertNotIn(">Public Home<", html_officer)
        self.assertNotIn(">Public Overview<", html_officer)
        self.assertIn("Enforcement Center", html_officer)
        self.client.get("/logout")

        # 3. Check Operator Dashboard Navigation
        self.login("operator1", "operator123")
        res_operator = self.client.get("/dashboard")
        self.assertEqual(res_operator.status_code, 200)
        html_operator = res_operator.data.decode("utf-8")
        self.assertNotIn(">Public Home<", html_operator)
        self.assertNotIn(">Public Overview<", html_operator)
        self.assertIn("Mine Operations", html_operator)
        self.client.get("/logout")

    def test_6_admin_login_and_full_access(self):
        """Test admin login, access to admin command center, and admin user management."""
        res = self.login("admin", "admin123")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/dashboard", res.headers["Location"])

        # Verify admin dashboard
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Directorate HQ Executive Command", html)
        self.assertIn("Authorized State Mining Leases", html)

        # Verify admin can access user management
        res = self.client.get("/admin/users")
        self.assertEqual(res.status_code, 200)
        self.assertIn("User &amp; Role Management", res.data.decode("utf-8"))

        self.client.get("/logout")

    def test_7_officer_login_and_enforcement_access(self):
        """Test officer login, enforcement dashboard, and restrictions."""
        res = self.login("officer1", "officer123")
        self.assertEqual(res.status_code, 302)

        # Verify enforcement dashboard
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Field Enforcement Command Post", html)
        self.assertIn("High-Risk Interception Queue", html)

        # Officer cannot access admin user management
        res = self.client.get("/admin/users", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/dashboard", res.headers["Location"])

        self.client.get("/logout")

    def test_8_operator_login_and_scoping(self):
        """Test operator login, scoped mining dashboard, and strict isolation."""
        res = self.login("operator1", "operator123")
        self.assertEqual(res.status_code, 302)

        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Authorized Mine Leaseholder Portal", html)
        self.assertIn("Aravalli Quartzite", html)

        # Verify operator cannot access police alerts or admin users
        for blocked_path in ["/alerts", "/investigations", "/admin/users"]:
            res = self.client.get(blocked_path, follow_redirects=False)
            self.assertIn(res.status_code, (302, 403), f"Operator should be blocked from {blocked_path}")

        self.client.get("/logout")


if __name__ == "__main__":
    unittest.main()
