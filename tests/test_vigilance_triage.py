"""
Unit tests for Hierarchical AI Triage & Admin Vigilance Audit System.
Tests:
1. Context-Aware AI Filtering (Highway Cellular Shadow vs Sensitive Zone Breach).
2. Officer Action Tracking & Anti-Collusion Escalation.
3. Admin Supervisory Audit (Confirm Clearance vs Flag for Vigilance Inquiry).
"""
import json
import unittest
from datetime import datetime, timedelta
from app import app
from services.db import db
from services.detection import DetectionEngine


class VigilanceTriageTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        db.run_auto_migrations()

    def test_01_context_aware_highway_shadow_vs_sensitive_zone(self):
        """AI must treat 5-minute highway signal drop as benign shadow, but escalate sensitive zones."""
        now = datetime.now()
        past_6m = (now - timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M:%S")

        # Case A: On highway corridor, no sensitive zone
        res_highway = DetectionEngine.check_gps_blackout(
            last_ping_time=past_6m,
            current_time=now,
            near_sensitive_zone=False
        )
        self.assertFalse(res_highway["is_violation"], "Highway cellular delay under 15m should not be a violation")
        self.assertEqual(res_highway["severity"], "LOW")
        self.assertEqual(res_highway["violation_type"], "NETWORK_BLINDSPOT")

        # Case B: Near sensitive riverbed zone
        res_riverbed = DetectionEngine.check_gps_blackout(
            last_ping_time=past_6m,
            current_time=now,
            near_sensitive_zone=True,
            zone_name="Sabi Riverbed Restricted Zone"
        )
        self.assertTrue(res_riverbed["is_violation"], "GPS blackout near protected zone must be an active violation")
        self.assertEqual(res_riverbed["severity"], "CRITICAL")
        self.assertEqual(res_riverbed["violation_type"], "GPS_BLACKOUT")

    def test_02_officer_dismiss_critical_alert_escalates_to_admin(self):
        """When an officer dismisses a critical alert, it must escalate to Admin Vigilance Queue with notes."""
        # Insert a mock critical alert
        alert_code = f"ALT-TEST-{int(datetime.now().timestamp())}"
        alert_id = db.execute("""
            INSERT INTO alerts (alert_code, alert_type, severity, risk_score, description, status, assigned_to_user_id)
            VALUES (?, 'ROUTE_DEVIATION', 'CRITICAL', 85, 'Vehicle deviated into prohibited riverbed buffer zone', 'NEW', 2)
        """, (alert_code,))

        # Login as Officer (user_id = 2, officer1)
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        officer_note = "Driver claimed GPS antenna connector was loose; verified physical challan at checkpost."
        res = self.client.post(f"/api/alerts/{alert_id}/action", json={
            "status": "DISMISSED",
            "remarks": officer_note
        })
        self.assertEqual(res.status_code, 200)

        # Check DB state
        updated = db.query("SELECT * FROM alerts WHERE id = ?", (alert_id,), one=True)
        self.assertEqual(updated["status"], "DISMISSED")
        self.assertEqual(updated["handled_by_user_id"], 2)
        self.assertEqual(updated["officer_remarks"], officer_note)
        self.assertEqual(updated["escalated_to_admin"], 1, "Critical dismissal must escalate to Admin")
        self.assertEqual(updated["admin_review_status"], "PENDING_VIGILANCE_REVIEW")

    def test_03_admin_confirm_supervisory_clearance(self):
        """Admin can audit and confirm an officer's field clearance."""
        alert_code = f"ALT-TEST-CONFIRM-{int(datetime.now().timestamp())}"
        alert_id = db.execute("""
            INSERT INTO alerts (alert_code, alert_type, severity, risk_score, description, status,
                                handled_by_user_id, action_taken, officer_remarks, escalated_to_admin, admin_review_status)
            VALUES (?, 'WEIGHT_ANOMALY', 'CRITICAL', 90, 'Gross scale overload +5 MT', 'DISMISSED',
                    2, 'DISMISSED', 'Verified tare recalibration on static scale', 1, 'PENDING_VIGILANCE_REVIEW')
        """, (alert_code,))

        # Login as Admin (user_id = 1, admin)
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"
            sess["username"] = "admin"

        res = self.client.post(f"/api/alerts/{alert_id}/admin_review", json={
            "decision": "CONFIRM",
            "notes": "Verified against tare audit ledger. Officer clearance approved."
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "CONFIRMED_BY_ADMIN")

        updated = db.query("SELECT * FROM alerts WHERE id = ?", (alert_id,), one=True)
        self.assertEqual(updated["admin_review_status"], "CONFIRMED_BY_ADMIN")
        self.assertEqual(updated["admin_reviewed_by"], 1)

    def test_04_admin_flag_inquiry_triggers_anti_corruption_case(self):
        """Admin rejecting suspicious officer clearance triggers an Anti-Corruption investigation case."""
        alert_code = f"ALT-TEST-FLAG-{int(datetime.now().timestamp())}"
        alert_id = db.execute("""
            INSERT INTO alerts (alert_code, alert_type, severity, risk_score, description, status,
                                handled_by_user_id, action_taken, officer_remarks, escalated_to_admin, admin_review_status)
            VALUES (?, 'UNAUTHORIZED_MINE_ENTRY', 'CRITICAL', 95, 'Unpermitted entry into Kotputli lease', 'DISMISSED',
                    2, 'DISMISSED', 'Officer stated driver made wrong turn', 1, 'PENDING_VIGILANCE_REVIEW')
        """, (alert_code,))

        # Login as Admin (user_id = 1)
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"
            sess["username"] = "admin"

        res = self.client.post(f"/api/alerts/{alert_id}/admin_review", json={
            "decision": "FLAG_INQUIRY",
            "notes": "Unacceptable explanation for unauthorized lease entry. Anti-Corruption Inquiry ordered."
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "FLAGGED_FOR_INQUIRY")
        self.assertIn("case_id", data)

        # Check that an investigation case was created
        inv = db.query("SELECT * FROM investigations WHERE case_id = ?", (data["case_id"],), one=True)
        self.assertIsNotNone(inv)
        self.assertIn("Vigilance Inquiry", inv["title"])
        self.assertEqual(inv["status"], "ACTION_REQUIRED")

    def test_05_officer_direct_permit_issuance_without_admin_permission(self):
        """Officer can directly issue e-Rawaana for a businessman's quarry block without admin approval."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 1 LIMIT 1", one=True)
        self.assertIsNotNone(qb)

        payload = {
            "mine_id": 1,
            "quarry_block_id": qb["id"],
            "truck_id": 1,
            "mineral": "Quartzite Stone",
            "permitted_weight_mt": 25.0,
            "destination_name": "Gurugram Infrastructure Hub",
            "buyer_name": "DLF ReadyMix Plant",
            "valid_hours": 12
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["issuance_type"], "OFFICER_AUTHORIZED_DISPATCH")
        
        # Verify permit in database
        permit = db.query("SELECT * FROM permits WHERE id = ?", (data["permit_id"],), one=True)
        self.assertIsNotNone(permit)
        self.assertEqual(permit["issuance_type"], "OFFICER_AUTHORIZED_DISPATCH")
        self.assertEqual(permit["quarry_block_id"], qb["id"])
        self.assertIn(qb["leaseholder_name"], permit["quarry_name"])

    def test_06_admin_emergency_permit_issuance(self):
        """Admin can issue emergency e-Rawaana under Section 26 MMDR."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"
            sess["username"] = "admin"

        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 2 LIMIT 1", one=True)
        payload = {
            "mine_id": 2,
            "quarry_block_id": qb["id"] if qb else None,
            "truck_id": 2,
            "mineral": "High-Grade Limestone",
            "permitted_weight_mt": 28.0,
            "destination_name": "State Emergency Highway Construction Project Lot 4",
            "buyer_name": "NHAI Highway Authority",
            "valid_hours": 24,
            "emergency_reason": "Pit scale hardware downtime override under emergency discretion"
        }
        res = self.client.post("/api/crud/permits", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["issuance_type"], "EMERGENCY_ADMIN_ISSUANCE")

        permit = db.query("SELECT * FROM permits WHERE id = ?", (data["permit_id"],), one=True)
        self.assertEqual(permit["issuance_type"], "EMERGENCY_ADMIN_ISSUANCE")

    def test_07_officer_dashboard_displays_quarry_blocks_directory(self):
        """Officer dashboard must display under-mine businessmen directory and direct issue modal."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Under-Mine Sub-Lease Concessions &amp; Businessmen Directory", html)
        self.assertIn("modal-officer-issue-permit", html)
        self.assertIn("Direct Issue e-Rawaana", html)
        self.assertIn("LOCKED SECTOR", html)

    def test_08_admin_dashboard_displays_emergency_erawana_capability(self):
        """Admin dashboard must display statewide emergency e-Rawaana modal."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_role"] = "ADMIN"
            sess["username"] = "admin"

        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("Emergency e-Rawaana", html)
        self.assertIn("modal-admin-emergency-permit", html)

    def test_09_officer_navbar_is_locked_to_assigned_mine_no_dropdown(self):
        """Officer navbar must NOT have any mine selection dropdown; must be locked to assigned mine."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        res = self.client.get("/trips")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        # Should contain locked sector badge
        self.assertIn("LOCKED SECTOR", html)
        self.assertIn("Assigned Mine:", html)
        self.assertIn("Aravalli Quartzite Quarry Block A", html)
        # Must NOT contain the dropdown selector for switching mines
        self.assertNotIn('<select name="mine_id"', html)

    def test_10_officer_cannot_switch_mine_filter(self):
        """Officer calling /set-mine-filter is denied and kept on their assigned mine."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        res = self.client.get("/set-mine-filter?mine_id=3", follow_redirects=True)
        html = res.get_data(as_text=True)
        self.assertIn("Access Denied", html)

        # Ensure session did not store cross-tenant mine_id
        with self.client.session_transaction() as sess:
            self.assertNotEqual(sess.get("selected_mine_id"), 3)

    def test_11_officer_trips_only_shows_assigned_mine_trips(self):
        """Officer on /trips only sees trips from their assigned mine (Mine 1)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        res = self.client.get("/trips")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("LOCKED SECTOR", html)
        self.assertIn("Aravalli Quartzite Quarry Block A", html)
        
        with self.app.test_request_context():
            from flask import session as flask_sess
            from app import get_active_mine_id
            flask_sess["user_id"] = 2
            flask_sess["user_role"] = "OFFICER"
            flask_sess["username"] = "officer1"
            self.assertEqual(get_active_mine_id(), 1)


if __name__ == "__main__":
    unittest.main()
