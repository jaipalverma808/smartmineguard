"""
Migration & Seeding script for real-world e-Rawana data:
HSIIDC Ltd. (Khanak Stone Mines), Truck HR-46-D-2823, e-Rawana RCO26041,
Tax Invoice 26-27/S8/29748, and Weighment Slip.
"""
import sqlite3
import hashlib
import time
from datetime import datetime, timedelta
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Config
from services.db import db

def run_seed():
    db.run_auto_migrations()
    
    # 1. Insert or update HSIIDC Khanak Stone Mines (Mine ID 5 or check existing)
    existing_mine = db.query("SELECT * FROM mines WHERE mine_code = 'MN-HR-BHW-05'", one=True)
    if not existing_mine:
        mine_id = db.execute("""
            INSERT INTO mines (mine_code, name, mineral, district, state, latitude, longitude,
                               authorized_annual_quota_mt, current_dispatch_mt, status, operator_name, contact_phone)
            VALUES ('MN-HR-BHW-05', 'HSIIDC Ltd. (Khanak Stone Mines)', 'Blue Stone', 'Bhiwani', 'Haryana',
                    28.8475, 75.8920, 250000.0, 48290.0, 'OPERATIONAL',
                    'Haryana State Industrial Infrastructure Development Corporation Limited / HSIIDC',
                    '+91 1664 242250')
        """)
        print(f"Created HSIIDC Khanak mine with ID: {mine_id}")
    else:
        mine_id = existing_mine["id"]
        print(f"HSIIDC Khanak mine exists with ID: {mine_id}")

    # 2. Insert or update Truck HR46D2823 (Registration: HR46D2823, formatted HR-46-D-2823)
    existing_truck = db.query("SELECT * FROM trucks WHERE registration_number = 'HR46D2823'", one=True)
    if not existing_truck:
        truck_id = db.execute("""
            INSERT INTO trucks (registration_number, vehicle_type, registered_owner, driver_name, driver_phone,
                                tare_weight_mt, max_capacity_mt, rfid_tag, gps_imei, status, current_lat, current_lng,
                                assigned_mine_id, allowed_rounds_per_day, completed_rounds_today, current_round_number)
            VALUES ('HR46D2823', '10-Wheeler Tipper Truck', 'Neelkanth Logistics Pvt Ltd', 'Sunil Kumar', '+91 98124 55678',
                    11.87, 45.0, 'RFID-HR46-2823', '864201045678999', 'WEIGHED', 28.8475, 75.8920,
                    ?, 4, 1, 1)
        """, (mine_id,))
        print(f"Created Truck HR46D2823 with ID: {truck_id}")
    else:
        truck_id = existing_truck["id"]
        db.execute("UPDATE trucks SET tare_weight_mt = 11.87, assigned_mine_id = ? WHERE id = ?", (mine_id, truck_id))
        print(f"Truck HR46D2823 exists with ID: {truck_id}")

    # 3. Add Destination: M/S Neelkanth Stone Crusher L-136, Khanak
    existing_dest = db.query("SELECT * FROM destinations WHERE name LIKE '%Neelkanth Stone Crusher%'", one=True)
    if not existing_dest:
        db.execute("""
            INSERT INTO destinations (name, destination_type, license_number, district, state, latitude, longitude, authorized_minerals, status)
            VALUES ('M/S Neelkanth Stone Crusher L-136', 'CRUSHER', 'CR-HR-BHW-136', 'Bhiwani', 'Haryana',
                    28.8520, 75.8850, 'Blue Stone', 'AUTHORIZED')
        """)

    # 4. Insert or update e-Rawana Permit RCO26041 matching Document 1 & 2
    existing_permit = db.query("SELECT * FROM permits WHERE permit_number = 'RCO26041'", one=True)
    qr_hash = hashlib.sha256(b"SMARTMINEGUARD:RCO26041:HR46D2823:HSIIDC:KHANAK").hexdigest()
    
    issued_dt = "2026-09-11 21:24:46"
    expires_dt = "2026-09-12 09:24:46"
    
    waypoints = [
        [28.8475, 75.8920],
        [28.8490, 75.8890],
        [28.8520, 75.8850]
    ]
    import json
    waypoints_json = json.dumps(waypoints)

    if not existing_permit:
        permit_id = db.execute("""
            INSERT INTO permits (permit_number, qr_code_hash, truck_id, mine_id, mineral,
                                permitted_weight_mt, source_name, destination_name, destination_lat, destination_lng,
                                buyer_name, buyer_type, buyer_address, buyer_gstn,
                                quarry_name, contractor_name, contractor_gstn,
                                rate_per_mt, taxable_amount, cgst_rate, cgst_amount, sgst_rate, sgst_amount, total_amount,
                                hsn_code, weighment_slip_no, auction_no, pit_lot_no, customer_code, balance_amount,
                                cctv_image_front, cctv_image_back,
                                issued_at, expires_at, status, route_waypoints_json)
            VALUES ('RCO26041', ?, ?, ?, 'Blue Stone',
                    30.39, 'HSIIDC Ltd. (Khanak Stone Mines)', 'M/S NEELKANTH STONE CRUSHER L-136', 28.8520, 75.8850,
                    'M/S NEELKANTH STONE CRUSHER L-136', 'Registered Entity',
                    'M/S NEELKANTH STONE CRUSHER, G.J.M. VILLAGE KHANAK TEHSIL TOSHAM 127040', '06AAAAN2658Q1Z4',
                    'HARYANA STATE INDUSTRIAL INFRASTRUCTURE DEVELOPMENT CORPORATION LIMITED/ HSIIDC',
                    'HARYANA STATE INDUSTRIAL INFRASTRUCTURE DEVELOPMENT CORPORATION LIMITED/ HSIIDC',
                    '06AAACH4114R2ZG',
                    336.00, 10211.04, 2.50, 255.28, 2.50, 255.28, 10721.59,
                    '2517', '26-27/S8/29748', 'MSTC/CDG/HSIIDC Limited/56/HARYANA/26-27/30341', '21', '61', 262969.59,
                    'static/images/weighbridge/cctv_anpr_front.jpg', 'static/images/weighbridge/cctv_bed_overhead.jpg',
                    ?, ?, 'ACTIVE', ?)
        """, (qr_hash, truck_id, mine_id, issued_dt, expires_dt, waypoints_json))
        print(f"Created e-Rawana Permit RCO26041 with ID: {permit_id}")
    else:
        permit_id = existing_permit["id"]
        db.execute("""
            UPDATE permits SET
                truck_id = ?, mine_id = ?, mineral = 'Blue Stone', permitted_weight_mt = 30.39,
                buyer_name = 'M/S NEELKANTH STONE CRUSHER L-136', buyer_type = 'Registered Entity',
                buyer_address = 'M/S NEELKANTH STONE CRUSHER, G.J.M. VILLAGE KHANAK TEHSIL TOSHAM 127040',
                buyer_gstn = '06AAAAN2658Q1Z4',
                quarry_name = 'HARYANA STATE INDUSTRIAL INFRASTRUCTURE DEVELOPMENT CORPORATION LIMITED/ HSIIDC',
                contractor_name = 'HARYANA STATE INDUSTRIAL INFRASTRUCTURE DEVELOPMENT CORPORATION LIMITED/ HSIIDC',
                contractor_gstn = '06AAACH4114R2ZG',
                rate_per_mt = 336.00, taxable_amount = 10211.04, cgst_rate = 2.50, cgst_amount = 255.28,
                sgst_rate = 2.50, sgst_amount = 255.28, total_amount = 10721.59, hsn_code = '2517',
                weighment_slip_no = '26-27/S8/29748', auction_no = 'MSTC/CDG/HSIIDC Limited/56/HARYANA/26-27/30341',
                pit_lot_no = '21', customer_code = '61', balance_amount = 262969.59,
                cctv_image_front = 'static/images/weighbridge/cctv_anpr_front.jpg',
                cctv_image_back = 'static/images/weighbridge/cctv_bed_overhead.jpg',
                status = 'ACTIVE'
            WHERE id = ?
        """, (truck_id, mine_id, permit_id))
        print(f"Updated e-Rawana Permit RCO26041 (ID: {permit_id})")

    # 5. Insert or update Trip for this permit
    existing_trip = db.query("SELECT * FROM trips WHERE permit_id = ?", (permit_id,), one=True)
    if not existing_trip:
        trip_id = db.execute("""
            INSERT INTO trips (trip_number, permit_id, truck_id, mine_id, status, start_time,
                               planned_distance_km, actual_distance_km, max_recorded_speed_kmh, avg_speed_kmh, risk_score, risk_level)
            VALUES ('TRIP-HR-2026-0881', ?, ?, ?, 'IN_TRANSIT', ?,
                    18.5, 4.2, 42.0, 32.0, 8, 'LOW')
        """, (permit_id, truck_id, mine_id, issued_dt))
        print(f"Created Trip with ID: {trip_id}")
    else:
        trip_id = existing_trip["id"]

    # 6. Insert or update Weighment matching Document 3
    existing_wb = db.query("SELECT * FROM weighments WHERE permit_id = ?", (permit_id,), one=True)
    if not existing_wb:
        wb_id = db.execute("""
            INSERT INTO weighments (trip_id, permit_id, truck_id, weighbridge_code, weighbridge_name,
                                    gross_weight_mt, tare_weight_mt, net_weight_mt, permitted_weight_mt, difference_mt,
                                    is_overweight, timestamp, measurement_source, measurement_status,
                                    slip_number, pit_lot_no, customer_code, balance_amount, auction_number, cctv_image_url)
            VALUES (?, ?, ?, 'WB-KHANAK-01', 'Khanak Automated Central Weighbridge #1',
                    42.26, 11.87, 30.39, 30.39, 0.0,
                    0, ?, 'AUTOMATED_WEIGHBRIDGE_SCALE', 'VERIFIED',
                    '26-27/S8/29748', '21', '61', 262969.59, 'MSTC/CDG/HSIIDC Limited/56/HARYANA/26-27/30341',
                    'static/images/weighbridge/cctv_anpr_front.jpg')
        """, (trip_id, permit_id, truck_id, issued_dt))
        print(f"Created Weighment record with ID: {wb_id}")
    else:
        wb_id = existing_wb["id"]
        db.execute("""
            UPDATE weighments SET
                gross_weight_mt = 42.26, tare_weight_mt = 11.87, net_weight_mt = 30.39,
                permitted_weight_mt = 30.39, difference_mt = 0.0, is_overweight = 0,
                slip_number = '26-27/S8/29748', pit_lot_no = '21', customer_code = '61',
                balance_amount = 262969.59, auction_number = 'MSTC/CDG/HSIIDC Limited/56/HARYANA/26-27/30341',
                cctv_image_url = 'static/images/weighbridge/cctv_anpr_front.jpg'
            WHERE id = ?
        """, (wb_id,))

    # 7. Also enrich any existing permits in DB that have null financials
    permits = db.query("SELECT * FROM permits WHERE rate_per_mt IS NULL OR taxable_amount IS NULL")
    for p in permits:
        rate = 320.0 if "Sand" in p.get("mineral", "") else 336.0
        taxable = round(rate * float(p["permitted_weight_mt"]), 2)
        cgst = round(taxable * 0.025, 2)
        sgst = round(taxable * 0.025, 2)
        total = round(taxable + cgst + sgst, 2)
        db.execute("""
            UPDATE permits SET
                buyer_type = 'Registered Entity',
                rate_per_mt = ?,
                taxable_amount = ?,
                cgst_rate = 2.50,
                cgst_amount = ?,
                sgst_rate = 2.50,
                sgst_amount = ?,
                total_amount = ?,
                hsn_code = '2517',
                weighment_slip_no = ?,
                cctv_image_front = 'static/images/weighbridge/cctv_anpr_front.jpg',
                cctv_image_back = 'static/images/weighbridge/cctv_bed_overhead.jpg'
            WHERE id = ?
        """, (rate, taxable, cgst, sgst, total, f"26-27/S8/{29000 + p['id']}", p["id"]))

    print("Seeding complete successfully!")

if __name__ == "__main__":
    run_seed()
