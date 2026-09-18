"""
Unit Tests for Real-World Mining Fraud Mitigation Suite (6 Core Scenarios)
1. Pass Recycling (Short-Looping Trip Reuse)
2. Weighbridge Kanta Cheating (Axle Off Scale Ramp)
3. Material Quality Fraud (Neela Maal vs Laal Maal Grade Arbitrage)
4. Off-Record Token System & Crusher Inward Kacha Maal Reconciliation
5. Pit Over-Extraction Beyond Lease Quotas (Drone DEM Volumetry & Kill-Switch)
6. Unclosed Vehicle Entries & Ghost Trucks (Dwell Watchdog)
7. Simulator Action Triggers & REST Endpoints
"""
import json
import unittest
from datetime import datetime, timedelta
from app import app
from services.db import db
from services.detection import DetectionEngine
from services.material_service import MaterialMonitoringService
from services.gps_simulator import simulator


class RealWorldFraudMitigationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        db.run_auto_migrations()

    # -------------------------------------------------------------
    # Scenario 1: Pass Recycling & Short-Looping
    # -------------------------------------------------------------
    def test_01_pass_recycling_rejected_for_consumed_permit(self):
        """A permit in CONSUMED status cannot be recycled for a second trip."""
        # Insert a consumed permit
        p_code = f"RAW-TEST-REUSE-{int(datetime.now().timestamp())}"
        pid = db.execute("""
            INSERT INTO permits (permit_number, qr_code_hash, truck_id, mine_id, mineral, permitted_weight_mt,
                                source_name, destination_name, destination_lat, destination_lng, buyer_name,
                                status, issued_at, expires_at, consumed_at)
            VALUES (?, ?, 1, 1, 'Quartzite', 25.0, 'Aravalli Quarry Block A', 'Bhiwadi Hub',
                    28.2100, 76.8500, 'DLF ReadyMix', 'CONSUMED',
                    datetime('now', '-2 hours'), datetime('now', '+2 hours'), datetime('now', '-10 minutes'))
        """, (p_code, f"QR-{p_code}"))

        res = DetectionEngine.check_pass_recycling_and_short_looping(truck_id=1, permit_id=pid, mine_id=1)
        self.assertTrue(res["is_violation"], "Consumed permit reuse must be flagged as violation")
        self.assertEqual(res["violation_type"], "PERMIT_REUSE_ATTEMPT")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertIn(res["risk_contribution"], (35, 40))
        self.assertIn("PASS RECYCLING", res["explanation"])

    def test_02_short_looping_velocity_anomaly(self):
        """Impossible quick turnaround on a 45-km route is flagged as short-looping fraud."""
        # Active permit but impossible velocity (returned in 18 minutes for 45 km)
        p_code = f"RAW-TEST-VEL-{int(datetime.now().timestamp())}"
        pid = db.execute("""
            INSERT INTO permits (permit_number, qr_code_hash, truck_id, mine_id, mineral, permitted_weight_mt,
                                source_name, destination_name, destination_lat, destination_lng, buyer_name,
                                status, issued_at, expires_at)
            VALUES (?, ?, 1, 1, 'Quartzite', 25.0, 'Aravalli Quarry Block A', 'Bhiwadi Hub',
                    28.2100, 76.8500, 'DLF ReadyMix', 'ACTIVE',
                    datetime('now', '-18 minutes'), datetime('now', '+4 hours'))
        """, (p_code, f"QR-{p_code}"))

        res = DetectionEngine.check_pass_recycling_and_short_looping(
            truck_id=1, permit_id=pid, mine_id=1, elapsed_turnaround_minutes=18.0
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "SHORT_LOOPING_ANOMALY")
        self.assertEqual(res["severity"], "HIGH")
        self.assertEqual(res["risk_contribution"], 25)

    # -------------------------------------------------------------
    # Scenario 2: Weighbridge Kanta Manipulation
    # -------------------------------------------------------------
    def test_03_kanta_cheating_axle_off_scale_ramp(self):
        """Wheels resting on approach ramp (broken IR position beam) triggers critical violation."""
        res = DetectionEngine.check_weighbridge_kanta_cheating(
            gross_weight_mt=38.0,
            tare_weight_mt=11.5,
            bed_volume_m3=20.0,
            axle_beam_aligned=False
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "WEIGHBRIDGE_AXLE_CHEATING")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 35)
        self.assertTrue(res["metrics"]["barrier_locked"])

    def test_04_kanta_volumetric_density_anomaly(self):
        """Volumetric LiDAR density check catches under-mass cargo (full bed volume with low recorded weight)."""
        # Full 20 m3 bed but net weight is only 22 MT (density 1.10 MT/m3 vs expected 1.60 MT/m3)
        res = DetectionEngine.check_weighbridge_kanta_cheating(
            gross_weight_mt=33.5,
            tare_weight_mt=11.5,
            bed_volume_m3=20.0,
            axle_beam_aligned=True,
            expected_density_mt_m3=1.60
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "DENSITY_VOLUME_DISCREPANCY")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 30)
        self.assertIn("VOLUMETRIC DENSITY ANOMALY", res["explanation"])

    def test_05_kanta_normal_weight_compliant(self):
        """Normal full-deck weighment with valid density passes with no violation."""
        res = DetectionEngine.check_weighbridge_kanta_cheating(
            gross_weight_mt=43.9,
            tare_weight_mt=11.5,
            bed_volume_m3=20.0,
            axle_beam_aligned=True,
            expected_density_mt_m3=1.60
        )
        self.assertFalse(res["is_violation"])
        self.assertEqual(res["severity"], "LOW")
        self.assertEqual(res["risk_contribution"], 0)

    # -------------------------------------------------------------
    # Scenario 3: Material Quality Fraud / Grade Arbitrage
    # -------------------------------------------------------------
    def test_06_grade_arbitrage_sandwich_loading(self):
        """High-grade blue stone pit declared under cheap red stone tariff is flagged."""
        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 1 LIMIT 1", one=True)
        res = DetectionEngine.check_mineral_grade_arbitrage(
            quarry_block_id=qb["id"],
            declared_tariff=300.0,
            declared_mineral="Red Low-Grade Gravel"
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "MINERAL_GRADE_ARBITRAGE")
        self.assertEqual(res["severity"], "HIGH")
        self.assertEqual(res["risk_contribution"], 25)
        self.assertEqual(res["metrics"]["royalty_evasion_delta_inr"], 75.0)

    def test_07_grade_compliant_declaration(self):
        """Correct tariff for certified pit passes cleanly."""
        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 1 LIMIT 1", one=True)
        res = DetectionEngine.check_mineral_grade_arbitrage(
            quarry_block_id=qb["id"],
            declared_tariff=375.0,
            declared_mineral="High-Grade Blue Quartzite"
        )
        self.assertFalse(res["is_violation"])
        self.assertEqual(res["risk_contribution"], 0)

    # -------------------------------------------------------------
    # Scenario 4: Token System & Crusher Inward Kacha Maal
    # -------------------------------------------------------------
    def test_08_token_system_bypass_detected(self):
        """Truck detected at perimeter RFID without digital e-Ravanna is locked down."""
        res = DetectionEngine.check_token_system_bypass(
            truck_reg="RJ02GA9901",
            rfid_detected=True,
            has_valid_permit=False,
            mine_id=1
        )
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "TOKEN_SYSTEM_BYPASS")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 40)
        self.assertTrue(res["metrics"]["barrier_locked"])

    def test_09_crusher_kacha_maal_audit(self):
        """Crusher feedstock reconciliation identifies unbilled kacha maal intake."""
        audit = MaterialMonitoringService.get_crusher_inward_kacha_maal_audit(mine_id=1)
        self.assertGreater(audit["total_crushed_feedstock_mt"], 0)
        self.assertGreater(audit["total_unaccounted_kacha_maal_mt"], 0)
        self.assertGreater(audit["overall_kacha_maal_pct"], 0)
        self.assertGreater(len(audit["crusher_plants"]), 0)

    # -------------------------------------------------------------
    # Scenario 5: Pit Over-Extraction & Drone DEM Audit
    # -------------------------------------------------------------
    def test_10_pit_over_extraction_killswitch(self):
        """Sub-plot exceeding statutory allocated quota triggers kill-switch lock."""
        qb = db.query("SELECT * FROM quarry_blocks WHERE mine_id = 1 LIMIT 1", one=True)
        b_id = qb["id"]
        orig_disp = qb["dispatched_mt"]
        orig_alloc = qb["allocated_quota_mt"]

        # Temporarily exhaust quota for Block
        db.execute("UPDATE quarry_blocks SET dispatched_mt = 15500.0, allocated_quota_mt = 12000.0 WHERE id = ?", (b_id,))
        res = DetectionEngine.check_pit_over_extraction(quarry_block_id=b_id, mine_id=1)
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "CONCESSION_QUOTA_EXHAUSTED")
        self.assertEqual(res["severity"], "CRITICAL")
        self.assertEqual(res["risk_contribution"], 40)
        self.assertTrue(res["metrics"]["kill_switch_active"])

        # Reset block back
        db.execute("UPDATE quarry_blocks SET dispatched_mt = ?, allocated_quota_mt = ? WHERE id = ?", (orig_disp, orig_alloc, b_id))

    def test_11_drone_dem_volumetric_audit(self):
        """Drone DEM volumetric model calculates physical excavation vs e-Ravanna dispatches."""
        audit = MaterialMonitoringService.get_drone_dem_volumetric_audit(mine_id=1)
        self.assertEqual(audit["mine_id"], 1)
        self.assertGreater(audit["dem_excavated_void_m3"], 0)
        self.assertGreater(audit["physical_extracted_mt"], 0)
        self.assertEqual(audit["mineral_density_mt_m3"], 1.62)
        self.assertIn("plot_breakdown", audit)

    # -------------------------------------------------------------
    # Scenario 6: Ghost Truck & Unclosed Entries Watchdog
    # -------------------------------------------------------------
    def test_12_unclosed_vehicle_entries_ghost_truck(self):
        """Truck inside mine with dwell > 90 mins is flagged as ghost truck hazard."""
        past_120m = (datetime.now() - timedelta(minutes=120)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute("UPDATE trucks SET is_inside_mine = 1, current_mine_id = 1, last_mine_entry = ? WHERE id = 1", (past_120m,))

        res = DetectionEngine.check_unclosed_vehicle_entries(mine_id=1, max_dwell_minutes=90)
        self.assertTrue(res["is_violation"])
        self.assertEqual(res["violation_type"], "UNCLOSED_ENTRY_TIMEOUT")
        self.assertEqual(res["risk_contribution"], 30)
        self.assertGreaterEqual(res["metrics"]["total_ghost_trucks_flagged"], 1)

    def test_13_active_pit_dwell_watchdog(self):
        """Active pit dwell watchdog returns vehicle census and dwell status."""
        watchdog = MaterialMonitoringService.get_active_pit_dwell_watchdog(mine_id=1)
        self.assertGreater(watchdog["total_trucks_inside"], 0)
        self.assertIn("active_vehicles", watchdog)

    # -------------------------------------------------------------
    # Scenario 7: Simulator API Actions & REST Endpoints
    # -------------------------------------------------------------
    def test_14_simulator_api_triggers_all_scenarios(self):
        """POST /api/simulator/action successfully handles all 6 real-world fraud triggers."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        actions = [
            "trigger_pass_reuse",
            "trigger_kanta_cheating",
            "trigger_grade_arbitrage",
            "trigger_token_bypass",
            "trigger_over_extraction_killswitch",
            "trigger_unclosed_entry"
        ]

        for act in actions:
            res = self.client.post("/api/simulator/action", json={"action": act, "truck_reg": "HR26AB1234"})
            self.assertEqual(res.status_code, 200, f"Action {act} failed with {res.status_code}")
            data = res.get_json()
            self.assertTrue(data.get("status", "").startswith("triggered_"))
            self.assertEqual(data["result"]["status"], "success")

    def test_15_audit_rest_endpoints(self):
        """GET /api/mine/drone-dem-audit, crusher audit, and unclosed entries return valid JSON."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["user_role"] = "OFFICER"
            sess["username"] = "officer1"

        # 1. Drone DEM
        res1 = self.client.get("/api/mine/drone-dem-audit?mine_id=1")
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.get_json()["success"])

        # 2. Crusher Kacha Maal
        res2 = self.client.get("/api/mine/crusher-kacha-maal-audit?mine_id=1")
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()["success"])

        # 3. Unclosed Entries
        res3 = self.client.get("/api/mine/unclosed-entries?mine_id=1")
        self.assertEqual(res3.status_code, 200)
        self.assertTrue(res3.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
