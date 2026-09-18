-- ============================================================
-- SmartMineGuard - PostgreSQL + PostGIS Schema
-- ============================================================

-- Enable PostGIS extension if available
CREATE EXTENSION IF NOT EXISTS postgis;

-- 1. USERS & ROLES
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('ADMIN', 'OFFICER', 'OPERATOR')),
    department VARCHAR(100) DEFAULT 'Department of Mines & Geology',
    badge_number VARCHAR(50),
    email VARCHAR(100),
    phone VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. MINES & LEASE BLOCKS
CREATE TABLE IF NOT EXISTS mines (
    id SERIAL PRIMARY KEY,
    mine_code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    mineral VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom geometry(Point, 4326),
    authorized_annual_quota_mt DOUBLE PRECISION NOT NULL DEFAULT 50000.0,
    current_dispatch_mt DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    status VARCHAR(30) DEFAULT 'OPERATIONAL',
    operator_name VARCHAR(150) NOT NULL,
    contact_phone VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. TRUCKS / TRANSPORT VEHICLES
CREATE TABLE IF NOT EXISTS trucks (
    id SERIAL PRIMARY KEY,
    registration_number VARCHAR(20) UNIQUE NOT NULL,
    vehicle_type VARCHAR(50) DEFAULT '10-Wheeler Tipper Truck',
    registered_owner VARCHAR(150) NOT NULL,
    driver_name VARCHAR(100) NOT NULL,
    driver_phone VARCHAR(20),
    tare_weight_mt DOUBLE PRECISION NOT NULL DEFAULT 11.5,
    max_capacity_mt DOUBLE PRECISION NOT NULL DEFAULT 28.0,
    rfid_tag VARCHAR(50) UNIQUE,
    gps_imei VARCHAR(50) UNIQUE,
    status VARCHAR(30) DEFAULT 'IDLE' CHECK (status IN ('IDLE', 'LOADING', 'IN_TRANSIT', 'WEIGHED', 'MAINTENANCE', 'TRUCK_ARRIVED')),
    current_lat DOUBLE PRECISION,
    current_lng DOUBLE PRECISION,
    geom geometry(Point, 4326),
    last_gps_time TIMESTAMP,
    current_risk_score INT DEFAULT 0,
    current_risk_level VARCHAR(20) DEFAULT 'LOW' CHECK (current_risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    assigned_mine_id INT REFERENCES mines(id),
    allowed_rounds_per_day INT DEFAULT 4,
    completed_rounds_today INT DEFAULT 0,
    current_round_number INT DEFAULT 1,
    is_inside_mine BOOLEAN DEFAULT FALSE,
    current_mine_id INT REFERENCES mines(id),
    last_mine_entry TIMESTAMP,
    last_mine_exit TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. e-RAWAANA PERMITS
CREATE TABLE IF NOT EXISTS permits (
    id SERIAL PRIMARY KEY,
    permit_number VARCHAR(50) UNIQUE NOT NULL,
    qr_code_hash VARCHAR(64) UNIQUE NOT NULL,
    truck_id INT REFERENCES trucks(id) ON DELETE SET NULL,
    mine_id INT REFERENCES mines(id) ON DELETE CASCADE,
    mineral VARCHAR(100) NOT NULL,
    permitted_weight_mt DOUBLE PRECISION NOT NULL,
    source_name VARCHAR(150) NOT NULL,
    destination_name VARCHAR(150) NOT NULL,
    destination_lat DOUBLE PRECISION NOT NULL,
    destination_lng DOUBLE PRECISION NOT NULL,
    dest_geom geometry(Point, 4326),
    buyer_name VARCHAR(150) NOT NULL,
    issued_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status VARCHAR(40) DEFAULT 'ACTIVE' CHECK (status IN ('ISSUED', 'ACTIVE', 'TRUCK_ARRIVED', 'LOADING', 'WEIGHED', 'DISPATCHED', 'COMPLETED', 'CONSUMED', 'EXPIRED', 'CANCELLED', 'SUSPICIOUS', 'RECONCILIATION_REQUIRED')),
    reconciliation_reason TEXT,
    route_waypoints_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. TRANSIT TRIPS
CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    trip_number VARCHAR(50) UNIQUE NOT NULL,
    permit_id INT REFERENCES permits(id) ON DELETE CASCADE,
    truck_id INT REFERENCES trucks(id) ON DELETE CASCADE,
    mine_id INT REFERENCES mines(id) ON DELETE CASCADE,
    round_number INT DEFAULT 1,
    status VARCHAR(30) DEFAULT 'DISPATCHED' CHECK (status IN ('DISPATCHED', 'IN_TRANSIT', 'LOADING', 'WEIGHED', 'DELIVERED', 'COMPLETED', 'SUSPICIOUS', 'CANCELLED', 'TRUCK_ARRIVED')),
    start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    planned_distance_km DOUBLE PRECISION NOT NULL DEFAULT 45.0,
    actual_distance_km DOUBLE PRECISION DEFAULT 0.0,
    max_recorded_speed_kmh DOUBLE PRECISION DEFAULT 0.0,
    avg_speed_kmh DOUBLE PRECISION DEFAULT 0.0,
    timeline_events_json TEXT DEFAULT '[]',
    risk_score INT DEFAULT 0,
    risk_level VARCHAR(20) DEFAULT 'LOW' CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. WEIGHBRIDGE RECORDS
CREATE TABLE IF NOT EXISTS weighments (
    id SERIAL PRIMARY KEY,
    trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
    permit_id INT REFERENCES permits(id) ON DELETE CASCADE,
    truck_id INT REFERENCES trucks(id) ON DELETE CASCADE,
    weighbridge_code VARCHAR(50) NOT NULL,
    weighbridge_name VARCHAR(150) NOT NULL,
    gross_weight_mt DOUBLE PRECISION NOT NULL,
    tare_weight_mt DOUBLE PRECISION NOT NULL,
    net_weight_mt DOUBLE PRECISION NOT NULL,
    permitted_weight_mt DOUBLE PRECISION NOT NULL,
    difference_mt DOUBLE PRECISION NOT NULL,
    is_overweight BOOLEAN DEFAULT FALSE,
    measurement_source VARCHAR(50) DEFAULT 'AUTOMATED_WEIGHBRIDGE_SCALE',
    measurement_status VARCHAR(30) DEFAULT 'VERIFIED',
    is_manual_override BOOLEAN DEFAULT FALSE,
    original_net_weight_mt DOUBLE PRECISION,
    override_reason TEXT,
    override_by_user_id INT REFERENCES users(id),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. GPS POSITIONS & TRACKING
CREATE TABLE IF NOT EXISTS gps_positions (
    id SERIAL PRIMARY KEY,
    trip_id INT REFERENCES trips(id) ON DELETE CASCADE,
    truck_id INT REFERENCES trucks(id) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom geometry(Point, 4326),
    speed_kmh DOUBLE PRECISION DEFAULT 0.0,
    heading DOUBLE PRECISION DEFAULT 0.0,
    deviation_distance_m DOUBLE PRECISION DEFAULT 0.0,
    is_deviated BOOLEAN DEFAULT FALSE,
    in_suspicious_zone BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. GEOFENCES & SENSITIVE ZONES
CREATE TABLE IF NOT EXISTS geofences (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    zone_type VARCHAR(50) NOT NULL CHECK (zone_type IN ('MINE_BOUNDARY', 'CORRIDOR', 'CHECKPOINT', 'RESTRICTED_RIVERBED', 'ECOLOGICAL_BUFFER')),
    polygon_coordinates_json TEXT NOT NULL,
    geom geometry(Polygon, 4326),
    severity VARCHAR(20) DEFAULT 'HIGH'
);

-- 9. ALERTS & DETECTIONS
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_code VARCHAR(50) UNIQUE NOT NULL,
    trip_id INT REFERENCES trips(id) ON DELETE SET NULL,
    truck_id INT REFERENCES trucks(id) ON DELETE SET NULL,
    permit_id INT REFERENCES permits(id) ON DELETE SET NULL,
    alert_type VARCHAR(50) NOT NULL CHECK (alert_type IN (
        'WEIGHT_ANOMALY', 
        'ROUTE_DEVIATION', 
        'GPS_BLACKOUT', 
        'PERMIT_REUSE', 
        'IMPOSSIBLE_TRANSIT', 
        'PRODUCTION_MISMATCH', 
        'PASS_RECYCLING',
        'UNAUTHORIZED_MINE_ENTRY',
        'PERMIT_MISMATCH',
        'EXCESSIVE_TRIP_FREQUENCY'
    )),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    risk_score INT NOT NULL,
    description TEXT NOT NULL,
    evidence_json TEXT,
    status VARCHAR(30) DEFAULT 'NEW' CHECK (status IN ('NEW', 'ACKNOWLEDGED', 'UNDER_REVIEW', 'RESOLVED', 'DISMISSED')),
    assigned_to_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    handled_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    action_taken VARCHAR(50),
    officer_remarks TEXT,
    escalated_to_admin INT DEFAULT 0,
    admin_review_status VARCHAR(50) DEFAULT 'NONE',
    admin_notes TEXT,
    admin_reviewed_at TIMESTAMP,
    admin_reviewed_by INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. INVESTIGATIONS & CASE FILES
CREATE TABLE IF NOT EXISTS investigations (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(50) UNIQUE NOT NULL,
    alert_id INT REFERENCES alerts(id) ON DELETE SET NULL,
    trip_id INT REFERENCES trips(id) ON DELETE SET NULL,
    truck_id INT REFERENCES trucks(id) ON DELETE SET NULL,
    permit_id INT REFERENCES permits(id) ON DELETE SET NULL,
    lead_officer_id INT REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(30) DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'UNDER_INVESTIGATION', 'ACTION_REQUIRED', 'CLOSED')),
    initial_findings TEXT NOT NULL,
    officer_notes TEXT,
    final_decision TEXT,
    penalty_amount_inr DOUBLE PRECISION DEFAULT 0.0,
    pdf_report_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. OFFICER FIELD VERIFICATIONS
CREATE TABLE IF NOT EXISTS verifications (
    id SERIAL PRIMARY KEY,
    permit_id INT REFERENCES permits(id) ON DELETE CASCADE,
    officer_id INT REFERENCES users(id) ON DELETE SET NULL,
    checkpoint_name VARCHAR(150) NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    verification_result VARCHAR(30) NOT NULL CHECK (verification_result IN ('VALID', 'SUSPICIOUS', 'REJECTED')),
    scanned_via VARCHAR(30) DEFAULT 'QR_SCAN',
    discrepancy_notes TEXT,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. DRIVERS REGISTRY
CREATE TABLE IF NOT EXISTS drivers (
    id SERIAL PRIMARY KEY,
    driver_name VARCHAR(100) NOT NULL,
    license_number VARCHAR(50) UNIQUE NOT NULL,
    contact_phone VARCHAR(25),
    assigned_truck_id INT REFERENCES trucks(id) ON DELETE SET NULL,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    allowed_rounds_per_day INT DEFAULT 4,
    completed_rounds_today INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. WEIGHBRIDGES INFRASTRUCTURE
CREATE TABLE IF NOT EXISTS weighbridges (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(150) NOT NULL,
    location VARCHAR(200) NOT NULL,
    mine_id INT REFERENCES mines(id) ON DELETE SET NULL,
    operator_name VARCHAR(150),
    capacity_mt DOUBLE PRECISION DEFAULT 100.0,
    status VARCHAR(30) DEFAULT 'OPERATIONAL',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 14. AUTHORIZED DESTINATIONS / CONSUMERS
CREATE TABLE IF NOT EXISTS destinations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    destination_type VARCHAR(50) DEFAULT 'CRUSHER',
    license_number VARCHAR(100),
    district VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    authorized_minerals VARCHAR(255),
    status VARCHAR(30) DEFAULT 'AUTHORIZED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. TRANSIT CORRIDOR CHECKPOINTS
CREATE TABLE IF NOT EXISTS checkpoints (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    district VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    authorized_route VARCHAR(200),
    status VARCHAR(30) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 16. STOCK & PRODUCTION RECONCILIATION
CREATE TABLE IF NOT EXISTS stock_production (
    id SERIAL PRIMARY KEY,
    mine_id INT REFERENCES mines(id) ON DELETE CASCADE,
    mineral VARCHAR(100) NOT NULL,
    record_date DATE DEFAULT CURRENT_DATE,
    opening_stock_mt DOUBLE PRECISION NOT NULL,
    production_mt DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    dispatch_mt DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    closing_stock_mt DOUBLE PRECISION NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SPATIAL & PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS idx_mines_geom ON mines USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_trucks_geom ON trucks USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_gps_positions_geom ON gps_positions USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_permits_number ON permits(permit_number);
CREATE INDEX IF NOT EXISTS idx_permits_qr ON permits(qr_code_hash);
CREATE INDEX IF NOT EXISTS idx_trucks_reg ON trucks(registration_number);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_investigations_case ON investigations(case_id);

