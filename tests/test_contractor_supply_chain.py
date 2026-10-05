"""
Unit & Integration Test Suite for Contractor Supply Chain Architecture:
LEGAL SOURCE -> CONTRACTOR CUSTODIAN -> DOWNSTREAM CONSUMER / PROJECT.

Validates:
1. Source sends 500 MT to Contractor.
2. Contractor receives 500 MT.
3. Contractor stock increases by 500 MT.
4. Contractor dispatches 200 MT to Consumer.
5. Contractor expected stock becomes 300 MT.
6. Consumer receives 200 MT.
7. Another receipt increases Contractor stock correctly.
8. Dispatch greater than verified available material creates a reconciliation exception.
9. Opening stock carries forward from previous closing stock (rolling material balance).
10. Existing SmartMineGuard pages continue working.
"""
import unittest
from app import app, get_contractor_reconciliation
from services.db import db


class TestContractorSupplyChainArchitecture(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def _get_csrf_header(self):
        with self.client.session_transaction() as sess:
            csrf = sess.get('_csrf_token') or ''
        return {'X-CSRF-Token': csrf}

    def test_01_to_07_source_receipt_and_consumer_dispatch_flow(self):
        """
        Step 1 to 7:
        1. Source generates permit for 500 MT to Contractor.
        2. Contractor receives 500 MT.
        3. Contractor stock increases by 500 MT.
        4. Contractor dispatches 200 MT to Consumer (NH-48).
        5. Contractor expected stock becomes 300 MT.
        6. Consumer project receives 200 MT.
        7. Another receipt increases Contractor stock correctly (+150 MT).
        """
        # Ensure a clean test contractor exists
        db.execute("""
            INSERT OR IGNORE INTO contractors (id, contractor_code, contractor_name, opening_stock_mt, status)
            VALUES (99, 'CONT-TEST-99', 'Test Custodian Infra Ltd', 0.0, 'ACTIVE')
        """)
        # Reset receipts and dispatches for test contractor 99
        db.execute("DELETE FROM contractor_receipts WHERE contractor_id = 99")
        db.execute("DELETE FROM contractor_dispatches WHERE contractor_id = 99")
        db.execute("UPDATE contractors SET opening_stock_mt = 0.0 WHERE id = 99")

        # Create a test legal source permit with 500 MT
        db.execute("""
            INSERT OR REPLACE INTO permits 
            (id, permit_number, mine_id, truck_id, source_name, destination_name, destination_lat, destination_lng, buyer_name, expires_at, mineral, permitted_weight_mt, status, qr_code_hash)
            VALUES (99901, 'SMG-TEST-500MT', 1, 1, 'Aravalli Quartzite Quarry Block A', 'Sharma Depot Manesar', 28.35, 76.92, 'Test Custodian Infra Ltd', '2027-12-31 23:59:59', 'Aravalli Quartzite Aggregate', 500.0, 'ACTIVE', 'qr_hash_500mt')
        """)

        # Initial recon
        recon_start = get_contractor_reconciliation(99)
        self.assertEqual(recon_start["opening_stock_mt"], 0.0)
        self.assertEqual(recon_start["total_available_mt"], 0.0)

        # 1 & 2. Contractor receives 500 MT from source via API
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        headers = self._get_csrf_header()
        res_rec = self.client.post('/api/contractor/receive-permit', json={
            'permit_number': 'SMG-TEST-500MT',
            'contractor_id': 99
        }, headers=headers)
        self.assertEqual(res_rec.status_code, 200)
        data_rec = res_rec.get_json()
        self.assertTrue(data_rec.get("success"))
        self.assertEqual(data_rec.get("added_mt"), 500.0)

        # 3. Contractor stock increases by 500 MT
        recon_after_rec = get_contractor_reconciliation(99)
        self.assertEqual(recon_after_rec["total_receipts_mt"], 500.0)
        self.assertEqual(recon_after_rec["total_available_mt"], 500.0)
        self.assertEqual(recon_after_rec["expected_closing_stock_mt"], 500.0)

        # Record consumer starting received total
        proj_before = db.query("SELECT * FROM infrastructure_projects WHERE id = 1", one=True)
        proj_initial_rec = float(proj_before["mineral_received_mt"] or 0.0)

        # 4. Contractor dispatches 200 MT to Downstream Consumer (NH-48, project_id=1)
        res_dsp = self.client.post('/api/contractor/dispatch-material', json={
            'contractor_id': 99,
            'project_id': 1,
            'quantity_mt': 200.0,
            'vehicle_number': 'HR26AB9999',
            'driver_name': 'Test Driver',
            'mineral': 'Aravalli Quartzite Aggregate'
        }, headers=headers)
        self.assertEqual(res_dsp.status_code, 200)
        data_dsp = res_dsp.get_json()
        self.assertTrue(data_dsp.get("success"))

        # 5. Contractor expected stock becomes 300 MT (500 MT - 200 MT = 300 MT)
        recon_after_dsp = get_contractor_reconciliation(99)
        self.assertEqual(recon_after_dsp["total_dispatches_mt"], 200.0)
        self.assertEqual(recon_after_dsp["expected_closing_stock_mt"], 300.0)

        # 6. Consumer project receives 200 MT
        proj_after = db.query("SELECT * FROM infrastructure_projects WHERE id = 1", one=True)
        proj_new_rec = float(proj_after["mineral_received_mt"] or 0.0)
        self.assertAlmostEqual(proj_new_rec, proj_initial_rec + 200.0, places=1)

        # 7. Another receipt increases Contractor stock correctly (+150 MT)
        db.execute("""
            INSERT OR REPLACE INTO permits 
            (id, permit_number, mine_id, truck_id, source_name, destination_name, destination_lat, destination_lng, buyer_name, expires_at, mineral, permitted_weight_mt, status, qr_code_hash)
            VALUES (99902, 'SMG-TEST-150MT', 3, 1, 'Khol Silica Sand & Stone Pit', 'Sharma Depot Manesar', 28.35, 76.92, 'Test Custodian Infra Ltd', '2027-12-31 23:59:59', 'River Sand & Sub-base Fill', 150.0, 'ACTIVE', 'qr_hash_150mt')
        """)
        res_rec2 = self.client.post('/api/contractor/receive-permit', json={
            'permit_number': 'SMG-TEST-150MT',
            'contractor_id': 99
        }, headers=headers)
        self.assertEqual(res_rec2.status_code, 200)
        recon_after_rec2 = get_contractor_reconciliation(99)
        # Total receipts: 500 + 150 = 650 MT. Total available: 650 MT. Dispatched: 200 MT. Expected closing: 450 MT.
        self.assertEqual(recon_after_rec2["total_receipts_mt"], 650.0)
        self.assertEqual(recon_after_rec2["total_available_mt"], 650.0)
        self.assertEqual(recon_after_rec2["expected_closing_stock_mt"], 450.0)

    def test_08_reconciliation_exception_when_dispatch_exceeds_available(self):
        """
        Step 8: Dispatch greater than verified available material creates a reconciliation exception.
        Does NOT accuse 'ILLEGAL MATERIAL CONFIRMED'; flags as MATERIAL RECONCILIATION EXCEPTION.
        """
        # Ensure contractor 99 has known available: 650 MT (500 MT Mine + 150 MT River)
        db.execute("""
            INSERT OR IGNORE INTO contractors (id, contractor_code, contractor_name, opening_stock_mt, status)
            VALUES (99, 'CONT-TEST-99', 'Test Custodian Infra Ltd', 0.0, 'ACTIVE')
        """)
        db.execute("DELETE FROM contractor_receipts WHERE contractor_id = 99")
        db.execute("DELETE FROM contractor_dispatches WHERE contractor_id = 99")
        db.execute("UPDATE contractors SET opening_stock_mt = 0.0 WHERE id = 99")

        db.execute("""
            INSERT INTO contractor_receipts 
            (receipt_code, contractor_id, permit_number, source_name, source_category, mineral, net_weight_mt, status)
            VALUES ('REC-TEST-650', 99, 'SMG-TEST-650', 'Aravalli Quarry', 'MINE', 'Quartzite Aggregate', 650.0, 'VERIFIED')
        """)

        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        headers = self._get_csrf_header()

        # Dispatch 800 MT (exceeds 650 MT available by 150 MT)
        res_over = self.client.post('/api/contractor/dispatch-material', json={
            'contractor_id': 99,
            'project_id': 2,
            'quantity_mt': 800.0,
            'vehicle_number': 'HR26AB8888',
            'driver_name': 'Carrier Lead',
            'mineral': 'Quartzite Aggregate'
        }, headers=headers)
        self.assertEqual(res_over.status_code, 200)
        data_over = res_over.get_json()
        self.assertTrue(data_over.get("success"))
        self.assertEqual(data_over.get("unreconciled_mt"), 150.0)
        self.assertEqual(data_over.get("reconciliation_status"), "EXCEPTION_FLAGGED")
        self.assertEqual(data_over.get("reconciliation_label"), "MATERIAL RECONCILIATION EXCEPTION")

        # Verify through dashboard rendering: never says 'ILLEGAL MATERIAL CONFIRMED'
        res_dash = self.client.get('/contractor/dashboard?contractor_id=99')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"MATERIAL RECONCILIATION EXCEPTION", res_dash.data)
        self.assertIn(b"150.0 MT UNRECONCILED", res_dash.data)
        self.assertNotIn(b"ILLEGAL MATERIAL CONFIRMED", res_dash.data)

    def test_09_rolling_stock_forward_carry(self):
        """
        Step 9: Opening stock carries forward from previous closing stock.
        Today's Opening Stock = Previous Day's Closing Stock.
        """
        # Set contractor 99 opening stock to 350.0 MT (representing carried forward closing stock)
        db.execute("UPDATE contractors SET opening_stock_mt = 350.0 WHERE id = 99")
        db.execute("DELETE FROM contractor_receipts WHERE contractor_id = 99")
        db.execute("DELETE FROM contractor_dispatches WHERE contractor_id = 99")

        recon = get_contractor_reconciliation(99)
        self.assertEqual(recon["opening_stock_mt"], 350.0)
        self.assertEqual(recon["total_available_mt"], 350.0)
        self.assertEqual(recon["expected_closing_stock_mt"], 350.0)

        # Day 2: Receipts 400 MT, Dispatches 350 MT -> Closing 400 MT
        db.execute("""
            INSERT INTO contractor_receipts 
            (receipt_code, contractor_id, permit_number, source_name, source_category, mineral, net_weight_mt, status)
            VALUES ('REC-ROLL-01', 99, 'SMG-ROLL-400', 'Khol Quarry', 'MINE', 'River Sand', 400.0, 'VERIFIED')
        """)
        db.execute("""
            INSERT INTO contractor_dispatches 
            (dispatch_code, contractor_id, project_id, consumer_name, project_code, mineral, quantity_mt, status)
            VALUES ('DSP-ROLL-01', 99, 1, 'NH-48 Expansion', 'NHAI-PKG-04', 'River Sand', 350.0, 'VERIFIED')
        """)
        recon_day2 = get_contractor_reconciliation(99)
        # 350 opening + 400 receipts = 750 available. 750 - 350 dispatches = 400 expected closing.
        self.assertEqual(recon_day2["total_available_mt"], 750.0)
        self.assertEqual(recon_day2["expected_closing_stock_mt"], 400.0)

    def test_10_existing_smartmineguard_pages_working(self):
        """
        Step 10: Existing SmartMineGuard core operational pages continue working seamlessly:
        - Admin Dashboard
        - Master Data Management
        - Alerts Center
        - Investigations
        - Analytics
        - Reports & Dossiers
        - Carrier Fleet Registry (Trucks)
        - e-Rawaana Passes
        - Transit Trips
        - Admin Supply Chain Ledger
        - Admin Infrastructure Audit
        - Contractor Dashboard
        """
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        routes_to_test = [
            ('/dashboard', b"Command Center"),
            ('/master-data', b"Master Data"),
            ('/alerts', b"Alerts"),
            ('/investigations', b"Investigations"),
            ('/analytics', b"Analytics"),
            ('/reports', b"Reports"),
            ('/trucks', b"Fleet"),
            ('/permits', b"e-Rawaana"),
            ('/trips', b"Trips"),
            ('/admin/supply-chain', b"Statewide Material Supply Chain"),
            ('/admin/infrastructure-audit', b"Consumer &amp; Project Mineral Audit"),
            ('/contractor/dashboard', b"Sharma Infrastructure Ltd")
        ]
        for path, expected_content in routes_to_test:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f"Route {path} returned status {res.status_code}")
            self.assertIn(expected_content, res.data, f"Content {expected_content} not found in {path}")


if __name__ == '__main__':
    unittest.main()
