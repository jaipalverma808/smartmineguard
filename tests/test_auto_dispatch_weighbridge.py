"""
Unit and integration tests for Automatic Weight Detection and [AUTO-DISPATCH MODE: ON] features.
"""
import unittest
import json
from app import app
from services.db import db


class TestAutoDispatchWeighbridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def login_as(self, username, password):
        return self.client.post("/login", data={
            "username": username,
            "password": password
        }, follow_redirects=True)

    def test_01_operator_weighbridge_page_renders_auto_dispatch_ui(self):
        """Verify operator weighbridge console renders with Auto-Dispatch Command Bar and IoT Scale Terminal."""
        self.login_as("operator1", "operator123")
        res = self.client.get("/operator/weighbridge")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        
        # Verify Auto-Dispatch command bar
        self.assertIn("[● AUTO-DISPATCH MODE: ON]", html)
        self.assertIn("Zero-Touch M2M Gate Clearance", html)
        self.assertIn("btn-toggle-auto-dispatch", html)

        # Verify IoT Scale Terminal & WebSerial controls
        self.assertIn("AVERY WEIGH-TRONIX E1310 / ESSAE IoT", html)
        self.assertIn("digital-scale-value", html)
        self.assertIn("Connect Scale (WebSerial)", html)
        self.assertIn("Simulate Scale (Legal Load)", html)
        self.assertIn("Simulate Scale (Overload)", html)

        # Verify Autonomous Clearance Dossier
        self.assertIn("modal-auto-dispatch-success", html)
        self.assertIn("Automated Boom Barrier Lifted", html)

    def test_02_auto_dispatch_legal_weight_lifts_barrier(self):
        """Verify that legal weighment under Auto-Dispatch lifts barrier automatically and issues PDF."""
        self.login_as("operator1", "operator123")
        
        # Pick an active trip
        trip = db.query("""
            SELECT tr.id, tr.truck_id, tr.permit_id, tr.mine_id, p.permitted_weight_mt, t.tare_weight_mt
            FROM trips tr
            JOIN permits p ON p.id = tr.permit_id
            JOIN trucks t ON t.id = tr.truck_id
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(trip)

        tare = trip["tare_weight_mt"]
        permitted = trip["permitted_weight_mt"]
        legal_gross = tare + permitted  # exact legal capacity

        payload = {
            "trip_id": trip["id"],
            "truck_id": trip["truck_id"],
            "permit_id": trip["permit_id"],
            "weighbridge_code": "WB-TEST-01",
            "weighbridge_name": "Automatic M2M Outbound Scale",
            "tare_weight_mt": tare,
            "gross_weight_mt": legal_gross,
            "measurement_source": "AUTOMATED_M2M_LOADCELL_TELEMETRY",
            "auto_dispatch": True
        }

        res = self.client.post("/api/crud/weighments",
                               data=json.dumps(payload),
                               content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["auto_dispatch"])
        self.assertFalse(data["is_overweight"])
        self.assertEqual(data["barrier_status"], "BARRIER_LIFTED_AUTOMATICALLY")
        self.assertIn("Zero-Touch Auto-Dispatch Complete", data["message"])
        self.assertIsNotNone(data["pdf_url"])

        # Check trip timeline
        trip_row = db.query("SELECT timeline_events_json FROM trips WHERE id = ?", (trip["id"],), one=True)
        self.assertIn("AUTO_DISPATCH_M2M", trip_row["timeline_events_json"])

    def test_03_auto_dispatch_overload_locks_barrier(self):
        """Verify that overloaded weighment under Auto-Dispatch locks down the barrier and alerts."""
        self.login_as("operator1", "operator123")
        
        trip = db.query("""
            SELECT tr.id, tr.truck_id, tr.permit_id, tr.mine_id, p.permitted_weight_mt, t.tare_weight_mt
            FROM trips tr
            JOIN permits p ON p.id = tr.permit_id
            JOIN trucks t ON t.id = tr.truck_id
            LIMIT 1
        """, one=True)
        self.assertIsNotNone(trip)

        tare = trip["tare_weight_mt"]
        permitted = trip["permitted_weight_mt"]
        overload_gross = tare + permitted + 6.0  # 6 tons overload!

        payload = {
            "trip_id": trip["id"],
            "truck_id": trip["truck_id"],
            "permit_id": trip["permit_id"],
            "weighbridge_code": "WB-TEST-01",
            "weighbridge_name": "Automatic M2M Outbound Scale",
            "tare_weight_mt": tare,
            "gross_weight_mt": overload_gross,
            "measurement_source": "AUTOMATED_M2M_LOADCELL_TELEMETRY",
            "auto_dispatch": True
        }

        res = self.client.post("/api/crud/weighments",
                               data=json.dumps(payload),
                               content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["auto_dispatch"])
        self.assertTrue(data["is_overweight"])
        self.assertEqual(data["barrier_status"], "BARRIER_LOCKED_OVERLOAD")
        self.assertIn("AUTO-DISPATCH INHIBITED", data["message"])


if __name__ == "__main__":
    unittest.main()
