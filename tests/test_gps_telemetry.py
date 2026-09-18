"""
SmartMineGuard - GPS Anti-Tamper & Telemetry Center Test Suite
Tests GPS Jammer ('Gamer') detection, hardware wire-cut tampering, network blindspot classification,
and SIH demonstration endpoints.
"""
import unittest
import json
from app import app
from services.db import db
from services.detection import DetectionEngine
from services.gps_simulator import simulator


class TestGpsAntiTamperTelemetry(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password}, follow_redirects=False)

    def test_01_gps_telemetry_requires_login(self):
        """Unauthenticated user is redirected from /gps-telemetry to login."""
        res = self.client.get("/gps-telemetry")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    def test_02_admin_can_access_gps_telemetry(self):
        """Admin can access /gps-telemetry and sees radar, tamper metrics, and AIS-140 ledger."""
        self.login("admin", "admin123")
        res = self.client.get("/gps-telemetry")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("GPS Anti-Tamper &amp; Telemetry Intelligence Center", html)
        self.assertIn("GPS Jammers", html)
        self.assertIn("Hardware Tamper", html)
        self.assertIn("Network Drops", html)
        self.assertIn("Riverbed Breaches", html)
        self.assertIn("SIH Live Demo Control", html)
        self.assertIn("HR26AB1234", html)
        self.client.get("/logout")

    def test_03_officer_can_access_gps_telemetry(self):
        """Officer can access /gps-telemetry and inspect fleet radar."""
        self.login("officer1", "officer123")
        res = self.client.get("/gps-telemetry")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("GPS Anti-Tamper", html)
        self.assertIn("Fleet Anti-Tamper Telemetry Ledger", html)
        self.client.get("/logout")

    def test_04_operator_can_access_gps_telemetry_scoped(self):
        """Operator can access /gps-telemetry scoped to their assigned mine."""
        self.login("operator1", "operator123")
        res = self.client.get("/gps-telemetry")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("GPS Anti-Tamper", html)
        self.client.get("/logout")

    def test_05_api_gps_trucks_endpoint(self):
        """GET /api/gps/trucks returns valid fleet telemetry JSON."""
        self.login("admin", "admin123")
        res = self.client.get("/api/gps/trucks")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsInstance(data["trucks"], list)
        self.assertGreater(len(data["trucks"]), 0)
        first_truck = data["trucks"][0]
        self.assertIn("registration_number", first_truck)
        self.assertIn("satellite_count", first_truck)
        self.assertIn("external_power_volts", first_truck)
        self.assertIn("gps_status", first_truck)
        self.client.get("/logout")

    def test_06_api_gps_diagnostics_endpoint(self):
        """GET /api/gps/trucks/<id>/diagnostics returns hardware diagnostics & AI verdict."""
        self.login("admin", "admin123")
        res = self.client.get("/api/gps/trucks/1/diagnostics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["truck"]["registration_number"], "HR26AB1234")
        self.assertIn("classification", data)
        self.assertIn("title", data["classification"])
        self.assertIn("explanation", data["classification"])
        self.client.get("/logout")

    def test_07_ai_heuristic_classifier_accurately_detects_jammer_vs_blindspot(self):
        """Test heuristic classification engine distinguishes RF jammer from cellular dead-zone."""
        # 1. Jammer attack: 0 satellites or C/N0 < 20 dB-Hz with normal external power
        jammer_res = DetectionEngine.classify_telemetry_interruption(
            satellite_count=0,
            cno_db_hz=14.0,
            external_power_volts=24.2,
            in_prohibited_zone=False
        )
        self.assertEqual(jammer_res["classification"], "GPS_JAMMER_DETECTED")
        self.assertEqual(jammer_res["severity"], "CRITICAL")
        self.assertTrue(jammer_res["is_threat"])

        # 2. Wire cut: external power <= 2.0V
        wire_res = DetectionEngine.classify_telemetry_interruption(
            satellite_count=11,
            cno_db_hz=44.0,
            external_power_volts=0.0,
            in_prohibited_zone=False
        )
        self.assertEqual(wire_res["classification"], "HARDWARE_TAMPER_WIRE_CUT")
        self.assertEqual(wire_res["severity"], "HIGH")
        self.assertTrue(wire_res["is_threat"])

        # 3. Legitimate cellular dead-zone: healthy satellites (10), delayed ping (>180s)
        blindspot_res = DetectionEngine.classify_telemetry_interruption(
            satellite_count=10,
            cno_db_hz=42.5,
            external_power_volts=24.2,
            in_prohibited_zone=False,
            elapsed_seconds=240
        )
        self.assertEqual(blindspot_res["classification"], "NETWORK_BLINDSPOT")
        self.assertFalse(blindspot_res["is_threat"])

        # 4. Prohibited zone incursion
        riverbed_res = DetectionEngine.classify_telemetry_interruption(
            satellite_count=11,
            cno_db_hz=43.0,
            external_power_volts=24.2,
            in_prohibited_zone=True
        )
        self.assertEqual(riverbed_res["classification"], "PROHIBITED_ZONE_INCURSION")
        self.assertEqual(riverbed_res["severity"], "CRITICAL")

    def test_08_simulator_trigger_actions(self):
        """Test SIH live demo simulation actions: jammer, tamper, blindspot, and restore."""
        self.login("admin", "admin123")

        # 1. Trigger GPS Jammer
        res_j = self.client.post("/api/gps/simulator/trigger", json={"action": "jammer", "truck_reg": "HR26AB1234"})
        self.assertEqual(res_j.status_code, 200)
        self.assertTrue(res_j.get_json()["success"])
        t_j = db.query("SELECT * FROM trucks WHERE registration_number = 'HR26AB1234'", one=True)
        self.assertEqual(t_j["gps_status"], "JAMMER_DETECTED")
        self.assertEqual(t_j["satellite_count"], 0)

        # 2. Trigger Hardware Wire Cut
        res_t = self.client.post("/api/gps/simulator/trigger", json={"action": "tamper", "truck_reg": "HR26AB1234"})
        self.assertEqual(res_t.status_code, 200)
        t_t = db.query("SELECT * FROM trucks WHERE registration_number = 'HR26AB1234'", one=True)
        self.assertEqual(t_t["gps_status"], "TAMPERED")
        self.assertEqual(t_t["external_power_volts"], 0.0)

        # 3. Restore Telemetry
        res_r = self.client.post("/api/gps/simulator/trigger", json={"action": "restore", "truck_reg": "HR26AB1234"})
        self.assertEqual(res_r.status_code, 200)
        t_r = db.query("SELECT * FROM trucks WHERE registration_number = 'HR26AB1234'", one=True)
        self.assertEqual(t_r["gps_status"], "HEALTHY")
        self.assertEqual(t_r["satellite_count"], 12)
        self.assertEqual(t_r["external_power_volts"], 24.2)

        self.client.get("/logout")

    def test_09_enforcement_action_dispatch(self):
        """Test that Flying Squad enforcement dispatch updates incident event."""
        self.login("admin", "admin123")
        event = db.query("SELECT id FROM gps_tamper_events ORDER BY id DESC LIMIT 1", one=True)
        if event:
            res = self.client.post(f"/api/gps/events/{event['id']}/enforce", json={"action_type": "FLYING_SQUAD", "notes": "Intercept ordered."})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data["success"])
            self.assertIn("Flying Squad Dispatched", data["action_taken"])
            updated_event = db.query("SELECT * FROM gps_tamper_events WHERE id = ?", (event["id"],), one=True)
            self.assertEqual(updated_event["status"], "ENFORCED")
        self.client.get("/logout")


if __name__ == "__main__":
    unittest.main()
