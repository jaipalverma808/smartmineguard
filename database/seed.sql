-- ============================================================
-- SmartMineGuard - PostgreSQL + PostGIS Seed Data
-- Realistic Synthetic Indian Mining Dataset
-- ============================================================

-- 1. USERS
INSERT INTO users (id, username, password_hash, full_name, role, department, badge_number, email, phone) VALUES
(1, 'admin', 'scrypt:32768:8:1$Zr30Mc23gHWgwT8A$270528ddd472694daf5a7f3cdd6592e8b731511c38b482f439ac766beb660bd2d61bd76b7a9c2e378b8a55f3ae75a2803934f7e66ffe05398acb4daf895cba54', 'Sanjay Verma, IAS', 'ADMIN', 'Directorate of Mines & Geology', 'DMG-HQ-01', 'sanjay.verma@mines.gov.in', '+91 98100 11223'),
(2, 'officer1', 'scrypt:32768:8:1$FK4stxukDtMqpkeV$860bedbad7459012931eed20b028629d2dc3d57a57e9479251ade9c2687169258ff8521cf85aa74963383905c5e866474c72e45f11cc3d7bedd21b8fe8e747de', 'Inspector Rajesh K. Meena', 'OFFICER', 'Mining Enforcement Squad Zone 4', 'MES-Z4-409', 'rajesh.meena@enforcement.gov.in', '+91 94140 22334'),
(3, 'operator1', 'scrypt:32768:8:1$LPCNLxkf3VowPuNr$81c09abbf1e26043183f4f42f34efe09be08859d32288a45c80a237df3ef3d2494b0dc646dcf5f1f743b86cc51153edb72a218cdf4a64e0d67b8e467850f3f90', 'Virendra Singh Rathore', 'OPERATOR', 'Aravalli Quartzite Consortium', 'OP-RJ-08', 'virendra@aravalliminerals.com', '+91 99280 33445')
ON CONFLICT (id) DO NOTHING;

-- 2. MINES / LEASES
INSERT INTO mines (id, mine_code, name, mineral, district, state, latitude, longitude, authorized_annual_quota_mt, current_dispatch_mt, status, operator_name, contact_phone) VALUES
(1, 'MN-RJ-ALW-01', 'Aravalli Quartzite Quarry Block A', 'Quartzite', 'Alwar', 'Rajasthan', 27.5624, 76.6121, 45000.0, 31250.0, 'OPERATIONAL', 'Aravalli Quartzite Consortium', '+91 99280 33445'),
(2, 'MN-RJ-KOT-04', 'Kotputli High-Grade Limestone Lease', 'Limestone', 'Kotputli-Behror', 'Rajasthan', 27.7052, 76.2023, 85000.0, 58400.0, 'OPERATIONAL', 'Shree Cement Raw Materials Div.', '+91 94142 88776'),
(3, 'MN-HR-REW-02', 'Khol Silica Sand & Stone Pit', 'Silica Sand', 'Rewari', 'Haryana', 28.1884, 76.6210, 30000.0, 28900.0, 'OPERATIONAL', 'Khol Mining Cooperative', '+91 98122 44332'),
(4, 'MN-RJ-JHJ-09', 'Khetri Copper Tailings & Rock Zone', 'Copper Tailings / Quartz', 'Jhunjhunu', 'Rajasthan', 28.0125, 75.7891, 60000.0, 64200.0, 'QUOTA_EXCEEDED', 'Hindustan Quarrying Partners', '+91 97841 55667')
ON CONFLICT (id) DO NOTHING;

-- 3. TRUCKS (Target of demo + normal fleet)
INSERT INTO trucks (id, registration_number, vehicle_type, registered_owner, driver_name, driver_phone, tare_weight_mt, max_capacity_mt, rfid_tag, gps_imei, status, current_lat, current_lng, last_gps_time, current_risk_score, current_risk_level) VALUES
(1, 'HR26AB1234', '10-Wheeler Tipper Truck', 'Shri Ram Logistics Pvt Ltd', 'Vikram Singh', '+91 98123 45678', 11.5, 28.0, 'RFID-HR26-001', '864201045678901', 'IN_TRANSIT', 27.8520, 76.4530, CURRENT_TIMESTAMP, 92, 'CRITICAL'),
(2, 'RJ14GA5521', '12-Wheeler Dump Truck', 'Aravalli Freightways', 'Ramesh Gurjar', '+91 94141 89765', 12.8, 32.0, 'RFID-RJ14-002', '864201045678902', 'IN_TRANSIT', 27.6800, 76.3500, CURRENT_TIMESTAMP, 15, 'LOW'),
(3, 'OD02BA8812', '10-Wheeler Tipper Truck', 'Kalinga Mineral Carrier', 'Sunil Yadav', '+91 99370 12345', 11.2, 28.0, 'RFID-OD02-003', '864201045678903', 'IN_TRANSIT', 27.6100, 76.5800, CURRENT_TIMESTAMP, 75, 'HIGH'),
(4, 'HR38EF9012', '14-Wheeler Multi-Axle', 'Highway Haulers Corp', 'Balwinder Singh', '+91 98188 67890', 14.0, 40.0, 'RFID-HR38-004', '864201045678904', 'IN_TRANSIT', 27.9500, 76.5100, CURRENT_TIMESTAMP, 65, 'HIGH'),
(5, 'RJ32CD3344', '10-Wheeler Tipper Truck', 'Meena Stone Transporters', 'Manoj Meena', '+91 97820 44556', 11.0, 26.0, 'RFID-RJ32-005', '864201045678905', 'LOADING', 27.5630, 76.6110, CURRENT_TIMESTAMP, 10, 'LOW'),
(6, 'DL1LA9022', '10-Wheeler Tipper Truck', 'Capital Bulk Carriers', 'Dharmendra Sharma', '+91 98111 22334', 11.6, 28.0, 'RFID-DL1L-006', '864201045678906', 'IDLE', 28.1850, 76.6200, CURRENT_TIMESTAMP, 5, 'LOW'),
(7, 'UP16BT4055', '12-Wheeler Dump Truck', 'Noida Aggregate Movers', 'Satish Kumar', '+91 98710 55443', 13.0, 34.0, 'RFID-UP16-007', '864201045678907', 'IN_TRANSIT', 27.7900, 76.4100, CURRENT_TIMESTAMP, 25, 'LOW'),
(8, 'RJ02CB7811', '10-Wheeler Tipper Truck', 'Mewat Minerals Transport', 'Imran Khan', '+91 99291 77665', 11.4, 28.0, 'RFID-RJ02-008', '864201045678908', 'IN_TRANSIT', 27.6300, 76.5200, CURRENT_TIMESTAMP, 45, 'MEDIUM')
ON CONFLICT (id) DO NOTHING;

-- 4. e-RAWAANA PERMITS
INSERT INTO permits (id, permit_number, qr_code_hash, truck_id, mine_id, mineral, permitted_weight_mt, source_name, destination_name, destination_lat, destination_lng, buyer_name, issued_at, expires_at, status, route_waypoints_json) VALUES
(1, 'SMG-2026-00125', 'e9b28a71c3f412d08a5c1029384756ab1234567890abcdef1234567890abcdef', 1, 1, 'Quartzite Aggregate', 20.0, 'Aravalli Quarry Block A (Alwar)', 'Bhiwadi Industrial Crushing Zone', 28.2100, 76.8600, 'Bhiwadi Aggregates & ReadyMix Ltd', CURRENT_TIMESTAMP - INTERVAL '3 hours', CURRENT_TIMESTAMP + INTERVAL '9 hours', 'ACTIVE', '[[27.5624, 76.6121], [27.7200, 76.5100], [27.9800, 76.6800], [28.2100, 76.8600]]'),
(2, 'TRP-2026-00124', 'f1c43a82b9e715d29b6d2130495867bc2345678901bcdef012345678901bcdef', 2, 2, 'Limestone Raw Boulder', 25.0, 'Kotputli Limestone Lease', 'Neemrana Cement Works Unit-2', 27.9850, 76.3850, 'Neemrana Cement & Clinker Ltd', CURRENT_TIMESTAMP - INTERVAL '2 hours', CURRENT_TIMESTAMP + INTERVAL '6 hours', 'ACTIVE', '[[27.7052, 76.2023], [27.8400, 76.2900], [27.9850, 76.3850]]'),
(3, 'TRP-2026-00088', 'a3d54b93c8f826e30c7e3241506978cd3456789012cdef0123456789012cdef', 3, 1, 'Quartzite Sand', 22.0, 'Aravalli Quarry Block A (Alwar)', 'Manesar Infrastructure Hub', 28.3500, 76.9400, 'DLF Urban Infra Projects', CURRENT_TIMESTAMP - INTERVAL '12 hours', CURRENT_TIMESTAMP - INTERVAL '2 hours', 'CONSUMED', '[[27.5624, 76.6121], [27.8900, 76.7200], [28.3500, 76.9400]]'),
(4, 'TRP-2026-00130', 'b4e65c04d9a937f41d8f4352617089de4567890123def01234567890123def', 4, 3, 'Silica Sand Grade-I', 30.0, 'Khol Silica Sand Pit (Rewari)', 'Jaipur Glass Containers Ltd', 26.9124, 75.7873, 'Jaipur Glassware Industries', CURRENT_TIMESTAMP - INTERVAL '1 hour', CURRENT_TIMESTAMP + INTERVAL '11 hours', 'ACTIVE', '[[28.1884, 76.6210], [27.8000, 76.3000], [27.2000, 75.9000], [26.9124, 75.7873]]')
ON CONFLICT (id) DO NOTHING;

-- 5. TRIPS
INSERT INTO trips (id, trip_number, permit_id, truck_id, mine_id, status, start_time, end_time, planned_distance_km, actual_distance_km, max_recorded_speed_kmh, avg_speed_kmh, risk_score, risk_level) VALUES
(1, 'TRIP-2026-00501', 1, 1, 1, 'IN_TRANSIT', CURRENT_TIMESTAMP - INTERVAL '2 hours', NULL, 78.0, 48.5, 68.0, 42.0, 92, 'CRITICAL'),
(2, 'TRIP-2026-00502', 2, 2, 2, 'IN_TRANSIT', CURRENT_TIMESTAMP - INTERVAL '1 hour', NULL, 42.0, 22.0, 52.0, 38.0, 15, 'LOW'),
(3, 'TRIP-2026-00503', 3, 3, 1, 'SUSPICIOUS', CURRENT_TIMESTAMP - INTERVAL '40 minutes', NULL, 95.0, 18.0, 60.0, 35.0, 75, 'HIGH'),
(4, 'TRIP-2026-00504', 4, 4, 3, 'IN_TRANSIT', CURRENT_TIMESTAMP - INTERVAL '30 minutes', NULL, 155.0, 32.0, 96.0, 88.0, 65, 'HIGH')
ON CONFLICT (id) DO NOTHING;

-- 6. WEIGHMENTS
INSERT INTO weighments (id, trip_id, permit_id, truck_id, weighbridge_code, weighbridge_name, gross_weight_mt, tare_weight_mt, net_weight_mt, permitted_weight_mt, difference_mt, is_overweight, timestamp) VALUES
(1, 1, 1, 1, 'WB-ALW-01', 'Alwar Mining Exit Weighbridge #1', 42.5, 11.5, 31.0, 20.0, 11.0, TRUE, CURRENT_TIMESTAMP - INTERVAL '1 hour 45 minutes'),
(2, 2, 2, 2, 'WB-KOT-02', 'Kotputli Lease Perimeter Weighbridge', 36.5, 12.8, 23.7, 25.0, -1.3, FALSE, CURRENT_TIMESTAMP - INTERVAL '50 minutes'),
(3, 4, 4, 4, 'WB-REW-01', 'Rewari Industrial Toll Weighbridge', 43.8, 14.0, 29.8, 30.0, -0.2, FALSE, CURRENT_TIMESTAMP - INTERVAL '25 minutes')
ON CONFLICT (id) DO NOTHING;

-- 7. GEOFENCES & SENSITIVE ZONES
INSERT INTO geofences (id, name, zone_type, polygon_coordinates_json, severity) VALUES
(1, 'Sabi Riverbed Restricted Mining Zone', 'RESTRICTED_RIVERBED', '[[27.8000, 76.3800], [27.8600, 76.3900], [27.8500, 76.4600], [27.7900, 76.4400]]', 'CRITICAL'),
(2, 'NH-48 Legal Mineral Transport Corridor', 'CORRIDOR', '[[27.5500, 76.6000], [27.7500, 76.4500], [28.0000, 76.6500], [28.2500, 76.8500]]', 'HIGH'),
(3, 'Sariska Tiger Reserve Northern Buffer', 'ECOLOGICAL_BUFFER', '[[27.4000, 76.5000], [27.5200, 76.5200], [27.5000, 76.6200], [27.3800, 76.5800]]', 'CRITICAL')
ON CONFLICT (id) DO NOTHING;

-- 8. ALERTS (Pre-seeded real-time alerts)
INSERT INTO alerts (id, alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id) VALUES
(1, 'ALT-2026-00101', 1, 1, 1, 'WEIGHT_ANOMALY', 'CRITICAL', 30, 'Weighbridge Net Weight 31.0 MT exceeds e-Rawaana permitted limit 20.0 MT (+11.0 MT / +55.0% overload).', '{"permitted_mt": 20.0, "actual_mt": 31.0, "difference_mt": 11.0, "weighbridge": "WB-ALW-01", "tolerance_exceeded": true}', 'NEW', 2),
(2, 'ALT-2026-00102', 1, 1, 1, 'ROUTE_DEVIATION', 'HIGH', 20, 'Vehicle deviated 1,420m outside permitted NH-48 mineral transit corridor toward unmonitored rural link.', '{"deviation_m": 1420, "allowed_corridor_m": 350, "last_lat": 27.8520, "last_lng": 76.4530, "corridor": "NH-48"}', 'NEW', 2),
(3, 'ALT-2026-00103', 1, 1, 1, 'GPS_BLACKOUT', 'HIGH', 20, 'GPS heartbeat lost for 14 minutes immediately adjacent to Sabi Riverbed Restricted Mining Zone.', '{"blackout_duration_min": 14, "proximity_zone": "Sabi Riverbed Restricted Mining Zone", "last_ping_lat": 27.8520, "last_ping_lng": 76.4530}', 'NEW', 2),
(4, 'ALT-2026-00104', 3, 3, 3, 'PERMIT_REUSE', 'CRITICAL', 30, 'e-Rawaana TRP-2026-00088 is being presented by Truck OD02BA8812 after already being marked CONSUMED 10 hours ago.', '{"permit_number": "TRP-2026-00088", "original_status": "CONSUMED", "scanned_truck": "OD02BA8812"}', 'NEW', 2),
(5, 'ALT-2026-00105', 4, 4, 4, 'IMPOSSIBLE_TRANSIT', 'HIGH', 30, 'Transit telemetry indicates average speed of 88.0 km/h with 96.0 km/h bursts on mountainous terrain (Maximum legal tipper speed: 85 km/h).', '{"avg_speed_kmh": 88.0, "max_speed_kmh": 96.0, "legal_limit_kmh": 85.0}', 'ACKNOWLEDGED', 2),
(6, 'ALT-2026-00106', NULL, NULL, NULL, 'PRODUCTION_MISMATCH', 'HIGH', 30, 'Mine MN-RJ-JHJ-09 (Khetri Zone) has dispatched 64,200 MT exceeding its authorized annual mining quota of 60,000 MT (+4,200 MT unpermitted extraction).', '{"mine_code": "MN-RJ-JHJ-09", "authorized_quota_mt": 60000.0, "current_dispatch_mt": 64200.0, "excess_mt": 4200.0}', 'NEW', 1)
ON CONFLICT (id) DO NOTHING;

-- 9. INVESTIGATIONS
INSERT INTO investigations (id, case_id, alert_id, trip_id, truck_id, permit_id, lead_officer_id, title, status, initial_findings, officer_notes, final_decision, penalty_amount_inr, pdf_report_path) VALUES
(1, 'SMG-2026-00041', 1, 1, 1, 1, 2, 'Enforcement Case: Overweight Dispatch & Route Deviation - Truck HR26AB1234', 'UNDER_INVESTIGATION', 'Vehicle HR26AB1234 dispatched from Aravalli Quarry Block A with +11 MT excess Quartzite. Vehicle subsequently diverted 1.4km from legal corridor into rural link road toward Sabi riverbed with intermittent GPS loss.', 'Enforcement squad intercepted vehicle at Kotputli bypass junction. Physical weighment verified 31.2 MT net load. Driver failed to present valid extension permit. Notice served under Section 21 of MMDR Act.', 'Vehicle impounded at Behror police yard pending compounding fee and environmental damage assessment.', 175000.0, 'static/reports/dossier_SMG-2026-00041.pdf')
ON CONFLICT (id) DO NOTHING;

-- 10. DRIVERS
INSERT INTO drivers (id, driver_name, license_number, contact_phone, assigned_truck_id, status) VALUES
(1, 'Vikram Singh', 'DL-0420180091234', '+91 98123 45678', 1, 'ACTIVE'),
(2, 'Ramesh Gurjar', 'RJ-1420190082341', '+91 94141 89765', 2, 'ACTIVE'),
(3, 'Sunil Yadav', 'OD-0220200073412', '+91 99370 12345', 3, 'ACTIVE'),
(4, 'Balwinder Singh', 'HR-3820170064523', '+91 98188 67890', 4, 'ACTIVE'),
(5, 'Manoj Meena', 'RJ-3220210055634', '+91 97820 44556', 5, 'ACTIVE'),
(6, 'Dharmendra Sharma', 'DL-1L20160046745', '+91 98111 22334', 6, 'ACTIVE'),
(7, 'Satish Kumar', 'UP-1620220037856', '+91 98710 55443', 7, 'ACTIVE'),
(8, 'Imran Khan', 'RJ-0220190028967', '+91 99291 77665', 8, 'ACTIVE')
ON CONFLICT (id) DO NOTHING;

-- 11. WEIGHBRIDGES
INSERT INTO weighbridges (id, code, name, location, mine_id, operator_name, capacity_mt, status, latitude, longitude) VALUES
(1, 'WB-ALW-01', 'Alwar Mining Exit Weighbridge #1', 'Alwar Bypass, NH-248A', 1, 'Aravalli Quartzite Consortium', 100.0, 'OPERATIONAL', 27.5680, 76.6180),
(2, 'WB-KOT-02', 'Kotputli Lease Perimeter Weighbridge', 'Kotputli-Neemrana Link, NH-48', 2, 'Shree Cement Raw Materials Div.', 120.0, 'OPERATIONAL', 27.7120, 76.2100),
(3, 'WB-REW-01', 'Rewari Industrial Toll Weighbridge', 'Rewari Industrial Estate, Bawal Road', 3, 'Khol Mining Cooperative', 100.0, 'OPERATIONAL', 28.1820, 76.6150),
(4, 'WB-JHJ-03', 'Khetri Gate Electronic Weighbridge', 'Singhana-Khetri Road, Jhunjhunu', 4, 'Hindustan Quarrying Partners', 100.0, 'OPERATIONAL', 28.0200, 75.7950)
ON CONFLICT (id) DO NOTHING;

-- 12. DESTINATIONS
INSERT INTO destinations (id, name, destination_type, license_number, district, state, latitude, longitude, authorized_minerals, status) VALUES
(1, 'Bhiwadi Industrial Crushing Zone', 'CRUSHER', 'CR-RJ-BHW-088', 'Alwar', 'Rajasthan', 28.2100, 76.8600, 'Quartzite Aggregate', 'AUTHORIZED'),
(2, 'Neemrana Cement Works Unit-2', 'CEMENT_PLANT', 'CP-RJ-NEE-014', 'Kotputli-Behror', 'Rajasthan', 27.9850, 76.3850, 'Limestone Raw Boulder', 'AUTHORIZED'),
(3, 'Manesar Infrastructure Hub', 'CONSTRUCTION_SITE', 'INF-HR-GGM-102', 'Gurugram', 'Haryana', 28.3500, 76.9400, 'Quartzite Sand', 'AUTHORIZED'),
(4, 'Jaipur Glass Containers Ltd', 'PROCESSING_PLANT', 'GL-RJ-JPR-045', 'Jaipur', 'Rajasthan', 26.9124, 75.7873, 'Silica Sand Grade-I', 'AUTHORIZED')
ON CONFLICT (id) DO NOTHING;

-- 13. CHECKPOINTS
INSERT INTO checkpoints (id, name, district, state, latitude, longitude, authorized_route, status) VALUES
(1, 'Alwar Mining Border Checkpost', 'Alwar', 'Rajasthan', 27.6800, 76.5600, 'NH-248A / Alwar-Bhiwadi Route', 'ACTIVE'),
(2, 'Behror Inter-State Flying Squad Post', 'Kotputli-Behror', 'Rajasthan', 27.8900, 76.2800, 'NH-48 Jaipur-Delhi Highway', 'ACTIVE'),
(3, 'Bawal Toll Monitoring Checkpoint', 'Rewari', 'Haryana', 28.0800, 76.5900, 'NH-48 Mineral Transit Corridor', 'ACTIVE'),
(4, 'Dharuhera Intercept Station', 'Rewari', 'Haryana', 28.2050, 76.7900, 'NH-48 Rewari-Bhiwadi Junction', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;

-- 14. STOCK & PRODUCTION RECONCILIATION
INSERT INTO stock_production (id, mine_id, mineral, record_date, opening_stock_mt, production_mt, dispatch_mt, closing_stock_mt, notes) VALUES
(1, 1, 'Quartzite', CURRENT_DATE, 4200.0, 650.0, 480.0, 4370.0, 'Morning shift quarry blast output logged.'),
(2, 2, 'Limestone', CURRENT_DATE, 7800.0, 1100.0, 850.0, 8050.0, 'High-grade limestone benching extraction.'),
(3, 3, 'Silica Sand', CURRENT_DATE, 2900.0, 450.0, 380.0, 2970.0, 'Screened silica sand production lot.'),
(4, 4, 'Copper Tailings / Quartz', CURRENT_DATE, 5400.0, 800.0, 720.0, 5480.0, 'Crushed overburden dispatch.')
ON CONFLICT (id) DO NOTHING;

