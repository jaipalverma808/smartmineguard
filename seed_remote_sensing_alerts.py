import sys
import os
import json
from datetime import datetime

sys.path.append(os.path.abspath("."))
from services.db import db

# Check if alerts already exist
existing = db.query("SELECT * FROM alerts WHERE alert_code IN ('ALT-2026-SAR-001', 'ALT-2026-DRN-002')")
if not existing:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""
        INSERT INTO alerts (alert_code, alert_type, severity, risk_score, description, evidence_json, status, created_at, updated_at)
        VALUES 
        (
            'ALT-2026-SAR-001', 
            'SATELLITE_SAR_ANOMALY', 
            'CRITICAL', 
            35, 
            'SAR SATELLITE RADAR ANOMALY: Automated radar backscatter change detected 14,200 m² unapproved excavation in Yamuna Riverbed Buffer Zone (Reach #3 Outskirts, 28.1824° N, 76.5120° E). No matching active mining permit found.', 
            ?, 
            'NEW', 
            ?, 
            ?
        ),
        (
            'ALT-2026-DRN-002', 
            'DRONE_VOLUMETRIC_LEAKAGE', 
            'CRITICAL', 
            35, 
            'High-precision Drone LiDAR DEM volumetric audit detected 14.5% pit void over-extraction (+51,109.6 MT unaccounted mineral removed vs official e-Rawaana permits).', 
            ?, 
            'NEW', 
            ?, 
            ?
        )
    """, (
        json.dumps({"sensor": "Sentinel-1 SAR C-Band", "area_sqm": 14200, "coherence_drop": 0.68, "lat": 28.1824, "lng": 76.5120, "reach": "Yamuna River Sand Reach #3"}),
        now_str, now_str,
        json.dumps({"survey_type": "Drone LiDAR DEM", "void_m3": 249129.4, "extracted_mt": 403589.6, "erawana_mt": 352480.0, "leakage_mt": 51109.6, "evaded_royalty_inr": 19166100.0}),
        now_str, now_str
    ))
    print("Inserted SAR and Drone alerts successfully.")
else:
    print("Alerts already exist.")
