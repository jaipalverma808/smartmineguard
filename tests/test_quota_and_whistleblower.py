"""
Test Suite: Citizen Public Whistleblower Portal & Concession Quota/Lease Hard-Locks
SmartMineGuard System — Python unittest
"""
import unittest
from datetime import datetime, timedelta
from app import app
from services.db import db


class TestQuotaAndWhistleblower(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    # -------------------------------------------------------------
    # FEATURE 1: CITIZEN PUBLIC WHISTLEBLOWER PORTAL (JANTA VIGILANCE)
    # -------------------------------------------------------------

    def test_01_public_whistleblower_submission_anonymous(self):
        """Test public citizen can lodge illegal mining report anonymously without logging in."""
        payload = {
            "incident_type": "MIDNIGHT_RIVERBED_EXTRACTION",
            "incident_date": "2026-10-05 01:15",
            "location_name": "Sabi Riverbed Ghat #4, Kotputli Border",
            "latitude": 27.8485,
            "longitude": 76.4322,
            "description": "3 tippers hauling sand without number plates escorted by white SUV.",
            "is_anonymous": True
        }
        res = self.client.post("/api/public/whistleblower", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("SMG-TIP-", data["report_token"])
        token = data["report_token"]

        # Verify tip stored in citizen_reports
        tip = db.query("SELECT * FROM citizen_reports WHERE report_token = ?", (token,), one=True)
        self.assertIsNotNone(tip)
        self.assertEqual(tip["incident_type"], "MIDNIGHT_RIVERBED_EXTRACTION")
        self.assertEqual(tip["location_name"], "Sabi Riverbed Ghat #4, Kotputli Border")
        self.assertIsNone(tip["reporter_name"])

        # Verify high-priority CRITICAL alert automatically generated
        alert = db.query("SELECT * FROM alerts WHERE alert_type = 'CITIZEN_WHISTLEBLOWER' ORDER BY id DESC", one=True)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["severity"], "CRITICAL")
        self.assertIn(token, alert["description"])

    def test_02_public_whistleblower_tracking_endpoint(self):
        """Test public citizen can track enforcement progress using secret token."""
        # 1. Track seeded demo token
        res = self.client.get("/api/public/track-tip/SMG-TIP-849201")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["found"])
        self.assertEqual(data["report_token"], "SMG-TIP-849201")
        self.assertIn("SQUAD_DISPATCHED", data["status"])
        self.assertIn("Flying Squad", data["action_taken"])

        # 2. Non-existent token returns 404
        res_fake = self.client.get("/api/public/track-tip/SMG-TIP-999999")
        self.assertEqual(res_fake.status_code, 404)
        data_fake = res_fake.get_json()
        self.assertFalse(data_fake["found"])

    def test_03_public_mine_stats_includes_quota_watchdog(self):
        """Test public mine-stats endpoint discloses EC quota, usage %, and lease expiry."""
        res = self.client.get("/api/public/mine-stats?mine_id=1")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("authorized_annual_quota_mt", data)
        self.assertIn("current_dispatch_mt", data)
        self.assertIn("lease_expiry_date", data)
        self.assertIn("ec_clearance_number", data)
        self.assertIn("quota_percent", data)
        self.assertIn("is_quota_exhausted", data)

    # -------------------------------------------------------------
    # FEATURE 3: STATUTORY MMDR ANNUAL QUOTA & LEASE EXPIRY HARD-LOCKS
    # -------------------------------------------------------------

    def test_04_permit_hard_locked_on_expired_mine_lease(self):
        """Test generation of e-Rawaana is locked under Section 4A when mine lease is expired."""
        # Authenticate as operator
        self.login("operator1", "operator123")

        # Temporarily create/update a mine with an expired lease
        expired_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        db.execute("UPDATE mines SET lease_expiry_date = ? WHERE id = 1", (expired_date,))

        payload = {
            "mine_id": 1,
            "truck_id": 1,
            "driver_id": 1,
            "mineral": "Riverbed Sand & Gravel",
            "permitted_weight_mt": 25.0
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data.get("lock_type"), "LEASE_EXPIRED")
        self.assertEqual(data.get("code"), "STATUTORY_LEASE_EXPIRED")
        self.assertIn("STATUTORY LEASE HARD-LOCK", data.get("error", ""))

        # Restore valid lease date
        future_date = (datetime.now() + timedelta(days=400)).strftime("%Y-%m-%d")
        db.execute("UPDATE mines SET lease_expiry_date = ? WHERE id = 1", (future_date,))

    def test_05_permit_hard_locked_on_exhausted_annual_quota(self):
        """Test generation of e-Rawaana is locked under Section 4(1A) when annual EC quota is exhausted."""
        self.login("operator1", "operator123")

        # Set mine 1 current_dispatch_mt to near its quota
        mine = db.query("SELECT authorized_annual_quota_mt FROM mines WHERE id = 1", one=True)
        quota = float(mine["authorized_annual_quota_mt"] or 50000.0)
        db.execute("UPDATE mines SET current_dispatch_mt = ? WHERE id = 1", (quota - 5.0,))

        # Try to dispatch 25.0 MT (which exceeds quota by 20.0 MT)
        payload = {
            "mine_id": 1,
            "truck_id": 1,
            "driver_id": 1,
            "mineral": "Riverbed Sand & Gravel",
            "permitted_weight_mt": 25.0
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data.get("lock_type"), "QUOTA_EXHAUSTED")
        self.assertEqual(data.get("code"), "STATUTORY_QUOTA_EXHAUSTED")
        self.assertIn("STATUTORY QUOTA HARD-LOCK", data.get("error", ""))

        # Reset dispatch to safe level
        db.execute("UPDATE mines SET current_dispatch_mt = 12500.0 WHERE id = 1")

    def test_06_permit_hard_locked_on_submine_pit_quota_or_lease(self):
        """Test generation of e-Rawaana is locked when sub-mine pit quota or lease is exhausted."""
        self.login("operator1", "operator123")

        # Sub-mine pit QB-ALW-04 is already configured in DB with status QUOTA_EXHAUSTED and expired lease
        pit = db.query("SELECT id, mine_id FROM quarry_blocks WHERE block_code = 'QB-ALW-04'", one=True)
        self.assertIsNotNone(pit)

        payload = {
            "mine_id": pit["mine_id"],
            "quarry_block_id": pit["id"],
            "truck_id": 1,
            "driver_id": 1,
            "mineral": "Quartzite Aggregate",
            "permitted_weight_mt": 20.0
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn(data.get("lock_type"), ["LEASE_EXPIRED", "QUOTA_EXHAUSTED"])
        self.assertIn("STATUTORY", data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
