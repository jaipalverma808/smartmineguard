"""
Unit tests for the Official Real-World e-Rawana Mineral Transit Pass,
HSIIDC Tax Invoice, and Weighment Slip PDF generation and view system.
"""
import unittest
import json
import os
from pathlib import Path
from app import app
from services.db import db
from services.report_generator import (
    generate_erawana_pdf, 
    number_to_indian_words, 
    get_enriched_permit_data
)
from config import Config


class TestERawanaPDFSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def login_as(self, username, password):
        return self.client.post("/login", data={
            "username": username,
            "password": password
        }, follow_redirects=True)

    def test_01_number_to_indian_words(self):
        """Verify Indian number-to-words currency formatting."""
        w1 = number_to_indian_words(10721.59)
        self.assertIn("Ten Thousand Seven Hundred Twenty One Rupees", w1)
        self.assertIn("Fifty Nine Paisa Only", w1)

        w2 = number_to_indian_words(50000.0)
        self.assertIn("Fifty Thousand Rupees Only", w2)

    def test_02_get_enriched_permit_data(self):
        """Verify permit data enrichment for real pass RCO26041."""
        data = get_enriched_permit_data("RCO26041")
        self.assertIsNotNone(data)
        self.assertEqual(data["rawana_no"], "RCO26041")
        self.assertEqual(data["mineral"], "Blue Stone")
        self.assertEqual(data["quantity_mt"], 30.39)
        self.assertEqual(data["slip_no"], "26-27/S8/29748")
        self.assertIn("NEELKANTH", data["buyer_name"].upper())
        self.assertIn("HSIIDC", data["quarry_name"])

    def test_03_generate_erawana_pdf_files(self):
        """Verify reportlab PDF generation for all four document configurations."""
        permit = db.query("SELECT id FROM permits WHERE permit_number = 'RCO26041'", one=True)
        self.assertIsNotNone(permit)
        p_id = permit["id"]

        # 1. Official e-Rawana Pass (Doc 1)
        pdf_erawana = generate_erawana_pdf(p_id, "erawana")
        self.assertIsNotNone(pdf_erawana)
        self.assertTrue(os.path.exists(os.path.join(Config.BASE_DIR, pdf_erawana)))

        # 2. Tax Invoice (Doc 2)
        pdf_invoice = generate_erawana_pdf(p_id, "invoice")
        self.assertIsNotNone(pdf_invoice)
        self.assertTrue(os.path.exists(os.path.join(Config.BASE_DIR, pdf_invoice)))

        # 3. Weighment Slip (Doc 3)
        pdf_weighment = generate_erawana_pdf(p_id, "weighment")
        self.assertIsNotNone(pdf_weighment)
        self.assertTrue(os.path.exists(os.path.join(Config.BASE_DIR, pdf_weighment)))

        # 4. Consolidated Statutory Packet
        pdf_packet = generate_erawana_pdf(p_id, "packet")
        self.assertIsNotNone(pdf_packet)
        self.assertTrue(os.path.exists(os.path.join(Config.BASE_DIR, pdf_packet)))

    def test_04_download_pdf_endpoint_roles(self):
        """Verify Admin, Officer, and Operator can all download e-Rawana PDFs."""
        permit = db.query("SELECT id FROM permits WHERE permit_number = 'RCO26041'", one=True)
        p_id = permit["id"]

        # Admin download
        self.login_as("admin", "admin123")
        res_admin = self.client.get(f"/permits/{p_id}/download-pdf?type=erawana")
        self.assertEqual(res_admin.status_code, 200)
        self.assertEqual(res_admin.mimetype, "application/pdf")

        # Officer download
        self.login_as("officer1", "officer123")
        res_officer = self.client.get(f"/permits/{p_id}/download-pdf?type=invoice")
        self.assertEqual(res_officer.status_code, 200)
        self.assertEqual(res_officer.mimetype, "application/pdf")

        # Operator download (Operator assigned to mine or admin)
        self.login_as("operator1", "operator123")
        # For operator, download their own mine pass or test general permit
        p_op = db.query("SELECT id FROM permits WHERE quarry_block_id = 55 OR mine_id = 5 OR mine_id = 1 ORDER BY (CASE WHEN quarry_block_id = 55 THEN 0 WHEN mine_id = 5 THEN 1 ELSE 2 END) LIMIT 1", one=True)
        if p_op:
            res_op = self.client.get(f"/permits/{p_op['id']}/download-pdf?type=weighment")
            self.assertEqual(res_op.status_code, 200)
            self.assertEqual(res_op.mimetype, "application/pdf")

    def test_05_view_permit_page(self):
        """Verify full-screen interactive e-Rawana document viewer renders correctly."""
        permit = db.query("SELECT id FROM permits WHERE permit_number = 'RCO26041'", one=True)
        p_id = permit["id"]
        self.login_as("admin", "admin123")
        res = self.client.get(f"/permits/{p_id}/view")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn("DEPARTMENT OF MINES & GEOLOGY", html)
        self.assertIn("RCO26041", html)
        self.assertIn("NEELKANTH STONE CRUSHER", html)
        self.assertIn("HSIIDC LTD. KHANAK", html)
        self.assertIn("Weighment Slip(Gross)", html)

    def test_06_api_permit_details(self):
        """Verify API returns structured JSON for modal preview."""
        permit = db.query("SELECT id FROM permits WHERE permit_number = 'RCO26041'", one=True)
        p_id = permit["id"]
        self.login_as("admin", "admin123")
        res = self.client.get(f"/api/permits/{p_id}/details")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["rawana_no"], "RCO26041")
        self.assertEqual(data["data"]["quantity_mt"], 30.39)


if __name__ == "__main__":
    unittest.main()
