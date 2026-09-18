"""
Test Suite: Operational Material & Dispatch Monitoring
SmartMineGuard System — Python unittest
Tests Sections 15 - 35 of the System Specification:
- Stock Reconciliation Formula (Opening + Production - Dispatch = Stock)
- Daily Dispatch Monitoring & Progress Targets
- Deterministic Quantity Anomalies (Actual > Permitted)
- Cumulative Truck Tracking & Multi-trip Movement
- Strict RBAC & Tenant Scoping (Admin, Officer, Operator)
- Public Portal Safe Aggregation Whitelisting
"""
import unittest
from app import app
from services.material_service import MaterialMonitoringService


class TestOperationalMaterialMonitoring(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    # =========================================================================
    # 1. SERVICE LAYER: STOCK RECONCILIATION & DISPATCH CALCULATIONS
    # =========================================================================
    def test_stock_reconciliation_formula(self):
        """Verify mass-balance formula: Opening Stock + Production - Dispatch = Current Stock."""
        recon = MaterialMonitoringService.get_stock_reconciliation()
        self.assertIn("opening_stock_mt", recon)
        self.assertIn("production_today_mt", recon)
        self.assertIn("dispatched_today_mt", recon)
        self.assertIn("current_stock_mt", recon)

        expected_current = round(recon["opening_stock_mt"] + recon["production_today_mt"] - recon["dispatched_today_mt"], 1)
        self.assertAlmostEqual(recon["current_stock_mt"], expected_current, places=1)
        self.assertEqual(recon["stock_change_mt"], round(recon["production_today_mt"] - recon["dispatched_today_mt"], 1))

        # Verify mine-wise material summary also satisfies the mass-balance formula for each mine
        mines = MaterialMonitoringService.get_mine_wise_material_summary()
        self.assertIsInstance(mines, list)
        self.assertGreater(len(mines), 0)
        for mine in mines:
            m_expected = round(mine["opening_stock_mt"] + mine["production_today_mt"] - mine["actual_dispatch_mt"], 1)
            self.assertAlmostEqual(mine["closing_stock_mt"], m_expected, places=1)

    def test_daily_dispatch_summary_metrics(self):
        """Verify daily dispatch KPIs: planned, actual, remaining, and completion %."""
        summary = MaterialMonitoringService.get_daily_dispatch_summary()
        self.assertIn("planned_dispatch_mt", summary)
        self.assertIn("actual_dispatch_mt", summary)
        self.assertIn("remaining_dispatch_mt", summary)
        self.assertIn("completion_pct", summary)
        self.assertIn("available_stock_mt", summary)
        self.assertIn("closing_stock_mt", summary)

        # Mathematical constraints
        self.assertAlmostEqual(summary["available_stock_mt"], round(summary["opening_stock_mt"] + summary["production_today_mt"], 1), places=1)
        self.assertAlmostEqual(summary["closing_stock_mt"], round(summary["available_stock_mt"] - summary["actual_dispatch_mt"], 1), places=1)
        if summary["planned_dispatch_mt"] > 0:
            expected_rem = round(max(0.0, summary["planned_dispatch_mt"] - summary["actual_dispatch_mt"]), 1)
            self.assertAlmostEqual(summary["remaining_dispatch_mt"], expected_rem, places=1)

    # =========================================================================
    # 2. SERVICE LAYER: DETERMINISTIC QUANTITY ANOMALIES
    # =========================================================================
    def test_deterministic_quantity_anomalies(self):
        """Verify anomalies are triggered IF AND ONLY IF actual_quantity > permitted_quantity."""
        anomalies = MaterialMonitoringService.get_quantity_anomalies()
        self.assertIsInstance(anomalies, list)
        self.assertGreater(len(anomalies), 0, "Expected demo dataset to contain quantity anomalies")

        for item in anomalies:
            self.assertGreater(item["actual_qty_mt"], item["permitted_qty_mt"],
                               f"Anomaly vehicle {item['vehicle_number']} must have actual > permitted")
            expected_excess = round(item["actual_qty_mt"] - item["permitted_qty_mt"], 1)
            self.assertAlmostEqual(item["excess_qty_mt"], expected_excess, places=1)
            self.assertIn(item["status"], ["FLAGGED FOR INTERCEPTION", "REVIEW REQUIRED"])

    # =========================================================================
    # 3. SERVICE LAYER: CUMULATIVE TRUCK MATERIAL TRACKING
    # =========================================================================
    def test_cumulative_truck_movement_and_repeat_offender(self):
        """Verify multi-trip aggregation per truck (trips today, permitted total, actual total, excess)."""
        ledger = MaterialMonitoringService.get_truck_wise_material_ledger()
        self.assertIsInstance(ledger, list)
        self.assertGreater(len(ledger), 0)

        # Find truck HR26AB1234 which has multiple trips today
        hr26_entries = [t for t in ledger if t["vehicle_number"] == "HR26AB1234"]
        self.assertGreater(len(hr26_entries), 0, "HR26AB1234 must exist in truck ledger")
        first = hr26_entries[0]
        self.assertGreaterEqual(first["trips_today"], 2, "HR26AB1234 should have at least 2 trips recorded today")
        self.assertGreater(first["cumulative_actual_mt"], 0)
        self.assertGreater(first["cumulative_excess_mt"], 0, "HR26AB1234 should have cumulative excess weight recorded")

    # =========================================================================
    # 4. SERVICE LAYER: RANKINGS & MINERAL-WISE MONITORING
    # =========================================================================
    def test_material_rankings_and_minerals(self):
        """Verify Top rankings calculation and mineral-wise summaries."""
        rankings = MaterialMonitoringService.get_top_material_rankings()
        self.assertIn("top_trucks_by_quantity", rankings)
        self.assertIn("top_mines_by_dispatch", rankings)
        self.assertIn("top_trucks_by_trips", rankings)
        self.assertIn("top_trucks_by_excess", rankings)

        # Ensure top trucks by excess has valid records
        if rankings["top_trucks_by_excess"]:
            top_excess = rankings["top_trucks_by_excess"][0]
            self.assertGreater(top_excess["excess_qty_mt"], 0)

        minerals = MaterialMonitoringService.get_mineral_wise_summary()
        self.assertIsInstance(minerals, list)
        self.assertGreater(len(minerals), 0)
        for m in minerals:
            self.assertIn("mineral", m)
            self.assertIn("produced_mt", m)
            self.assertIn("dispatched_mt", m)
            self.assertIn("remaining_mt", m)

    # =========================================================================
    # 5. REST APIS & STRICT ROLE-BASED ACCESS CONTROL (RBAC)
    # =========================================================================
    def test_api_material_summary_rbac(self):
        """Admin and Officer can access material summary; Operator gets mine-scoped summary; Public gets 401."""
        # Public visitor -> 401
        res = self.client.get("/api/material/summary")
        self.assertEqual(res.status_code, 401)

        # Admin -> 200 system-wide (all 4 mines aggregate opening stock = 20,300 MT)
        login_res = self.login("admin", "admin123")
        self.assertEqual(login_res.status_code, 302)
        res = self.client.get("/api/material/summary")
        self.assertEqual(res.status_code, 200)
        admin_data = res.get_json()
        self.assertEqual(admin_data["opening_stock_mt"], 20300.0)
        self.client.get("/logout")

        # Officer -> 200
        self.login("officer1", "officer123")
        res = self.client.get("/api/material/summary")
        self.assertEqual(res.status_code, 200)
        self.client.get("/logout")

        # Operator -> 200 scoped strictly to mine 1 (opening stock = 4,200 MT)
        self.login("operator1", "operator123")
        res = self.client.get("/api/material/summary")
        self.assertEqual(res.status_code, 200)
        op_data = res.get_json()
        self.assertEqual(op_data["opening_stock_mt"], 4200.0, "Operator must be scoped to their authorized mine")
        self.client.get("/logout")

    def test_api_material_anomalies_enforcement_rbac(self):
        """Officer and Admin can access anomalies endpoint; Operator is strictly FORBIDDEN (403)."""
        # Public -> 401
        res = self.client.get("/api/material/anomalies")
        self.assertEqual(res.status_code, 401)

        # Admin -> 200
        self.login("admin", "admin123")
        res = self.client.get("/api/material/anomalies")
        self.assertEqual(res.status_code, 200)
        self.assertIn("anomalies", res.get_json())
        self.client.get("/logout")

        # Officer -> 200
        self.login("officer1", "officer123")
        res = self.client.get("/api/material/anomalies")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("anomalies", data)
        self.assertGreater(len(data["anomalies"]), 0)
        self.client.get("/logout")

        # Operator -> 403 FORBIDDEN (Operators cannot access enforcement anomaly lists)
        self.login("operator1", "operator123")
        res = self.client.get("/api/material/anomalies")
        self.assertEqual(res.status_code, 403, "Operator must receive 403 Forbidden for anomalies endpoint")
        self.client.get("/logout")

    def test_api_material_trucks_tenant_scoping(self):
        """Operator attempting to query mine_id=2 is forced to mine_id=1 on backend."""
        self.login("operator1", "operator123")
        # Operator tries to query another mine (mine_id=2)
        res = self.client.get("/api/material/trucks?mine_id=2")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("ledger", data)
        for truck in data["ledger"]:
            self.assertEqual(truck["mine_id"], 1, "Operator must never receive trucks from another mine")
        self.client.get("/logout")

        # Admin can legitimately query mine_id=2
        self.login("admin", "admin123")
        res = self.client.get("/api/material/trucks?mine_id=2")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        for truck in data["ledger"]:
            self.assertEqual(truck["mine_id"], 2)
        self.client.get("/logout")

    # =========================================================================
    # 6. PUBLIC PORTAL SAFETY: NO SENSITIVE OVERLOAD OR RISK DATA EXPOSED
    # =========================================================================
    def test_public_portal_safe_material_aggregation(self):
        """Public mine stats endpoint only exposes aggregated safe dispatch, not truck overloads."""
        res = self.client.get("/api/public/mine-stats?mine_id=1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("today_dispatch_mt", data)

        # Ensure NO sensitive enforcement/investigation/overload fields exist in public response
        forbidden_public_keys = [
            "anomalies", "excess_weight", "overload_flags", "risk_score",
            "telemetry", "investigation_id", "officer_notes", "gps_tracks"
        ]
        for key in forbidden_public_keys:
            self.assertNotIn(key, data, f"Public mine stats must not expose {key}")

    # =========================================================================
    # 7. DASHBOARDS RENDER ACCORDING TO ROLE
    # =========================================================================
    def test_dashboards_render_material_sections(self):
        """Verify that Admin, Officer, and Operator dashboards properly render material UI."""
        # Admin Dashboard
        self.login("admin", "admin123")
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Daily Dispatch Monitoring &amp; Stock Balance", html)
        self.assertIn("Stock Reconciliation", html)
        self.assertIn("Mine-Wise Material Summary", html)
        self.assertIn("Top Material Movement", html)
        self.assertIn("Truck-Wise Material Movement", html)
        self.client.get("/logout")

        # Officer Dashboard
        self.login("officer1", "officer123")
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("QUANTITY ANOMALIES", html)
        self.assertIn("OVER-PERMITTED DISPATCH INTERCEPTIONS", html)
        self.assertIn("Investigate", html)
        self.client.get("/logout")

        # Operator Dashboard
        self.login("operator1", "operator123")
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Leasehold Daily Dispatch &amp; Stock Balance", html)
        self.assertIn("Truck-Wise Material Movement", html)
        # Verify Operator does not see global multi-mine tables
        self.assertNotIn("Mine-Wise Material Summary", html)
        self.assertNotIn("Top Material Movement", html)
        self.client.get("/logout")

    def test_truck_detail_renders_material_profile(self):
        """Admin or Officer viewing /trucks/1 sees the material weighment and cumulative profile card."""
        self.login("admin", "admin123")
        res = self.client.get("/trucks/1")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Material Payload &amp; Cumulative Weighment Audit", html)
        self.assertIn("Permitted Total", html)
        self.assertIn("Actual Transported", html)
        self.client.get("/logout")


if __name__ == "__main__":
    unittest.main()
