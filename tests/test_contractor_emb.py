"""
Unit & Integration Test Suite for Contractor Infrastructure Portal,
Multi-Sector Development Reconciliation, and Treasury Penalty Withholding.
"""
import unittest
from app import app
from services.db import db


class TestContractorInfrastructureReconciliation(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Reset test state
        db.execute("""
            UPDATE permits 
            SET status = 'ACTIVE', project_work_order = 'NHAI-PKG-04', received_at_site = NULL 
            WHERE permit_number = 'SMG-2026-00125'
        """)
        db.execute("""
            UPDATE infrastructure_projects 
            SET sand_received_mt = 1600.0, mineral_received_mt = 1600.0, status = 'DEFICIT_FLAGGED' 
            WHERE id = 1
        """)

    def test_01_contractor_login_and_dashboard(self):
        """Test Contractor login and multi-sector mineral wallet dashboard loading."""
        res = self.client.post('/login', data={'username': 'contractor1', 'password': 'contractor123'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Sharma Infrastructure", res.data)
        self.assertIn(b"Structural Volume", res.data)
        self.assertIn(b"Target Required", res.data)

    def test_02_site_gate_receive_truck_api(self):
        """Test Site Gate QR scan endpoint credits mineral wallet and prevents double-counting."""
        # Login first to get session CSRF token
        self.client.post('/login', data={'username': 'contractor1', 'password': 'contractor123'}, follow_redirects=True)
        with self.client.session_transaction() as sess:
            csrf = sess.get('_csrf_token')

        # 1. First Scan (Valid Receipt)
        res = self.client.post(
            '/api/contractor/receive-truck',
            headers={'X-CSRF-Token': csrf},
            json={'permit_number': 'SMG-2026-00125', 'project_id': 1}
        )
        data = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('added_mt'), 20.0)
        self.assertEqual(data.get('new_total_mt'), 1620.0)

        # 2. Duplicate Scan (Must Reject)
        res_dup = self.client.post(
            '/api/contractor/receive-truck',
            headers={'X-CSRF-Token': csrf},
            json={'permit_number': 'SMG-2026-00125', 'project_id': 1}
        )
        data_dup = res_dup.get_json()
        self.assertEqual(res_dup.status_code, 400)
        self.assertFalse(data_dup.get('success'))
        self.assertIn('ALREADY', data_dup.get('error', '').upper())

    def test_03_admin_infrastructure_audit_views(self):
        """Test Admin Dashboard and dedicated Multi-Sector Infrastructure Audit views."""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        # Admin Dashboard card
        res_dash = self.client.get('/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b"Multi-Sector Project &amp; Contractor Mineral Reconciliation", res_dash.data)

        # Full Statewide Audit Ledger
        res_audit = self.client.get('/admin/infrastructure-audit')
        self.assertEqual(res_audit.status_code, 200)
        self.assertIn(b"NHAI-PKG-04", res_audit.data)
        self.assertIn(b"DLF-CYBER-T2", res_audit.data)
        self.assertIn(b"ACC ReadyMix", res_audit.data)

    def test_04_admin_audit_hierarchical_filtering(self):
        """Test filtering by Development Sector (Real Estate Builders vs Highways)."""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

        # Filter only Real Estate Builders
        res_builder = self.client.get('/admin/infrastructure-audit?category=REAL_ESTATE_BUILDER')
        self.assertEqual(res_builder.status_code, 200)
        self.assertIn(b"DLF Universal", res_builder.data)
        self.assertNotIn(b"NHAI-PKG-04", res_builder.data)

        # Filter only Highway Infrastructure
        res_hw = self.client.get('/admin/infrastructure-audit?category=HIGHWAY_INFRA')
        self.assertEqual(res_hw.status_code, 200)
        self.assertIn(b"NHAI-PKG-04", res_hw.data)
        self.assertNotIn(b"DLF Universal", res_hw.data)

    def test_05_royalty_noc_pdf_generation(self):
        """Test formal Statutory Royalty Clearance Certificate PDF builder."""
        self.client.post('/login', data={'username': 'contractor1', 'password': 'contractor123'}, follow_redirects=True)
        res = self.client.get('/contractor/download-noc/1')
        self.assertIn(res.status_code, (200, 302))


if __name__ == '__main__':
    unittest.main()
