"""
Seed script to establish realistic dummy data for testing global mine and sub-mine filtering.
Complies with SMARTMINEGUARD requirements Sections 12 & 13.
"""
from services.db import db
from datetime import datetime, timedelta

def seed_filter_test_data():
    conn = db.get_connection()
    c = conn.cursor()

    # Clear existing operational tables to avoid ghost links
    c.execute("DELETE FROM gps_tamper_events")
    c.execute("DELETE FROM investigations")
    c.execute("DELETE FROM alerts")
    c.execute("DELETE FROM weighments")
    c.execute("DELETE FROM trips")
    c.execute("DELETE FROM permits")
    c.execute("DELETE FROM drivers")
    c.execute("DELETE FROM trucks")

    # 1. TRUCKS (24 trucks total across Mines 1, 2, 3)
    truck_specs = [
        # --- Mine 1 (Aravalli Quartzite Quarry Block A) ---
        # Sub-Mine 5: QB-ALW-05 (3 trucks)
        (1, 'HR26AB1234', '10-Wheeler Tipper Truck', 'Shri Ram Logistics', 'Vikram Singh', '+91 98123 45678', 11.5, 28.0, 1, 5, 'IN_TRANSIT', 27.8520, 76.4530, 92, 'CRITICAL', 'JAMMER_DETECTED', 3, 2, 0, 1, 8, 23.4, 45, -78, 38.5),
        (2, 'RJ14GA5521', '12-Wheeler Dump Truck', 'Aravalli Freightways', 'Ramesh Gurjar', '+91 94141 89765', 12.8, 32.0, 1, 5, 'IN_TRANSIT', 27.6800, 76.3500, 15, 'LOW', 'NORMAL', 0, 0, 0, 0, 14, 25.1, 98, -62, 45.2),
        (3, 'OD02BA8812', '10-Wheeler Tipper Truck', 'Kalinga Mineral Carrier', 'Sunil Yadav', '+91 99370 12345', 11.2, 28.0, 1, 5, 'IN_TRANSIT', 27.6100, 76.5800, 75, 'HIGH', 'TAMPERED', 1, 0, 2, 0, 10, 18.2, 70, -75, 41.0),

        # Sub-Mine 15: QB-ALW-15 (4 trucks)
        (4, 'HR38EF9012', '14-Wheeler Multi-Axle', 'Highway Haulers Corp', 'Balwinder Singh', '+91 98188 67890', 14.0, 40.0, 1, 15, 'IN_TRANSIT', 27.9500, 76.5100, 45, 'MEDIUM', 'NORMAL', 0, 0, 0, 0, 13, 24.8, 92, -65, 44.0),
        (5, 'RJ32CD3344', '10-Wheeler Tipper Truck', 'Meena Stone Transporters', 'Manoj Meena', '+91 97820 44556', 11.0, 26.0, 1, 15, 'IN_TRANSIT', 27.5630, 76.6110, 10, 'LOW', 'NORMAL', 0, 0, 0, 0, 12, 24.9, 95, -64, 43.8),
        (6, 'DL1LA9022', '10-Wheeler Tipper Truck', 'Capital Bulk Carriers', 'Dharmendra Sharma', '+91 98111 22334', 11.6, 28.0, 1, 15, 'IN_TRANSIT', 28.1850, 76.6200, 20, 'LOW', 'NORMAL', 0, 0, 0, 0, 14, 25.0, 96, -63, 44.5),
        (7, 'UP16BT4055', '12-Wheeler Dump Truck', 'Noida Aggregate Movers', 'Satish Kumar', '+91 98710 55443', 13.0, 34.0, 1, 15, 'IN_TRANSIT', 27.7900, 76.4100, 35, 'LOW', 'BLINDSPOT', 2, 0, 0, 0, 7, 24.2, 80, -92, 35.0),

        # Sub-Mine 33: QB-ALW-33 (5 trucks)
        (8, 'RJ02CB7811', '10-Wheeler Tipper Truck', 'Mewat Minerals Transport', 'Imran Khan', '+91 99291 77665', 11.4, 28.0, 1, 33, 'IN_TRANSIT', 27.6300, 76.5200, 85, 'CRITICAL', 'PROHIBITED_ZONE', 0, 1, 1, 3, 11, 23.9, 88, -70, 42.1),
        (9, 'RJ14GA9988', '14-Wheeler Multi-Axle', 'Everest Heavy Movers', 'Gopal Jat', '+91 94140 11998', 14.5, 45.0, 1, 33, 'IN_TRANSIT', 27.5900, 76.4800, 68, 'HIGH', 'NORMAL', 0, 0, 0, 0, 12, 24.5, 90, -68, 43.0),
        (10, 'HR55XY1122', '12-Wheeler Dump Truck', 'Aravalli Rock Logistics', 'Surender Singh', '+91 98120 33445', 13.2, 35.0, 1, 33, 'IN_TRANSIT', 27.6500, 76.5400, 72, 'HIGH', 'JAMMER_DETECTED', 2, 3, 0, 0, 9, 23.0, 75, -80, 37.0),
        (11, 'RJ02CD5566', '10-Wheeler Tipper Truck', 'Rajputana Earthmovers', 'Pradeep Rathore', '+91 97830 55667', 11.8, 28.0, 1, 33, 'IN_TRANSIT', 27.6200, 76.5100, 55, 'MEDIUM', 'NORMAL', 0, 0, 0, 0, 13, 24.7, 94, -66, 43.5),
        (12, 'HR26ZZ7788', '14-Wheeler Multi-Axle', 'Gurgaon Freight Consortium', 'Harpreet Sandhu', '+91 98110 77889', 14.2, 42.0, 1, 33, 'IN_TRANSIT', 27.6700, 76.5300, 60, 'MEDIUM', 'NORMAL', 0, 0, 0, 0, 14, 25.0, 92, -64, 44.2),

        # --- Mine 2 (Kotputli High-Grade Limestone Lease) ---
        # Sub-Mine 37: QB-KOT-01 (3 trucks)
        (13, 'RJ32KL1001', '12-Wheeler Dump Truck', 'Kotputli Lime Transport', 'Babulal Saini', '+91 94142 10011', 12.5, 32.0, 2, 37, 'IN_TRANSIT', 27.7100, 76.2100, 40, 'MEDIUM', 'NORMAL', 0, 0, 0, 0, 13, 24.8, 95, -63, 44.0),
        (14, 'RJ32KL1002', '10-Wheeler Tipper Truck', 'Kotputli Lime Transport', 'Ramkishore Gurjar', '+91 94142 10022', 11.5, 28.0, 2, 37, 'IN_TRANSIT', 27.7200, 76.2200, 78, 'HIGH', 'JAMMER_DETECTED', 1, 2, 0, 0, 8, 23.5, 60, -82, 36.5),
        (15, 'RJ32KL1003', '14-Wheeler Multi-Axle', 'Shree Cement Logistics', 'Mukesh Yadav', '+91 94142 10033', 14.0, 40.0, 2, 37, 'IN_TRANSIT', 27.7300, 76.2000, 25, 'LOW', 'NORMAL', 0, 0, 0, 0, 14, 25.1, 98, -61, 45.0),

        # Sub-Mine 38: QB-KOT-02 (3 trucks)
        (16, 'RJ32KL1004', '10-Wheeler Tipper Truck', 'Toran Minerals Co', 'Dinesh Meena', '+91 94142 10044', 11.2, 28.0, 2, 38, 'IN_TRANSIT', 27.7050, 76.1950, 20, 'LOW', 'NORMAL', 0, 0, 0, 0, 12, 24.9, 90, -65, 43.2),
        (17, 'RJ32KL1005', '12-Wheeler Dump Truck', 'Toran Minerals Co', 'Vinod Sharma', '+91 94142 10055', 12.8, 32.0, 2, 38, 'IN_TRANSIT', 27.6980, 76.1890, 50, 'MEDIUM', 'TAMPERED', 0, 0, 1, 0, 11, 21.0, 85, -72, 40.0),
        (18, 'RJ32KL1006', '14-Wheeler Multi-Axle', 'Behror Freight Line', 'Ashok Kumar', '+91 94142 10066', 14.2, 42.0, 2, 38, 'IN_TRANSIT', 27.7150, 76.2050, 15, 'LOW', 'NORMAL', 0, 0, 0, 0, 13, 24.8, 92, -64, 44.1),

        # Sub-Mine 39: QB-KOT-03 (2 trucks)
        (19, 'RJ32KL1007', '10-Wheeler Tipper Truck', 'Dolomite Carriers', 'Subhash Chand', '+91 94142 10077', 11.5, 28.0, 2, 39, 'IN_TRANSIT', 27.7080, 76.2150, 65, 'HIGH', 'BLINDSPOT', 3, 0, 0, 0, 6, 24.1, 70, -90, 34.5),
        (20, 'RJ32KL1008', '12-Wheeler Dump Truck', 'Dolomite Carriers', 'Sanjay Rawat', '+91 94142 10088', 13.0, 34.0, 2, 39, 'IN_TRANSIT', 27.7010, 76.2250, 30, 'LOW', 'NORMAL', 0, 0, 0, 0, 14, 25.0, 96, -62, 45.0),

        # --- Mine 3 (Khol Silica Sand & Stone Pit) ---
        # Sub-Mine 41: QB-REW-01 (2 trucks)
        (21, 'HR36SS2001', '10-Wheeler Tipper Truck', 'Khol Sand Transport', 'Pawan Kumar', '+91 98122 20011', 11.0, 26.0, 3, 41, 'IN_TRANSIT', 28.1880, 76.6210, 70, 'HIGH', 'TAMPERED', 0, 0, 2, 0, 11, 20.5, 80, -74, 40.5),
        (22, 'HR36SS2002', '12-Wheeler Dump Truck', 'Khol Sand Transport', 'Jagdish Chander', '+91 98122 20022', 12.6, 32.0, 3, 41, 'IN_TRANSIT', 28.1850, 76.6250, 15, 'LOW', 'NORMAL', 0, 0, 0, 0, 14, 25.1, 98, -60, 45.2),

        # Sub-Mine 42: QB-REW-02 (2 trucks)
        (23, 'HR36SS2003', '10-Wheeler Tipper Truck', 'Rewari Glass Sands', 'Deepak Saini', '+91 98122 20033', 11.4, 28.0, 3, 42, 'IN_TRANSIT', 28.1920, 76.6180, 60, 'MEDIUM', 'BLINDSPOT', 1, 0, 0, 0, 9, 24.2, 85, -82, 38.0),
        (24, 'HR36SS2004', '12-Wheeler Dump Truck', 'Rewari Glass Sands', 'Mahesh Verma', '+91 98122 20044', 12.8, 32.0, 3, 42, 'IN_TRANSIT', 28.1820, 76.6300, 25, 'LOW', 'NORMAL', 0, 0, 0, 0, 13, 24.9, 95, -63, 44.0),
    ]

    for t in truck_specs:
        c.execute("""
            INSERT INTO trucks (
                id, registration_number, vehicle_type, registered_owner, driver_name, driver_phone,
                tare_weight_mt, max_capacity_mt, assigned_mine_id, sub_mine_id, status,
                current_lat, current_lng, current_risk_score, current_risk_level, gps_status,
                network_blindspot_count, jammer_detected_count, tamper_count, prohibited_zone_count,
                satellite_count, external_power_volts, backup_battery_pct, signal_strength_dbm, carrier_noise_ratio_cno,
                transponder_model, allowed_rounds_per_day, completed_rounds_today, current_round_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'AIS-140 IRNSS v2', 4, 1, 1)
        """, t)

    # 2. PERMITS (e-Rawaana Passes for trucks)
    # Specified dispatch MTs:
    # Sub-Mine 5 (QB-ALW-05): 75.5 MT (e.g. 30.0 + 25.5 + 20.0 = 75.5)
    # Sub-Mine 15 (QB-ALW-15): 182.3 MT (e.g. 48.0 + 45.3 + 44.0 + 45.0 = 182.3)
    # Sub-Mine 33 (QB-ALW-33): 520.0 MT (e.g. 104.0 * 5 = 520.0)
    # Total Mine 1 = 777.8 MT!
    permit_specs = [
        # Mine 1, Sub-Mine 5
        (1, 'SMG-2026-00101', 1, 1, 5, 'Quartzite Aggregate', 20.0, 'QB-ALW-05 Pit', 'Bhiwadi Crusher', 28.2100, 76.8600, 'Bhiwadi ReadyMix Ltd'),
        (2, 'SMG-2026-00102', 2, 1, 5, 'Quartzite Boulder', 25.0, 'QB-ALW-05 Pit', 'Neemrana Industrial Zone', 27.9850, 76.3850, 'Neemrana Builders'),
        (3, 'SMG-2026-00103', 3, 1, 5, 'Quartzite Grit', 20.0, 'QB-ALW-05 Pit', 'Manesar Hub', 28.3500, 76.9400, 'DLF Infra'),

        # Mine 1, Sub-Mine 15
        (4, 'SMG-2026-00104', 4, 1, 15, 'Quartzite Sand', 40.0, 'QB-ALW-15 Lot', 'Gurgaon ReadyMix', 28.4500, 77.0200, 'Capital Concrete'),
        (5, 'SMG-2026-00105', 5, 1, 15, 'Quartzite Aggregate', 26.0, 'QB-ALW-15 Lot', 'Alwar Depot', 27.5700, 76.6000, 'Rajasthan Concretes'),
        (6, 'SMG-2026-00106', 6, 1, 15, 'Quartzite Boulder', 28.0, 'QB-ALW-15 Lot', 'Rewari Toll Terminal', 28.1800, 76.6100, 'Apex Roadways'),
        (7, 'SMG-2026-00107', 7, 1, 15, 'Quartzite Aggregate', 34.0, 'QB-ALW-15 Lot', 'Noida Metro Yard', 28.5300, 77.3900, 'Delhi Metro Infra'),

        # Mine 1, Sub-Mine 33
        (8, 'SMG-2026-00108', 8, 1, 33, 'Quartzite Ballast', 28.0, 'QB-ALW-33 Escarpment', 'Northern Railway Yard', 28.2000, 76.8000, 'Indian Railways'),
        (9, 'SMG-2026-00109', 9, 1, 33, 'Quartzite Large Block', 45.0, 'QB-ALW-33 Escarpment', 'Faridabad Express Corridor', 28.4000, 77.3000, 'NHAI Expressway'),
        (10, 'SMG-2026-00110', 10, 1, 33, 'Quartzite Boulder', 35.0, 'QB-ALW-33 Escarpment', 'Sohna Industrial Plot', 28.2500, 77.0600, 'Sohna Minerals'),
        (11, 'SMG-2026-00111', 11, 1, 33, 'Quartzite Grit', 28.0, 'QB-ALW-33 Escarpment', 'Bhiwadi Yard 2', 28.2150, 76.8500, 'Bhiwadi Builders'),
        (12, 'SMG-2026-00112', 12, 1, 33, 'Quartzite Ballast', 42.0, 'QB-ALW-33 Escarpment', 'Manesar Metro Yard', 28.3600, 76.9300, 'Haryana Rail Corp'),

        # Mine 2 (Kotputli Limestone): Sub-Mines 37, 38, 39 (Total = 320 MT)
        (13, 'SMG-2026-00201', 13, 2, 37, 'Limestone High-Grade', 32.0, 'QB-KOT-01 Sector A', 'Kotputli Clinker Plant', 27.7050, 76.2050, 'Shree Cement'),
        (14, 'SMG-2026-00202', 14, 2, 37, 'Limestone Raw', 28.0, 'QB-KOT-01 Sector A', 'Kotputli Kiln #2', 27.7120, 76.2150, 'UltraTech Clinker'),
        (15, 'SMG-2026-00203', 15, 2, 37, 'Limestone Chemical', 40.0, 'QB-KOT-01 Sector A', 'Neemrana Chemical Works', 27.9900, 76.3800, 'Neemrana Chemicals'),
        (16, 'SMG-2026-00204', 16, 2, 38, 'Commercial Limestone', 28.0, 'QB-KOT-02 Pit B', 'Behror Cement Depot', 27.8900, 76.2800, 'Behror Buildcon'),
        (17, 'SMG-2026-00205', 17, 2, 38, 'Commercial Limestone', 32.0, 'QB-KOT-02 Pit B', 'Kotputli Grinding Unit', 27.7000, 76.1900, 'JK Cement Works'),
        (18, 'SMG-2026-00206', 18, 2, 38, 'Commercial Limestone', 40.0, 'QB-KOT-02 Pit B', 'Shahpura Toll Depot', 27.3900, 75.9600, 'Jaipur Highway Infra'),
        (19, 'SMG-2026-00207', 19, 2, 39, 'Dolomite Stone', 28.0, 'QB-KOT-03 Plot', 'Alwar Steel Foundry', 27.5600, 76.6200, 'Alwar Alloy Steels'),
        (20, 'SMG-2026-00208', 20, 2, 39, 'Dolomite Stone', 34.0, 'QB-KOT-03 Plot', 'Bhiwadi Foundry Zone', 28.2100, 76.8650, 'Foundry Minerals'),

        # Mine 3 (Khol Silica Sand): Sub-Mines 41, 42 (Total = 95 MT)
        (21, 'SMG-2026-00301', 21, 3, 41, 'Silica Sand Grade-I', 26.0, 'QB-REW-01 Concession', 'Bawal Glass Containers', 28.0800, 76.5900, 'Asahi Glass India'),
        (22, 'SMG-2026-00302', 22, 3, 41, 'Silica Sand Riverbed', 30.0, 'QB-REW-01 Concession', 'Rewari Glassworks', 28.1800, 76.6150, 'Haryana Glass Ltd'),
        (23, 'SMG-2026-00303', 23, 3, 42, 'Silica Sand Grade-II', 28.0, 'QB-REW-02 Basin', 'Dharuhera Ceramics', 28.2050, 76.7900, 'Orient Bell Ceramics'),
        (24, 'SMG-2026-00304', 24, 3, 42, 'Silica Sand Grade-II', 30.0, 'QB-REW-02 Basin', 'Gurgaon Foundry Supply', 28.4400, 77.0100, 'Modern Foundries Ltd')
    ]

    for p in permit_specs:
        c.execute("""
            INSERT INTO permits (
                id, permit_number, qr_code_hash, truck_id, mine_id, quarry_block_id, mineral,
                permitted_weight_mt, source_name, destination_name, destination_lat, destination_lng,
                buyer_name, status, issued_at, expires_at
            ) VALUES (?, ?, 'HASH_QR_' || ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', datetime('now', '-4 hours'), datetime('now', '+8 hours'))
        """, (p[0], p[1], str(p[0])) + p[2:])

    # 3. TRIPS & WEIGHMENTS (Dispatch tonnage accurately summing to prompt Section 13 specs)
    # Weighments for Mine 1:
    # Sub-Mine 5: 31.0 + 24.5 + 20.0 = 75.5 MT
    # Sub-Mine 15: 48.0 + 45.3 + 44.0 + 45.0 = 182.3 MT
    # Sub-Mine 33: 110.0 + 105.0 + 100.0 + 105.0 + 100.0 = 520.0 MT
    # Total Mine 1 = 777.8 MT
    # Weighments for Mine 2:
    # Sub-Mine 37: 50.0 + 45.0 + 45.0 = 140.0 MT
    # Sub-Mine 38: 38.0 + 36.0 + 36.0 = 110.0 MT
    # Sub-Mine 39: 35.0 + 35.0 = 70.0 MT
    # Total Mine 2 = 320.0 MT
    # Weighments for Mine 3:
    # Sub-Mine 41: 28.0 + 27.0 = 55.0 MT
    # Sub-Mine 42: 20.0 + 20.0 = 40.0 MT
    # Total Mine 3 = 95.0 MT
    weighment_weights = {
        1: (31.0, 20.0, 11.0, 1),   # Overweight anomaly!
        2: (24.5, 25.0, -0.5, 0),
        3: (20.0, 20.0, 0.0, 0),

        4: (48.0, 40.0, 8.0, 1),    # Overweight anomaly!
        5: (45.3, 26.0, 19.3, 1),
        6: (44.0, 28.0, 16.0, 1),
        7: (45.0, 34.0, 11.0, 1),

        8: (110.0, 28.0, 82.0, 1),
        9: (105.0, 45.0, 60.0, 1),
        10: (100.0, 35.0, 65.0, 1),
        11: (105.0, 28.0, 77.0, 1),
        12: (100.0, 42.0, 58.0, 1),

        13: (50.0, 32.0, 18.0, 1),
        14: (45.0, 28.0, 17.0, 1),
        15: (45.0, 40.0, 5.0, 1),

        16: (38.0, 28.0, 10.0, 1),
        17: (36.0, 32.0, 4.0, 1),
        18: (36.0, 40.0, -4.0, 0),

        19: (35.0, 28.0, 7.0, 1),
        20: (35.0, 34.0, 1.0, 0),

        21: (28.0, 26.0, 2.0, 0),
        22: (27.0, 30.0, -3.0, 0),
        23: (20.0, 28.0, -8.0, 0),
        24: (20.0, 30.0, -10.0, 0),
    }

    for tid in range(1, 25):
        # find mine_id
        mid = 1 if tid <= 12 else (2 if tid <= 20 else 3)
        c.execute("""
            INSERT INTO trips (
                id, trip_number, permit_id, truck_id, mine_id, status, start_time,
                planned_distance_km, actual_distance_km, max_recorded_speed_kmh, avg_speed_kmh
            ) VALUES (?, 'TRIP-2026-' || ?, ?, ?, ?, 'IN_TRANSIT', datetime('now', '-2 hours'), 65.0, 42.0, 62.0, 45.0)
        """, (tid, 1000 + tid, tid, tid, mid))

        w = weighment_weights[tid]
        c.execute("""
            INSERT INTO weighments (
                id, trip_id, permit_id, truck_id, weighbridge_code, weighbridge_name,
                gross_weight_mt, tare_weight_mt, net_weight_mt, permitted_weight_mt, difference_mt, is_overweight, timestamp
            ) VALUES (?, ?, ?, ?, 'WB-01', 'Scale Station 1', ?, 12.0, ?, ?, ?, ?, datetime('now', '-90 minutes'))
        """, (tid, tid, tid, tid, w[0] + 12.0, w[0], w[1], w[2], w[3]))

    # 4. ALERTS:
    # Target Alert Counts:
    # Mine 1:
    #   Sub-Mine 5 (QB-ALW-05): 5 alerts
    #   Sub-Mine 15 (QB-ALW-15): 2 alerts
    #   Sub-Mine 33 (QB-ALW-33): 10 alerts
    #   Total Mine 1 = 17 alerts
    # Mine 2:
    #   Sub-Mine 37: 3 alerts
    #   Sub-Mine 38: 2 alerts
    #   Sub-Mine 39: 2 alerts
    #   Total Mine 2 = 7 alerts
    # Mine 3:
    #   Sub-Mine 41: 2 alerts
    #   Sub-Mine 42: 2 alerts
    #   Total Mine 3 = 4 alerts
    # Statewide = 28 alerts!
    alert_specs = [
        # --- Mine 1: Sub-Mine 5 (5 alerts on trucks 1, 2, 3) ---
        (1, 'ALT-2026-00101', 1, 1, 1, 'WEIGHT_ANOMALY', 'CRITICAL', 30, 'Weighbridge Net Weight 31.0 MT exceeds e-Rawaana limit 20.0 MT (+11 MT overload)', 'NEW'),
        (2, 'ALT-2026-00102', 1, 1, 1, 'ROUTE_DEVIATION', 'HIGH', 20, 'Vehicle deviated 1.4km from legal transport corridor toward unmonitored riverbed route', 'NEW'),
        (3, 'ALT-2026-00103', 1, 1, 1, 'GPS_BLACKOUT', 'HIGH', 20, 'GPS heartbeat lost for 14 minutes adjacent to Sariska buffer eco-sensitive perimeter', 'NEW'),
        (4, 'ALT-2026-00104', 3, 3, 3, 'TAMPER_DETECTED', 'CRITICAL', 25, 'AIS-140 enclosure microswitch triggered (wire cut / cabinet breach)', 'NEW'),
        (5, 'ALT-2026-00105', 3, 3, 3, 'PERMIT_REUSE', 'HIGH', 20, 'Attempted dispatch verification against already consumed e-Rawaana slip', 'NEW'),

        # --- Mine 1: Sub-Mine 15 (2 alerts on trucks 4, 7) ---
        (6, 'ALT-2026-00106', 4, 4, 4, 'WEIGHT_ANOMALY', 'HIGH', 20, 'Net weight 48.0 MT exceeds permit 40.0 MT (+8 MT excess load)', 'NEW'),
        (7, 'ALT-2026-00107', 7, 7, 7, 'BLINDSPOT_PROLONGED', 'MEDIUM', 15, 'Cellular tower handover delay exceeded 22 minutes on rural spur', 'UNDER_REVIEW'),

        # --- Mine 1: Sub-Mine 33 (10 alerts on trucks 8, 9, 10, 11, 12) ---
        (8, 'ALT-2026-00108', 8, 8, 8, 'PROHIBITED_ZONE_INCURSION', 'CRITICAL', 35, 'Truck entered unleased extraction escarpment block outside legal boundary', 'NEW'),
        (9, 'ALT-2026-00109', 8, 8, 8, 'JAMMER_DETECTED', 'CRITICAL', 30, 'C/No carrier-to-noise ratio collapsed to 0 dB-Hz while GPS power intact (Gamer active)', 'NEW'),
        (10, 'ALT-2026-00110', 8, 8, 8, 'WEIGHT_ANOMALY', 'HIGH', 25, 'Net weight 110.0 MT audited at weighbridge against permitted 28.0 MT (+82 MT overload)', 'NEW'),
        (11, 'ALT-2026-00111', 9, 9, 9, 'SPEED_VIOLATION', 'MEDIUM', 15, 'Tipper velocity recorded at 94 km/h exceeding 80 km/h statutory highway cap', 'NEW'),
        (12, 'ALT-2026-00112', 9, 9, 9, 'WEIGHT_ANOMALY', 'HIGH', 20, 'Net weight 105.0 MT exceeds sanctioned axle limits', 'NEW'),
        (13, 'ALT-2026-00113', 10, 10, 10, 'JAMMER_DETECTED', 'CRITICAL', 30, 'RF signature detected deliberate GPS frequency denial jammer', 'NEW'),
        (14, 'ALT-2026-00114', 10, 10, 10, 'NIGHT_HAULAGE_VIOLATION', 'MEDIUM', 15, 'Transit movement detected between 23:00 and 04:00 without night permit', 'NEW'),
        (15, 'ALT-2026-00115', 11, 11, 11, 'ROUTE_DEVIATION', 'HIGH', 20, 'Detour toward unregistered stone crusher cluster in Mewat foothills', 'NEW'),
        (16, 'ALT-2026-00116', 11, 11, 11, 'WEIGHT_ANOMALY', 'HIGH', 20, 'Excess weight 77.0 MT flagged at perimeter optical scale', 'NEW'),
        (17, 'ALT-2026-00117', 12, 12, 12, 'WEIGHT_ANOMALY', 'HIGH', 20, 'Multi-axle vehicle registered net 100.0 MT exceeding permit quota', 'NEW'),

        # --- Mine 2: Sub-Mine 37 (3 alerts on trucks 13, 14, 15) ---
        (18, 'ALT-2026-00201', 13, 13, 13, 'WEIGHT_ANOMALY', 'HIGH', 20, 'Kotputli Lime dispatch exceeded permitted tare ratio by 18.0 MT', 'NEW'),
        (19, 'ALT-2026-00202', 14, 14, 14, 'JAMMER_DETECTED', 'CRITICAL', 30, 'AIS-140 RF attenuation anomaly recorded near Behror interchange', 'NEW'),
        (20, 'ALT-2026-00203', 15, 15, 15, 'ROUTE_DEVIATION', 'MEDIUM', 15, 'Transit diverted from NH-48 toward rural bypass road', 'UNDER_REVIEW'),

        # --- Mine 2: Sub-Mine 38 (2 alerts on trucks 16, 17) ---
        (21, 'ALT-2026-00204', 16, 16, 16, 'WEIGHT_ANOMALY', 'HIGH', 20, 'Overweight dispatch +10 MT recorded at commercial pit exit', 'NEW'),
        (22, 'ALT-2026-00205', 17, 17, 17, 'TAMPER_DETECTED', 'HIGH', 25, 'Battery backup disconnection sensor triggered during transit', 'NEW'),

        # --- Mine 2: Sub-Mine 39 (2 alerts on trucks 19, 20) ---
        (23, 'ALT-2026-00206', 19, 19, 19, 'BLINDSPOT_PROLONGED', 'MEDIUM', 15, 'Signal loss duration 34 minutes in dolomite quarry sector', 'NEW'),
        (24, 'ALT-2026-00207', 19, 19, 19, 'WEIGHT_ANOMALY', 'MEDIUM', 15, 'Dolomite overload +7 MT flagged on perimeter load cell', 'NEW'),

        # --- Mine 3: Sub-Mine 41 (2 alerts on trucks 21, 22) ---
        (25, 'ALT-2026-00301', 21, 21, 21, 'TAMPER_DETECTED', 'CRITICAL', 30, 'External harness sever signal received from Khol riverbank truck', 'NEW'),
        (26, 'ALT-2026-00302', 21, 21, 21, 'UNAUTHORIZED_PIT_ENTRY', 'HIGH', 25, 'Vehicle detected inside seasonal riverbed zone without valid green voucher', 'NEW'),

        # --- Mine 3: Sub-Mine 42 (2 alerts on trucks 23, 24) ---
        (27, 'ALT-2026-00303', 23, 23, 23, 'BLINDSPOT_PROLONGED', 'MEDIUM', 15, 'Silica sand truck lost cellular uplink for 28 minutes near Rewari border', 'NEW'),
        (28, 'ALT-2026-00304', 24, 24, 24, 'SPEED_VIOLATION', 'LOW', 10, 'Moderate overspeeding recorded on Rewari industrial link', 'ACKNOWLEDGED')
    ]

    for a in alert_specs:
        c.execute("""
            INSERT INTO alerts (
                id, alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score,
                description, status, assigned_to_user_id, escalated_to_admin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 2, ?)
        """, a + (1 if a[6] == 'CRITICAL' else 0,))

    # 5. INVESTIGATIONS (6 cases total across Mines and Sub-Mines)
    # Mine 1, Sub-Mine 5: 1 case
    # Mine 1, Sub-Mine 15: 1 case
    # Mine 1, Sub-Mine 33: 2 cases
    # Mine 2, Sub-Mine 37: 1 case
    # Mine 3, Sub-Mine 41: 1 case
    inv_specs = [
        (1, 'SMG-2026-00041', 1, 1, 1, 1, 2, 'Enforcement Case: Overweight Dispatch & Route Deviation - Truck HR26AB1234', 'UNDER_INVESTIGATION', 'Vehicle HR26AB1234 dispatched with +11 MT excess Quartzite from Sariska Buffer Escarpment (QB-ALW-05). Intercepted at Kotputli.', 175000.0, 'static/reports/dossier_SMG-2026-00041.pdf'),
        (2, 'SMG-2026-00042', 6, 4, 4, 4, 2, 'Enforcement Case: Overload Transit - Truck HR38EF9012', 'UNDER_INVESTIGATION', 'Vehicle HR38EF9012 dispatched with +8 MT excess Quartzite from Goyal Mineral Lot (QB-ALW-15).', 95000.0, 'static/reports/dossier_SMG-2026-00042.pdf'),
        (3, 'SMG-2026-00043', 8, 8, 8, 8, 2, 'Enforcement Case: Prohibited Zone Extraction & Jammer Use - Truck RJ02CB7811', 'UNDER_INVESTIGATION', 'Vehicle RJ02CB7811 deployed active GPS jammer and incursion into unleased pit at Everest Rock Aggregates (QB-ALW-33).', 250000.0, 'static/reports/dossier_SMG-2026-00043.pdf'),
        (4, 'SMG-2026-00044', 13, 10, 10, 10, 2, 'Enforcement Case: Jammer Frequency Denial - Truck HR55XY1122', 'UNDER_INVESTIGATION', 'Hardware anti-tamper detected frequency denial jammer during night transit at Everest Rock Aggregates (QB-ALW-33).', 180000.0, 'static/reports/dossier_SMG-2026-00044.pdf'),
        (5, 'SMG-2026-00045', 19, 14, 14, 14, 2, 'Enforcement Case: Limestone RF Anomaly - Truck RJ32KL1002', 'UNDER_INVESTIGATION', 'Telemetry blackout and jammer signature detected at Kotputli Sector A (QB-KOT-01).', 120000.0, 'static/reports/dossier_SMG-2026-00045.pdf'),
        (6, 'SMG-2026-00046', 25, 21, 21, 21, 2, 'Enforcement Case: Riverbed Illegal Extraction - Truck HR36SS2001', 'UNDER_INVESTIGATION', 'Harness wire cut and prohibited riverbed ingress at Khol Riverbank Concession (QB-REW-01).', 210000.0, 'static/reports/dossier_SMG-2026-00046.pdf')
    ]

    for inv in inv_specs:
        c.execute("""
            INSERT INTO investigations (
                id, case_id, alert_id, trip_id, truck_id, permit_id, lead_officer_id,
                title, status, initial_findings, penalty_amount_inr, pdf_report_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, inv)

    # 6. GPS Tamper Events
    tamper_specs = [
        (1, 1, 'JAMMER_DETECTED', 'CRITICAL', 27.8520, 76.4530, 'C/No dropped below 15 dB-Hz while auxiliary power nominal', 14),
        (2, 3, 'TAMPER_DETECTED', 'HIGH', 27.6100, 76.5800, 'Main power wire severed, unit switched to internal backup', 0),
        (3, 8, 'PROHIBITED_ZONE', 'CRITICAL', 27.6300, 76.5200, 'Geofence breach: Sariska Ecological Buffer Escarpment', 35),
        (4, 10, 'JAMMER_DETECTED', 'CRITICAL', 27.6500, 76.5400, 'Continuous carrier wave jammer detected at 1575.42 MHz', 22),
        (5, 14, 'JAMMER_DETECTED', 'HIGH', 27.7200, 76.2200, 'L1 frequency jammer active near Kotputli toll barrier', 18),
        (6, 21, 'TAMPER_DETECTED', 'HIGH', 28.1880, 76.6210, 'Chassis ground wire cut adjacent to Khol riverbed', 0),
    ]
    for te in tamper_specs:
        c.execute("""
            INSERT INTO gps_tamper_events (
                id, truck_id, event_type, severity, latitude, longitude, evidence_notes, duration_seconds, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ? * 60, datetime('now', '-45 minutes'))
        """, te)

    conn.commit()
    conn.close()
    print("Filter demonstration dummy data seeded successfully!")

if __name__ == '__main__':
    seed_filter_test_data()
