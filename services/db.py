"""
SmartMineGuard - Database Abstraction Layer
Supports PostgreSQL / PostGIS with seamless SQLite spatial-emulated fallback.
"""
import sqlite3
import math
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from config import Config

logger = logging.getLogger("smartmineguard.db")

# Optional psycopg2 import
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool as pg_pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


def haversine_distance_km(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in km."""
    R = 6371.0  # Earth radius in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def point_to_segment_distance_m(p_lat, p_lon, a_lat, a_lon, b_lat, b_lon):
    """
    Calculate perpendicular distance in meters from point P to line segment AB.
    """
    # Convert lat/lon degrees approximately to meters (at ~28 deg latitude)
    meters_per_lat = 111132.0
    meters_per_lon = 111132.0 * math.cos(math.radians(p_lat))
    
    px = p_lon * meters_per_lon
    py = p_lat * meters_per_lat
    ax = a_lon * meters_per_lon
    ay = a_lat * meters_per_lat
    bx = b_lon * meters_per_lon
    by = b_lat * meters_per_lat
    
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq == 0:
        return math.hypot(px - ax, py - ay)
    
    # Project point P onto segment AB
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


class DatabaseManager:
    def __init__(self):
        self.use_postgres = False
        self._pg_pool = None  # Connection pool for PostgreSQL
        self._test_postgres()

    def _test_postgres(self):
        if not PSYCOPG2_AVAILABLE:
            self.use_postgres = False
            return
        # In serverless environments, only test Postgres if explicit DATABASE_URL env var is provided
        import os
        if Config.IS_SERVERLESS and "DATABASE_URL" not in os.environ:
            self.use_postgres = False
            return
        try:
            # Create a persistent connection pool (min=2, max=10 connections)
            # This avoids expensive TCP handshakes on every request
            self._pg_pool = pg_pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=Config.DATABASE_URL,
                connect_timeout=5
            )
            self.use_postgres = True
            logger.info("Connected successfully to PostgreSQL / PostGIS (connection pool ready).")
        except Exception as e:
            self._pg_pool = None
            self.use_postgres = False
            logger.info(f"PostgreSQL not active. Operating in SQLite mode. ({e})")

    def get_connection(self):
        """Get a connection from the pool (PostgreSQL) or create a SQLite connection."""
        if self.use_postgres:
            if self._pg_pool is None:
                # Fallback: create a direct connection if pool is somehow unavailable
                return psycopg2.connect(Config.DATABASE_URL)
            return self._pg_pool.getconn()
        else:
            try:
                Config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            conn = sqlite3.connect(str(Config.SQLITE_PATH))
            conn.row_factory = sqlite3.Row
            try:
                has_users = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
            except Exception:
                has_users = 0
            if not has_users:
                conn.close()
                self.init_sqlite(force=True)
                conn = sqlite3.connect(str(Config.SQLITE_PATH))
                conn.row_factory = sqlite3.Row
            return conn

    def _return_connection(self, conn):
        """Return a PostgreSQL connection back to the pool, or close SQLite connection."""
        if self.use_postgres and self._pg_pool is not None:
            try:
                self._pg_pool.putconn(conn)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            conn.close()


    def _format_pg_sql(self, sql):
        import re
        pg_sql = sql.replace("?", "%s")
        pg_sql = pg_sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
        pg_sql = pg_sql.replace("datetime('now', 'localtime')", "CURRENT_TIMESTAMP")
        pg_sql = re.sub(r'substr\(([\w\.]*timestamp),', r'substr(\1::text,', pg_sql)
        return pg_sql

    def _serialize_row(self, row_dict):
        from datetime import datetime, date
        for k, v in list(row_dict.items()):
            if isinstance(v, (datetime, date)):
                row_dict[k] = v.strftime("%Y-%m-%d %H:%M:%S")
        return row_dict

    def query(self, sql, params=None, one=False):
        """Execute a query and return rows as list of dicts."""
        params = params or ()
        conn = self.get_connection()
        try:
            if self.use_postgres:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    pg_sql = self._format_pg_sql(sql)
                    cur.execute(pg_sql, params)
                    rows = cur.fetchall()
                    data = [self._serialize_row(dict(r)) for r in rows]
                    return (data[0] if data else None) if one else data
            else:
                cur = conn.cursor()
                cur.execute(sql, params)
                rows = cur.fetchall()
                data = [dict(r) for r in rows]
                return (data[0] if data else None) if one else data
        finally:
            self._return_connection(conn)

    def execute(self, sql, params=None):
        """Execute insert/update/delete and commit. Returns lastrowid or affected rows."""
        params = params or ()
        conn = self.get_connection()
        try:
            if self.use_postgres:
                with conn.cursor() as cur:
                    pg_sql = self._format_pg_sql(sql)
                    cur.execute(pg_sql, params)
                    conn.commit()
                    try:
                        return cur.fetchone()[0]
                    except Exception:
                        return cur.rowcount
            else:
                cur = conn.cursor()
                cur.execute(sql, params)
                conn.commit()
                return cur.lastrowid
        except Exception:
            # On error, rollback and return connection in a clean state
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self._return_connection(conn)

    def log_audit(self, action, details_or_entity="", *args, **kwargs):
        """
        Inserts a structured platform audit event into audit_logs table.
        Supports both styles:
        db.log_audit(action, details, user_id=..., ...)
        db.log_audit(action, entity, record_id, prev_state, new_state, reason, ...)
        """
        try:
            user_id = kwargs.get("user_id")
            username = kwargs.get("username") or "SYSTEM"
            ip_address = kwargs.get("ip_address", "127.0.0.1")

            if len(args) >= 3:
                entity = str(details_or_entity)
                record_id = args[0]
                previous_state = str(args[1]) if args[1] is not None else None
                new_state = str(args[2]) if args[2] is not None else None
                reason = str(args[3]) if len(args) > 3 else kwargs.get("reason")
                details = f"Entity {entity} #{record_id} transitioned: {previous_state} -> {new_state}. Reason: {reason}"
            else:
                details = str(details_or_entity)
                entity = kwargs.get("entity")
                previous_state = kwargs.get("previous_state")
                new_state = kwargs.get("new_state")
                reason = kwargs.get("reason")

            self.execute("""
                INSERT INTO audit_logs (user_id, username, action, details, entity, previous_state, new_state, reason, ip_address, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (user_id, username, action, details, entity, previous_state, new_state, reason, ip_address))
        except Exception as e:
            logger.warning(f"Database audit log failed: {e}")


    def append_trip_timeline(self, trip_id, event_title, details="", status="COMPLIANT", timestamp=None):
        """Appends a chronological milestone to a trip's timeline_events_json array."""
        try:
            import json
            t_str = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trip = self.query("SELECT timeline_events_json FROM trips WHERE id = ?", (trip_id,), one=True)
            if not trip:
                return
            try:
                events = json.loads(trip["timeline_events_json"] or "[]")
            except Exception:
                events = []
            events.append({
                "timestamp": t_str,
                "title": event_title,
                "details": details,
                "status": status
            })
            self.execute("UPDATE trips SET timeline_events_json = ? WHERE id = ?", (json.dumps(events), trip_id))
        except Exception as e:
            logger.warning(f"Failed to append timeline event for trip {trip_id}: {e}")

    def init_db(self, force=False):
        """Initialize database schema and seed data."""
        if self.use_postgres:
            conn = self.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users'")
                    has_users_table = cur.fetchone()[0]
                    user_count = 0
                    if has_users_table:
                        cur.execute("SELECT count(*) FROM users")
                        user_count = cur.fetchone()[0]

                    if force or user_count == 0:
                        schema_file = Config.BASE_DIR / "database" / "schema.sql"
                        seed_file = Config.BASE_DIR / "database" / "seed.sql"
                        cur.execute(schema_file.read_text(encoding="utf-8"))
                        cur.execute(seed_file.read_text(encoding="utf-8"))
                        conn.commit()
                        logger.info("PostgreSQL database initialized and seeded.")
                    else:
                        logger.info("PostgreSQL database verified and ready.")
            except Exception as e:
                logger.error(f"PostgreSQL initialization check failed: {e}")
            finally:
                self._return_connection(conn)
        else:
            self.init_sqlite(force=force)

    def run_auto_migrations(self, conn=None):
        """Ensures all new schema columns and tables exist on existing SQLite databases."""
        close_needed = False
        if conn is None:
            conn = sqlite3.connect(str(Config.SQLITE_PATH))
            close_needed = True
        cur = conn.cursor()
        try:
            # mine columns
            mine_cols = [r[1] for r in cur.execute("PRAGMA table_info(mines)").fetchall()]
            if "opening_stock_mt" not in mine_cols:
                cur.execute("ALTER TABLE mines ADD COLUMN opening_stock_mt REAL DEFAULT 5000.0")
            if "current_stock_mt" not in mine_cols:
                cur.execute("ALTER TABLE mines ADD COLUMN current_stock_mt REAL DEFAULT 5000.0")
            if "daily_production_mt" not in mine_cols:
                cur.execute("ALTER TABLE mines ADD COLUMN daily_production_mt REAL DEFAULT 500.0")
            if "daily_planned_dispatch_mt" not in mine_cols:
                cur.execute("ALTER TABLE mines ADD COLUMN daily_planned_dispatch_mt REAL DEFAULT 600.0")

            # truck columns
            truck_cols = [r[1] for r in cur.execute("PRAGMA table_info(trucks)").fetchall()]
            if "assigned_mine_id" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN assigned_mine_id INTEGER DEFAULT 1")
            if "allowed_rounds_per_day" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN allowed_rounds_per_day INTEGER DEFAULT 4")
            if "completed_rounds_today" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN completed_rounds_today INTEGER DEFAULT 0")
            if "current_round_number" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN current_round_number INTEGER DEFAULT 1")
            if "is_inside_mine" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN is_inside_mine INTEGER DEFAULT 0")
            if "current_mine_id" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN current_mine_id INTEGER")
            if "last_mine_entry" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN last_mine_entry DATETIME")
            if "last_mine_exit" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN last_mine_exit DATETIME")
            if "gps_status" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN gps_status TEXT DEFAULT 'HEALTHY'")
            if "network_blindspot_count" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN network_blindspot_count INTEGER DEFAULT 0")
            if "jammer_detected_count" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN jammer_detected_count INTEGER DEFAULT 0")
            if "tamper_count" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN tamper_count INTEGER DEFAULT 0")
            if "prohibited_zone_count" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN prohibited_zone_count INTEGER DEFAULT 0")
            if "satellite_count" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN satellite_count INTEGER DEFAULT 12")
            if "external_power_volts" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN external_power_volts REAL DEFAULT 24.2")
            if "backup_battery_pct" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN backup_battery_pct INTEGER DEFAULT 100")
            if "signal_strength_dbm" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN signal_strength_dbm INTEGER DEFAULT -65")
            if "carrier_noise_ratio_cno" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN carrier_noise_ratio_cno REAL DEFAULT 44.5")
            if "last_tamper_time" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN last_tamper_time DATETIME")
            if "last_tamper_type" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN last_tamper_type TEXT")
            if "transponder_model" not in truck_cols:
                cur.execute("ALTER TABLE trucks ADD COLUMN transponder_model TEXT DEFAULT 'AIS-140 IRNSS Rugged v4.2'")

            # GPS tamper events table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gps_tamper_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    truck_id INTEGER,
                    trip_id INTEGER,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    location_name TEXT,
                    satellite_count INTEGER DEFAULT 0,
                    external_power_volts REAL DEFAULT 24.0,
                    battery_level_pct INTEGER DEFAULT 100,
                    duration_seconds INTEGER DEFAULT 0,
                    detection_method TEXT,
                    evidence_notes TEXT,
                    action_taken TEXT,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Seed initial telemetry events if table is empty
            events_count = cur.execute("SELECT COUNT(*) FROM gps_tamper_events").fetchone()[0]
            if events_count == 0:
                past_1 = (datetime.now() - timedelta(minutes=42)).strftime("%Y-%m-%d %H:%M:%S")
                past_2 = (datetime.now() - timedelta(hours=1, minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
                past_3 = (datetime.now() - timedelta(hours=3, minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                past_4 = (datetime.now() - timedelta(hours=5, minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
                cur.executemany("""
                    INSERT INTO gps_tamper_events 
                    (truck_id, trip_id, event_type, severity, latitude, longitude, location_name, 
                     satellite_count, external_power_volts, battery_level_pct, duration_seconds, 
                     detection_method, evidence_notes, action_taken, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (1, 1, 'GPS_JAMMER_DETECTED', 'CRITICAL', 27.8520, 76.4530, 'Sabi Riverbed Outskirts (Behror-Kotputli)', 0, 24.2, 100, 840, 'RF C/N0 Collapse to 14 dB-Hz with active GSM ping', 'Deliberate high-power GNSS Jammer detected. GSM heartbeat continued while GNSS satellite lock collapsed to 0.', 'Alert generated; Case SMG-2026-00041 under investigation', 'ACTIVE', past_1),
                    (1, 1, 'HARDWARE_TAMPER_WIRE_CUT', 'HIGH', 27.8410, 76.4420, 'Kotputli Bypass Industrial Link', 11, 0.0, 94, 300, 'Main 24V Power Bus Severed (Internal 3.7V LiPo engaged)', 'Chassis tamper microswitch triggered and main vehicle power dropped from 24.2V to 0.0V.', 'Warning SMS dispatched to registered fleet owner', 'ACTIVE', past_2),
                    (3, 3, 'NETWORK_BLINDSPOT', 'LOW', 27.6100, 76.5800, 'Alwar South Ridge Canyon Passage', 10, 24.1, 100, 180, 'Gradual GSM cell handover timeout in rocky terrain', 'Normal GNSS satellite reception (10 sats) with temporary GSM cell tower packet retransmission delay.', 'Logged as standard network shadow zone', 'RESOLVED', past_3),
                    (4, 4, 'PROHIBITED_ZONE_INCURSION', 'HIGH', 27.9500, 76.5100, 'Aravalli Eco-Sensitive Buffer Zone', 12, 24.0, 100, 420, 'Geofence Polygon Boundary Breach', 'Vehicle lingered 7 minutes inside prohibited non-mining ecological buffer polygon.', 'Notice served to transport contractor', 'RESOLVED', past_4)
                ])
                # Initialize realistic counts on trucks
                cur.execute("UPDATE trucks SET gps_status = 'JAMMER_DETECTED', jammer_detected_count = 1, tamper_count = 1, network_blindspot_count = 1, satellite_count = 0, carrier_noise_ratio_cno = 14.2, last_tamper_type = 'GPS_JAMMER_RF' WHERE id = 1")
                cur.execute("UPDATE trucks SET network_blindspot_count = 2 WHERE id = 3")
                cur.execute("UPDATE trucks SET prohibited_zone_count = 1 WHERE id = 4")

            # permit columns
            permit_cols = [r[1] for r in cur.execute("PRAGMA table_info(permits)").fetchall()]
            if "reconciliation_reason" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN reconciliation_reason TEXT")
            if "buyer_type" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN buyer_type TEXT DEFAULT 'Registered Entity'")
            if "buyer_address" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN buyer_address TEXT")
            if "buyer_gstn" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN buyer_gstn TEXT")
            if "quarry_name" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN quarry_name TEXT")
            if "contractor_name" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN contractor_name TEXT")
            if "contractor_gstn" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN contractor_gstn TEXT")
            if "rate_per_mt" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN rate_per_mt REAL DEFAULT 336.00")
            if "taxable_amount" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN taxable_amount REAL")
            if "cgst_rate" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN cgst_rate REAL DEFAULT 2.50")
            if "cgst_amount" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN cgst_amount REAL")
            if "sgst_rate" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN sgst_rate REAL DEFAULT 2.50")
            if "sgst_amount" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN sgst_amount REAL")
            if "total_amount" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN total_amount REAL")
            if "hsn_code" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN hsn_code TEXT DEFAULT '2517'")
            if "weighment_slip_no" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN weighment_slip_no TEXT")
            if "auction_no" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN auction_no TEXT")
            if "pit_lot_no" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN pit_lot_no TEXT DEFAULT '21'")
            if "customer_code" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN customer_code TEXT DEFAULT '61'")
            if "balance_amount" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN balance_amount REAL DEFAULT 262969.59")
            if "cctv_image_front" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN cctv_image_front TEXT DEFAULT 'static/images/weighbridge/cctv_anpr_front.jpg'")
            if "cctv_image_back" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN cctv_image_back TEXT DEFAULT 'static/images/weighbridge/cctv_bed_overhead.jpg'")

            # trip columns
            trip_cols = [r[1] for r in cur.execute("PRAGMA table_info(trips)").fetchall()]
            if "round_number" not in trip_cols:
                cur.execute("ALTER TABLE trips ADD COLUMN round_number INTEGER DEFAULT 1")
            if "timeline_events_json" not in trip_cols:
                cur.execute("ALTER TABLE trips ADD COLUMN timeline_events_json TEXT DEFAULT '[]'")

            # weighment columns
            wb_cols = [r[1] for r in cur.execute("PRAGMA table_info(weighments)").fetchall()]
            if "measurement_source" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN measurement_source TEXT DEFAULT 'AUTOMATED_WEIGHBRIDGE_SCALE'")
            if "measurement_status" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN measurement_status TEXT DEFAULT 'VERIFIED'")
            if "is_manual_override" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN is_manual_override INTEGER DEFAULT 0")
            if "original_net_weight_mt" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN original_net_weight_mt REAL")
            if "override_reason" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN override_reason TEXT")
            if "override_by_user_id" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN override_by_user_id INTEGER")
            if "slip_number" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN slip_number TEXT")
            if "pit_lot_no" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN pit_lot_no TEXT DEFAULT '21'")
            if "customer_code" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN customer_code TEXT DEFAULT '61'")
            if "balance_amount" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN balance_amount REAL DEFAULT 262969.59")
            if "auction_number" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN auction_number TEXT")
            if "cctv_image_url" not in wb_cols:
                cur.execute("ALTER TABLE weighments ADD COLUMN cctv_image_url TEXT DEFAULT 'static/images/weighbridge/cctv_anpr_front.jpg'")

            # audit columns
            audit_cols = [r[1] for r in cur.execute("PRAGMA table_info(audit_logs)").fetchall()]
            if "entity" not in audit_cols:
                cur.execute("ALTER TABLE audit_logs ADD COLUMN entity TEXT")
            if "previous_state" not in audit_cols:
                cur.execute("ALTER TABLE audit_logs ADD COLUMN previous_state TEXT")
            if "new_state" not in audit_cols:
                cur.execute("ALTER TABLE audit_logs ADD COLUMN new_state TEXT")
            if "reason" not in audit_cols:
                cur.execute("ALTER TABLE audit_logs ADD COLUMN reason TEXT")

            # driver columns
            driver_cols = [r[1] for r in cur.execute("PRAGMA table_info(drivers)").fetchall()]
            if "allowed_rounds_per_day" not in driver_cols:
                cur.execute("ALTER TABLE drivers ADD COLUMN allowed_rounds_per_day INTEGER DEFAULT 4")
            if "completed_rounds_today" not in driver_cols:
                cur.execute("ALTER TABLE drivers ADD COLUMN completed_rounds_today INTEGER DEFAULT 0")

            # alert columns (Supervisory Vigilance Audit & Officer Triage)
            alert_cols = [r[1] for r in cur.execute("PRAGMA table_info(alerts)").fetchall()]
            if "handled_by_user_id" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN handled_by_user_id INTEGER")
            if "action_taken" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN action_taken TEXT")
            if "officer_remarks" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN officer_remarks TEXT")
            if "escalated_to_admin" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN escalated_to_admin INTEGER DEFAULT 0")
            if "admin_review_status" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN admin_review_status TEXT DEFAULT 'NONE'")
            if "admin_notes" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN admin_notes TEXT")
            if "admin_reviewed_at" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN admin_reviewed_at DATETIME")
            if "admin_reviewed_by" not in alert_cols:
                cur.execute("ALTER TABLE alerts ADD COLUMN admin_reviewed_by INTEGER")

            # permit columns (Sub-location & Issuance Type)
            permit_cols = [r[1] for r in cur.execute("PRAGMA table_info(permits)").fetchall()]
            if "quarry_block_id" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN quarry_block_id INTEGER")
            if "issuance_type" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN issuance_type TEXT DEFAULT 'AUTOMATED_SCALE_DISPATCH'")
            if "consumed_at" not in permit_cols:
                cur.execute("ALTER TABLE permits ADD COLUMN consumed_at DATETIME")

            # users columns (Assigned Concession Leasehold)
            user_cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
            if "assigned_mine_id" not in user_cols:
                cur.execute("ALTER TABLE users ADD COLUMN assigned_mine_id INTEGER DEFAULT 1")
            cur.execute("UPDATE users SET assigned_mine_id = 1 WHERE username IN ('officer1', 'operator1') AND (assigned_mine_id IS NULL OR assigned_mine_id = 0)")

            # quarry_blocks table (Mine Sub-Locations / Businessmen Concessions)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS quarry_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mine_id INTEGER REFERENCES mines(id),
                    block_code TEXT NOT NULL,
                    block_name TEXT NOT NULL,
                    leaseholder_name TEXT NOT NULL,
                    operator_name TEXT NOT NULL,
                    contact_phone TEXT,
                    allocated_quota_mt REAL DEFAULT 15000.0,
                    dispatched_mt REAL DEFAULT 0.0,
                    active_trucks_count INTEGER DEFAULT 4,
                    status TEXT DEFAULT 'OPERATIONAL',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Pre-seed realistic sub-locations if fewer than 10 blocks exist for Mine 1
            mine1_blocks = cur.execute("SELECT COUNT(*) FROM quarry_blocks WHERE mine_id = 1").fetchone()[0]
            if mine1_blocks < 10:
                # Remove stale test blocks if only 4 exist
                if mine1_blocks > 0 and mine1_blocks <= 4:
                    cur.execute("DELETE FROM quarry_blocks WHERE mine_id = 1")

                cur.executemany("""
                    INSERT INTO quarry_blocks 
                    (mine_id, block_code, block_name, leaseholder_name, operator_name, contact_phone, allocated_quota_mt, dispatched_mt, active_trucks_count, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    # Mine 1 (Aravalli Quartzite - Alwar) 36 sub-mine businessmen concession plots
                    (1, "QB-ALW-01", "Northern Quartzite Pit (Block 1A)", "Sharma Stone Aggregates Ltd. (Ramesh Sharma)", "Virendra Singh (Scale Operator 1)", "+91 98290 11223", 12000.0, 8400.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-02", "Eastern Crusher Lot (Block 2B)", "Yadav Minerals & Infrastructure (Sunil Yadav)", "Kailash Chand (Scale Operator 2)", "+91 98290 22334", 11000.0, 7800.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-03", "Ridge Basin Quarry (Block 3C)", "Aravalli Grit Suppliers (Pawan Choudhary)", "Mahesh Meena (Scale Operator 3)", "+91 98290 33445", 10000.0, 6900.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-04", "Deep Quarry Pit #4 (Block 4D)", "Apex Roadways & Stones (Vijay Aggarwal)", "Dinesh Rawat (Scale Operator 4)", "+91 98290 44556", 12000.0, 8150.0, 2, "OPERATIONAL"),
                    (1, "QB-ALW-05", "Sariska Buffer Escarpment (Plot 5E)", "Rajputana Quartzite Consortium (Bhanwar Singh)", "Ramavtar Gurjar (Scale Operator 5)", "+91 98290 55667", 14000.0, 9200.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-06", "Siliserh Escarpment Lot (Plot 6F)", "Singhal Granites & Crushing Ltd. (Mahesh Singhal)", "Satish Verma (Scale Operator 6)", "+91 98290 66778", 13500.0, 8900.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-07", "Alwar Blue Metal Basin (Plot 7G)", "Alwar Blue Metal Aggregates (Devendra Meena)", "Suraj Bhan (Scale Operator 7)", "+91 98290 77889", 15000.0, 11400.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-08", "Mewat Rock Extraction Cut (Plot 8H)", "Mewat Mineral Excavators (Abdul Hameed)", "Mohd. Aslam (Scale Operator 8)", "+91 98290 88990", 11500.0, 7100.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-09", "Shree Ram Crusher Field (Plot 9I)", "Shree Ram Stone Concessionaires (Gopal Sharma)", "Kishan Lal (Scale Operator 1)", "+91 98290 99001", 12500.0, 9800.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-10", "Karni Mata Highwall Pit (Plot 10J)", "Karni Mata Quarry Works (Vikramaditya Rathore)", "Madan Singh (Scale Operator 2)", "+91 98291 10101", 16000.0, 12800.0, 5, "OPERATIONAL"),
                    (1, "QB-ALW-11", "Tijara Ridge Basin (Plot 11K)", "Balaji Aggregates & Earthmovers (Manoj Saini)", "Deepak Saini (Scale Operator 3)", "+91 98291 21212", 10500.0, 6800.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-12", "Northern Highway Ballast Pit (Plot 12L)", "Northern Highway Ballast Suppliers (Harpreet Singh)", "Gurinder Singh (Scale Operator 4)", "+91 98291 32323", 14500.0, 11200.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-13", "Amber Quartzite Ledge (Plot 13M)", "Amber Stone Mining Consortium (Ashok Verma)", "Om Prakash (Scale Operator 5)", "+91 98291 43434", 12000.0, 8600.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-14", "Surya Grit Quarry Zone (Plot 14N)", "Surya Grit & Mining Works (Sanjay Tiwari)", "Nand Kishore (Scale Operator 6)", "+91 98291 54545", 13000.0, 9500.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-15", "Goyal Mineral Lot (Plot 15O)", "Goyal Mineral Logistics (Anurag Goyal)", "Mukesh Goyal (Scale Operator 7)", "+91 98291 65656", 11000.0, 7400.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-16", "Marwar Rock Terrace (Plot 16P)", "Marwar Rock Products Pvt Ltd (Surendra Shekhawat)", "Prithvi Singh (Scale Operator 8)", "+91 98291 76767", 15500.0, 12100.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-17", "Jaigarh Aggregates Sector (Plot 17Q)", "Jaigarh Aggregates & Silica (Deepak Gupta)", "Ravi Sharma (Scale Operator 1)", "+91 98291 87878", 12500.0, 8900.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-18", "Vijay Mining Concession Pit (Plot 18R)", "Vijay Mining Enterprises (Kamal Kishore)", "Rajesh Yadav (Scale Operator 2)", "+91 98291 98989", 14000.0, 10600.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-19", "Bhiwadi Industrial Buffer Quarry (Plot 19S)", "Bhiwadi Crushed Stone Co. (Praveen Bansal)", "Hemant Kumar (Scale Operator 3)", "+91 98292 01010", 16500.0, 13400.0, 5, "OPERATIONAL"),
                    (1, "QB-ALW-20", "Matsya Stone Quarry Bench (Plot 20T)", "Matsya Mining & Earthwork (Laxman Meena)", "Babu Lal (Scale Operator 4)", "+91 98292 12121", 11000.0, 7900.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-21", "Shahpura Highway Gravel Lot (Plot 21U)", "Shahpura Highway Material Suppliers (Naresh Gurjar)", "Subhash Gurjar (Scale Operator 5)", "+91 98292 23232", 13000.0, 9100.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-22", "Kishangarh Rail Ballast Lot (Plot 22V)", "Railtrack Mineral Aggregates (Kuldeep Bishnoi)", "Jaswant Singh (Scale Operator 6)", "+91 98292 34343", 15000.0, 11800.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-23", "Deewan Sandstone & Quartz Cut (Plot 23W)", "Deewan Mining Corporation (Trilok Deewan)", "Arjun Deewan (Scale Operator 7)", "+91 98292 45454", 12000.0, 8300.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-24", "Behror Border Extraction Zone (Plot 24X)", "Behror Stone Crushing Consortium (Ratan Lal)", "Pawan Saini (Scale Operator 8)", "+91 98292 56565", 14000.0, 10200.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-25", "Sunderban Quartzite Quarry Pit (Plot 25Y)", "Sunderban Minerals Ltd. (Jagdish Prasad)", "Ghanshyam (Scale Operator 1)", "+91 98292 67676", 11500.0, 8100.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-26", "Royal Stone Extraction Lot (Plot 26Z)", "Royal Rock Infrastructure (Ajay Choudhary)", "Bhupendra (Scale Operator 2)", "+91 98292 78787", 13500.0, 9700.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-27", "Krishna Aggregates Basin #2 (Plot 27AA)", "Krishna Mining & Trading Co. (Radhey Shyam)", "Dharampal (Scale Operator 3)", "+91 98292 89898", 12500.0, 8800.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-28", "Neemrana Industrial Aggregates (Plot 28AB)", "Neemrana Eco-Aggregates (Satyanarayan)", "Chhaju Ram (Scale Operator 4)", "+91 98292 90909", 17000.0, 14200.0, 5, "OPERATIONAL"),
                    (1, "QB-ALW-29", "Aravalli Valley Stone Pit #29 (Plot 29AC)", "Valley Minerals Consortium (Khemchand Yadav)", "Birendra (Scale Operator 5)", "+91 98293 01010", 10000.0, 6700.0, 2, "OPERATIONAL"),
                    (1, "QB-ALW-30", "Ganesh Stone Quarry Lot #30 (Plot 30AD)", "Ganesh Excavations & Crushing (Vinod Sharma)", "Jagmohan (Scale Operator 6)", "+91 98293 12121", 13000.0, 9400.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-31", "Sardar Stone Concession Pit #31 (Plot 31AE)", "Sardarji Roadways & Minerals (Tarlochan Singh)", "Satnam Singh (Scale Operator 7)", "+91 98293 23232", 14500.0, 11000.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-32", "Pratapgarh Rock Cutting Basin (Plot 32AF)", "Pratap Stone Infrastructure (Pratap Singh)", "Bhawani (Scale Operator 8)", "+91 98293 34343", 11000.0, 7600.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-33", "Everest Rock Aggregates (Plot 33AG)", "Everest Quarry & Grit Works (Mukesh Mittal)", "Banwari Lal (Scale Operator 1)", "+91 98293 45454", 15000.0, 11600.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-34", "Alwar South Border Pit #34 (Plot 34AH)", "South Valley Earthmovers (Harpal Meena)", "Giriraj (Scale Operator 2)", "+91 98293 56565", 12000.0, 8500.0, 3, "OPERATIONAL"),
                    (1, "QB-ALW-35", "Himalaya Grit & Rock Lot #35 (Plot 35AI)", "Himalaya Aggregates Syndicate (Rakesh Gupta)", "Mohan Lal (Scale Operator 3)", "+91 98293 67676", 13500.0, 9900.0, 4, "OPERATIONAL"),
                    (1, "QB-ALW-36", "Golden Rock Quarry Lot #36 (Plot 36AJ)", "Golden Crest Mining Ltd. (Dharmendra Soni)", "Kanhiya Lal (Scale Operator 4)", "+91 98293 78787", 16000.0, 13100.0, 4, "OPERATIONAL"),
                    
                    # Mine 2 (Kotputli Limestone) sub-blocks
                    (2, "QB-KOT-01", "High-Grade Limestone Sector A", "Shree Industrial Clinker Co.", "Om Prakash (Scale Operator 1)", "+91 94140 55667", 25000.0, 18200.0, 6, "OPERATIONAL"),
                    (2, "QB-KOT-02", "Commercial Limestone Pit B", "Bhiwadi Cement Raw Materials Ltd.", "Rajendra Prasad (Scale Operator 2)", "+91 94140 66778", 22000.0, 15900.0, 5, "OPERATIONAL"),
                    (2, "QB-KOT-03", "Western Dolomite & Rock Plot", "Rajdhani Aggregates Consortium", "Suresh Gurjar (Scale Operator 3)", "+91 94140 77889", 20000.0, 13400.0, 4, "OPERATIONAL"),
                    (2, "QB-KOT-04", "Northern Buffer Extraction Block", "Kisan Stone Crushing Works", "Harish Kumar (Scale Operator 4)", "+91 94140 88990", 18000.0, 10900.0, 3, "OPERATIONAL"),

                    # Mine 3 (Khol Silica Sand - Rewari, Haryana) sub-blocks
                    (3, "QB-REW-01", "Khol Riverbank Sand Concession #1", "Haryana Glass Sand Producers (Anil Mittal)", "Jagdish Chand (Scale Operator 1)", "+91 98120 11223", 10000.0, 9400.0, 4, "OPERATIONAL"),
                    (3, "QB-REW-02", "Rewari Silica Extraction Basin #2", "Mittal Silica Minerals (Pardeep Mittal)", "Satbir Singh (Scale Operator 2)", "+91 98120 22334", 10000.0, 9800.0, 3, "OPERATIONAL"),
                    (3, "QB-REW-03", "South Khol Co-operative Plot", "Khol Miners Welfare Union (Sukhbir Yadav)", "Baljit Yadav (Scale Operator 3)", "+91 98120 33445", 10000.0, 9700.0, 3, "OPERATIONAL")
                ])

            conn.commit()
        finally:
            if close_needed:
                conn.close()

    def init_sqlite(self, force=False):
        """Set up SQLite with identical schema and realistic demo data."""
        try:
            Config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        conn = sqlite3.connect(str(Config.SQLITE_PATH))
        cur = conn.cursor()

        if not force:
            try:
                has_users = cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
                if has_users:
                    user_count = cur.execute("SELECT count(*) FROM users").fetchone()[0]
                    if user_count > 0:
                        conn.close()
                        return
            except Exception:
                pass

        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT DEFAULT 'Department of Mines & Geology',
            badge_number TEXT,
            email TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS mines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mine_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            mineral TEXT NOT NULL,
            district TEXT NOT NULL,
            state TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            authorized_annual_quota_mt REAL NOT NULL DEFAULT 50000.0,
            current_dispatch_mt REAL NOT NULL DEFAULT 0.0,
            status TEXT DEFAULT 'OPERATIONAL',
            operator_name TEXT NOT NULL,
            contact_phone TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trucks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_number TEXT UNIQUE NOT NULL,
            vehicle_type TEXT DEFAULT '10-Wheeler Tipper Truck',
            registered_owner TEXT NOT NULL,
            driver_name TEXT NOT NULL,
            driver_phone TEXT,
            tare_weight_mt REAL NOT NULL DEFAULT 11.5,
            max_capacity_mt REAL NOT NULL DEFAULT 28.0,
            rfid_tag TEXT UNIQUE,
            gps_imei TEXT UNIQUE,
            status TEXT DEFAULT 'IDLE',
            current_lat REAL,
            current_lng REAL,
            last_gps_time DATETIME,
            current_risk_score INTEGER DEFAULT 0,
            current_risk_level TEXT DEFAULT 'LOW',
            assigned_mine_id INTEGER DEFAULT 1,
            allowed_rounds_per_day INTEGER DEFAULT 4,
            completed_rounds_today INTEGER DEFAULT 0,
            current_round_number INTEGER DEFAULT 1,
            is_inside_mine INTEGER DEFAULT 0,
            current_mine_id INTEGER,
            last_mine_entry DATETIME,
            last_mine_exit DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS permits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_number TEXT UNIQUE NOT NULL,
            qr_code_hash TEXT UNIQUE NOT NULL,
            truck_id INTEGER,
            mine_id INTEGER,
            mineral TEXT NOT NULL,
            permitted_weight_mt REAL NOT NULL,
            source_name TEXT NOT NULL,
            destination_name TEXT NOT NULL,
            destination_lat REAL NOT NULL,
            destination_lng REAL NOT NULL,
            buyer_name TEXT NOT NULL,
            issued_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            status TEXT DEFAULT 'ACTIVE',
            reconciliation_reason TEXT,
            route_waypoints_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_number TEXT UNIQUE NOT NULL,
            permit_id INTEGER,
            truck_id INTEGER,
            mine_id INTEGER,
            round_number INTEGER DEFAULT 1,
            status TEXT DEFAULT 'DISPATCHED',
            start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_time DATETIME,
            planned_distance_km REAL NOT NULL DEFAULT 45.0,
            actual_distance_km REAL DEFAULT 0.0,
            max_recorded_speed_kmh REAL DEFAULT 0.0,
            avg_speed_kmh REAL DEFAULT 0.0,
            timeline_events_json TEXT DEFAULT '[]',
            risk_score INTEGER DEFAULT 0,
            risk_level TEXT DEFAULT 'LOW',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS weighments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER,
            permit_id INTEGER,
            truck_id INTEGER,
            weighbridge_code TEXT NOT NULL,
            weighbridge_name TEXT NOT NULL,
            gross_weight_mt REAL NOT NULL,
            tare_weight_mt REAL NOT NULL,
            net_weight_mt REAL NOT NULL,
            permitted_weight_mt REAL NOT NULL,
            difference_mt REAL NOT NULL,
            is_overweight INTEGER DEFAULT 0,
            measurement_source TEXT DEFAULT 'AUTOMATED_WEIGHBRIDGE_SCALE',
            measurement_status TEXT DEFAULT 'VERIFIED',
            is_manual_override INTEGER DEFAULT 0,
            original_net_weight_mt REAL,
            override_reason TEXT,
            override_by_user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS gps_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id INTEGER,
            truck_id INTEGER,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            speed_kmh REAL DEFAULT 0.0,
            heading REAL DEFAULT 0.0,
            deviation_distance_m REAL DEFAULT 0.0,
            is_deviated INTEGER DEFAULT 0,
            in_suspicious_zone INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS geofences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            zone_type TEXT NOT NULL,
            polygon_coordinates_json TEXT NOT NULL,
            severity TEXT DEFAULT 'HIGH'
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_code TEXT UNIQUE NOT NULL,
            trip_id INTEGER,
            truck_id INTEGER,
            permit_id INTEGER,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            risk_score INTEGER NOT NULL,
            description TEXT NOT NULL,
            evidence_json TEXT,
            status TEXT DEFAULT 'NEW',
            assigned_to_user_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT UNIQUE NOT NULL,
            alert_id INTEGER,
            trip_id INTEGER,
            truck_id INTEGER,
            permit_id INTEGER,
            lead_officer_id INTEGER,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'OPEN',
            initial_findings TEXT NOT NULL,
            officer_notes TEXT,
            final_decision TEXT,
            penalty_amount_inr REAL DEFAULT 0.0,
            pdf_report_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permit_id INTEGER,
            officer_id INTEGER,
            checkpoint_name TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            verification_result TEXT NOT NULL,
            scanned_via TEXT DEFAULT 'QR_SCAN',
            discrepancy_notes TEXT,
            verified_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            details TEXT,
            entity TEXT,
            previous_state TEXT,
            new_state TEXT,
            reason TEXT,
            ip_address TEXT DEFAULT '127.0.0.1',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_name TEXT NOT NULL,
            license_number TEXT UNIQUE NOT NULL,
            contact_phone TEXT,
            assigned_truck_id INTEGER,
            status TEXT DEFAULT 'ACTIVE',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS weighbridges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            mine_id INTEGER,
            operator_name TEXT,
            capacity_mt REAL DEFAULT 100.0,
            status TEXT DEFAULT 'OPERATIONAL',
            latitude REAL,
            longitude REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            destination_type TEXT DEFAULT 'CRUSHER',
            license_number TEXT,
            district TEXT NOT NULL,
            state TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            authorized_minerals TEXT,
            status TEXT DEFAULT 'AUTHORIZED',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            district TEXT NOT NULL,
            state TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            authorized_route TEXT,
            status TEXT DEFAULT 'ACTIVE',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stock_production (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mine_id INTEGER NOT NULL,
            mineral TEXT NOT NULL,
            record_date DATE DEFAULT (DATE('now')),
            opening_stock_mt REAL NOT NULL,
            production_mt REAL NOT NULL DEFAULT 0.0,
            dispatch_mt REAL NOT NULL DEFAULT 0.0,
            closing_stock_mt REAL NOT NULL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Auto-migration: ensure columns exist on existing databases
        mine_cols = [r[1] for r in cur.execute("PRAGMA table_info(mines)").fetchall()]
        if "opening_stock_mt" not in mine_cols:
            cur.execute("ALTER TABLE mines ADD COLUMN opening_stock_mt REAL DEFAULT 5000.0")
        if "current_stock_mt" not in mine_cols:
            cur.execute("ALTER TABLE mines ADD COLUMN current_stock_mt REAL DEFAULT 5000.0")
        if "daily_production_mt" not in mine_cols:
            cur.execute("ALTER TABLE mines ADD COLUMN daily_production_mt REAL DEFAULT 500.0")
        if "daily_planned_dispatch_mt" not in mine_cols:
            cur.execute("ALTER TABLE mines ADD COLUMN daily_planned_dispatch_mt REAL DEFAULT 600.0")

        truck_cols = [r[1] for r in cur.execute("PRAGMA table_info(trucks)").fetchall()]
        if "assigned_mine_id" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN assigned_mine_id INTEGER DEFAULT 1")
        if "allowed_rounds_per_day" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN allowed_rounds_per_day INTEGER DEFAULT 4")
        if "completed_rounds_today" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN completed_rounds_today INTEGER DEFAULT 0")
        if "current_round_number" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN current_round_number INTEGER DEFAULT 1")
        if "is_inside_mine" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN is_inside_mine INTEGER DEFAULT 0")
        if "current_mine_id" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN current_mine_id INTEGER")
        if "last_mine_entry" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN last_mine_entry DATETIME")
        if "last_mine_exit" not in truck_cols:
            cur.execute("ALTER TABLE trucks ADD COLUMN last_mine_exit DATETIME")

        permit_cols = [r[1] for r in cur.execute("PRAGMA table_info(permits)").fetchall()]
        if "reconciliation_reason" not in permit_cols:
            cur.execute("ALTER TABLE permits ADD COLUMN reconciliation_reason TEXT")

        trip_cols = [r[1] for r in cur.execute("PRAGMA table_info(trips)").fetchall()]
        if "round_number" not in trip_cols:
            cur.execute("ALTER TABLE trips ADD COLUMN round_number INTEGER DEFAULT 1")
        if "timeline_events_json" not in trip_cols:
            cur.execute("ALTER TABLE trips ADD COLUMN timeline_events_json TEXT DEFAULT '[]'")

        wb_cols = [r[1] for r in cur.execute("PRAGMA table_info(weighments)").fetchall()]
        if "measurement_source" not in wb_cols:
            cur.execute("ALTER TABLE weighments ADD COLUMN measurement_source TEXT DEFAULT 'AUTOMATED_WEIGHBRIDGE_SCALE'")
        if "measurement_status" not in wb_cols:
            cur.execute("ALTER TABLE weighments ADD COLUMN measurement_status TEXT DEFAULT 'VERIFIED'")
        if "is_manual_override" not in wb_cols:
            cur.execute("ALTER TABLE weighments ADD COLUMN is_manual_override INTEGER DEFAULT 0")
        if "original_net_weight_mt" not in wb_cols:
            cur.execute("ALTER TABLE weighments ADD COLUMN original_net_weight_mt REAL")
        if "override_reason" not in wb_cols:
            cur.execute("ALTER TABLE weighments ADD COLUMN override_reason TEXT")
        if "override_by_user_id" not in wb_cols:
            cur.execute("ALTER TABLE weighments ADD COLUMN override_by_user_id INTEGER")

        audit_cols = [r[1] for r in cur.execute("PRAGMA table_info(audit_logs)").fetchall()]
        if "entity" not in audit_cols:
            cur.execute("ALTER TABLE audit_logs ADD COLUMN entity TEXT")
        if "previous_state" not in audit_cols:
            cur.execute("ALTER TABLE audit_logs ADD COLUMN previous_state TEXT")
        if "new_state" not in audit_cols:
            cur.execute("ALTER TABLE audit_logs ADD COLUMN new_state TEXT")
        if "reason" not in audit_cols:
            cur.execute("ALTER TABLE audit_logs ADD COLUMN reason TEXT")

        driver_cols = [r[1] for r in cur.execute("PRAGMA table_info(drivers)").fetchall()]
        if "allowed_rounds_per_day" not in driver_cols:
            cur.execute("ALTER TABLE drivers ADD COLUMN allowed_rounds_per_day INTEGER DEFAULT 4")
        if "completed_rounds_today" not in driver_cols:
            cur.execute("ALTER TABLE drivers ADD COLUMN completed_rounds_today INTEGER DEFAULT 0")

        # Explicitly align existing fleet with their respective concession leaseholds
        cur.execute("UPDATE trucks SET assigned_mine_id = 1 WHERE id IN (1, 3, 5)")
        cur.execute("UPDATE trucks SET assigned_mine_id = 2 WHERE id IN (2, 7)")
        cur.execute("UPDATE trucks SET assigned_mine_id = 3 WHERE id IN (4, 6)")
        cur.execute("UPDATE trucks SET assigned_mine_id = 4 WHERE id = 8")

        # Insert Seed Data
        # Users
        cur.executemany("""
        INSERT OR IGNORE INTO users (id, username, password_hash, full_name, role, department, badge_number, email, phone)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'admin', 'scrypt:32768:8:1$Zr30Mc23gHWgwT8A$270528ddd472694daf5a7f3cdd6592e8b731511c38b482f439ac766beb660bd2d61bd76b7a9c2e378b8a55f3ae75a2803934f7e66ffe05398acb4daf895cba54', 'Sanjay Verma, IAS', 'ADMIN', 'Directorate of Mines & Geology', 'DMG-HQ-01', 'sanjay.verma@mines.gov.in', '+91 98100 11223'),
            (2, 'officer1', 'scrypt:32768:8:1$FK4stxukDtMqpkeV$860bedbad7459012931eed20b028629d2dc3d57a57e9479251ade9c2687169258ff8521cf85aa74963383905c5e866474c72e45f11cc3d7bedd21b8fe8e747de', 'Inspector Rajesh K. Meena', 'OFFICER', 'Mining Enforcement Squad Zone 4', 'MES-Z4-409', 'rajesh.meena@enforcement.gov.in', '+91 94140 22334'),
            (3, 'operator1', 'scrypt:32768:8:1$LPCNLxkf3VowPuNr$81c09abbf1e26043183f4f42f34efe09be08859d32288a45c80a237df3ef3d2494b0dc646dcf5f1f743b86cc51153edb72a218cdf4a64e0d67b8e467850f3f90', 'Virendra Singh Rathore', 'OPERATOR', 'Aravalli Quartzite Consortium', 'OP-RJ-08', 'virendra@aravalliminerals.com', '+91 99280 33445'),
            (4, 'admin1', 'scrypt:32768:8:1$Zr30Mc23gHWgwT8A$270528ddd472694daf5a7f3cdd6592e8b731511c38b482f439ac766beb660bd2d61bd76b7a9c2e378b8a55f3ae75a2803934f7e66ffe05398acb4daf895cba54', 'Sanjay Verma, IAS', 'ADMIN', 'Directorate of Mines & Geology', 'DMG-HQ-01', 'sanjay.verma@mines.gov.in', '+91 98100 11223')
        ])

        # Mines
        cur.executemany("""
        INSERT OR IGNORE INTO mines (id, mine_code, name, mineral, district, state, latitude, longitude, authorized_annual_quota_mt, current_dispatch_mt, status, operator_name, contact_phone, opening_stock_mt, current_stock_mt, daily_production_mt, daily_planned_dispatch_mt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'MN-RJ-ALW-01', 'Aravalli Quartzite Quarry Block A', 'Quartzite', 'Alwar', 'Rajasthan', 27.5624, 76.6121, 45000.0, 31250.0, 'OPERATIONAL', 'Aravalli Quartzite Consortium', '+91 99280 33445', 4200.0, 4370.0, 650.0, 700.0),
            (2, 'MN-RJ-KOT-04', 'Kotputli High-Grade Limestone Lease', 'Limestone', 'Kotputli-Behror', 'Rajasthan', 27.7052, 76.2023, 85000.0, 58400.0, 'OPERATIONAL', 'Shree Cement Raw Materials Div.', '+91 94142 88776', 7800.0, 8050.0, 1100.0, 1200.0),
            (3, 'MN-HR-REW-02', 'Khol Silica Sand & Stone Pit', 'Silica Sand', 'Rewari', 'Haryana', 28.1884, 76.6210, 30000.0, 28900.0, 'OPERATIONAL', 'Khol Mining Cooperative', '+91 98122 44332', 2900.0, 2970.0, 450.0, 500.0),
            (4, 'MN-RJ-JHJ-09', 'Khetri Copper Tailings & Rock Zone', 'Copper Tailings / Quartz', 'Jhunjhunu', 'Rajasthan', 28.0125, 75.7891, 60000.0, 64200.0, 'QUOTA_EXCEEDED', 'Hindustan Quarrying Partners', '+91 97841 55667', 5400.0, 5480.0, 800.0, 900.0)
        ])

        # Trucks
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.executemany("""
        INSERT OR IGNORE INTO trucks (id, registration_number, vehicle_type, registered_owner, driver_name, driver_phone, tare_weight_mt, max_capacity_mt, rfid_tag, gps_imei, status, current_lat, current_lng, last_gps_time, current_risk_score, current_risk_level, assigned_mine_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'HR26AB1234', '10-Wheeler Tipper Truck', 'Shri Ram Logistics Pvt Ltd', 'Vikram Singh', '+91 98123 45678', 11.5, 28.0, 'RFID-HR26-001', '864201045678901', 'IN_TRANSIT', 27.8520, 76.4530, now_str, 92, 'CRITICAL', 1),
            (2, 'RJ14GA5521', '12-Wheeler Dump Truck', 'Aravalli Freightways', 'Ramesh Gurjar', '+91 94141 89765', 12.8, 32.0, 'RFID-RJ14-002', '864201045678902', 'IN_TRANSIT', 27.6800, 76.3500, now_str, 15, 'LOW', 2),
            (3, 'OD02BA8812', '10-Wheeler Tipper Truck', 'Kalinga Mineral Carrier', 'Sunil Yadav', '+91 99370 12345', 11.2, 28.0, 'RFID-OD02-003', '864201045678903', 'IN_TRANSIT', 27.6100, 76.5800, now_str, 75, 'HIGH', 1),
            (4, 'HR38EF9012', '14-Wheeler Multi-Axle', 'Highway Haulers Corp', 'Balwinder Singh', '+91 98188 67890', 14.0, 40.0, 'RFID-HR38-004', '864201045678904', 'IN_TRANSIT', 27.9500, 76.5100, now_str, 65, 'HIGH', 3),
            (5, 'RJ32CD3344', '10-Wheeler Tipper Truck', 'Meena Stone Transporters', 'Manoj Meena', '+91 97820 44556', 11.0, 26.0, 'RFID-RJ32-005', '864201045678905', 'LOADING', 27.5630, 76.6110, now_str, 10, 'LOW', 1),
            (6, 'DL1LA9022', '10-Wheeler Tipper Truck', 'Capital Bulk Carriers', 'Dharmendra Sharma', '+91 98111 22334', 11.6, 28.0, 'RFID-DL1L-006', '864201045678906', 'IDLE', 28.1850, 76.6200, now_str, 5, 'LOW', 3),
            (7, 'UP16BT4055', '12-Wheeler Dump Truck', 'Noida Aggregate Movers', 'Satish Kumar', '+91 98710 55443', 13.0, 34.0, 'RFID-UP16-007', '864201045678907', 'IN_TRANSIT', 27.7900, 76.4100, now_str, 25, 'LOW', 2),
            (8, 'RJ02CB7811', '10-Wheeler Tipper Truck', 'Mewat Minerals Transport', 'Imran Khan', '+91 99291 77665', 11.4, 28.0, 'RFID-RJ02-008', '864201045678908', 'IN_TRANSIT', 27.6300, 76.5200, now_str, 45, 'MEDIUM', 1)
        ])

        # Permits
        cur.executemany("""
        INSERT OR IGNORE INTO permits (id, permit_number, qr_code_hash, truck_id, mine_id, mineral, permitted_weight_mt, source_name, destination_name, destination_lat, destination_lng, buyer_name, issued_at, expires_at, status, route_waypoints_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'SMG-2026-00125', 'e9b28a71c3f412d08a5c1029384756ab1234567890abcdef1234567890abcdef', 1, 1, 'Quartzite Aggregate', 20.0, 'Aravalli Quarry Block A (Alwar)', 'Bhiwadi Industrial Crushing Zone', 28.2100, 76.8600, 'Bhiwadi Aggregates & ReadyMix Ltd', (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"), (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S"), 'ACTIVE', '[[27.5624, 76.6121], [27.7200, 76.5100], [27.9800, 76.6800], [28.2100, 76.8600]]'),
            (2, 'TRP-2026-00124', 'f1c43a82b9e715d29b6d2130495867bc2345678901bcdef012345678901bcdef', 2, 2, 'Limestone Raw Boulder', 25.0, 'Kotputli Limestone Lease', 'Neemrana Cement Works Unit-2', 27.9850, 76.3850, 'Neemrana Cement & Clinker Ltd', (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), (datetime.now() + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"), 'ACTIVE', '[[27.7052, 76.2023], [27.8400, 76.2900], [27.9850, 76.3850]]'),
            (3, 'TRP-2026-00088', 'a3d54b93c8f826e30c7e3241506978cd3456789012cdef0123456789012cdef', 3, 1, 'Quartzite Sand', 22.0, 'Aravalli Quarry Block A (Alwar)', 'Manesar Infrastructure Hub', 28.3500, 76.9400, 'DLF Urban Infra Projects', (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"), (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), 'CONSUMED', '[[27.5624, 76.6121], [27.8900, 76.7200], [28.3500, 76.9400]]'),
            (4, 'TRP-2026-00130', 'b4e65c04d9a937f41d8f4352617089de4567890123def01234567890123def', 4, 3, 'Silica Sand Grade-I', 30.0, 'Khol Silica Sand Pit (Rewari)', 'Jaipur Glass Containers Ltd', 26.9124, 75.7873, 'Jaipur Glassware Industries', (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), (datetime.now() + timedelta(hours=11)).strftime("%Y-%m-%d %H:%M:%S"), 'ACTIVE', '[[28.1884, 76.6210], [27.8000, 76.3000], [27.2000, 75.9000], [26.9124, 75.7873]]')
        ])

        # Seed Timeline for Trip 1
        timeline_1 = json.dumps([
            {"timestamp": (datetime.now() - timedelta(hours=2, minutes=15)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Truck Entered Mine", "details": "GPS geofence entry detected at Aravalli Quarry Block A (Alwar)", "status": "COMPLIANT"},
            {"timestamp": (datetime.now() - timedelta(hours=2, minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), "title": "e-Rawaana Pass Matched", "details": "Validated SMG-2026-00125 for Round #1 (20.0 MT Quartzite Aggregate)", "status": "COMPLIANT"},
            {"timestamp": (datetime.now() - timedelta(hours=1, minutes=45)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Automated Scale Weighment", "details": "Gross: 42.5 MT, Tare: 11.5 MT -> Net: 31.0 MT (+11.0 MT OVERLOAD)", "status": "VIOLATION"},
            {"timestamp": (datetime.now() - timedelta(hours=1, minutes=40)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Dispatch Authorized & Gate Exit", "details": "Vehicle departed pithead gate. Round #1 completed, in transit.", "status": "COMPLIANT"},
            {"timestamp": (datetime.now() - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Route Corridor Deviation", "details": "Diverted 1,420m outside NH-48 towards Sabi riverbed link road", "status": "CRITICAL"},
            {"timestamp": (datetime.now() - timedelta(minutes=14)).strftime("%Y-%m-%d %H:%M:%S"), "title": "GPS Blackout Event", "details": "Telemetry dropped near Sabi Riverbed restricted mining zone", "status": "CRITICAL"}
        ])

        timeline_2 = json.dumps([
            {"timestamp": (datetime.now() - timedelta(hours=1, minutes=15)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Truck Entered Mine", "details": "GPS geofence entry detected at Kotputli Limestone Lease", "status": "COMPLIANT"},
            {"timestamp": (datetime.now() - timedelta(hours=1, minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), "title": "e-Rawaana Pass Matched", "details": "Validated TRP-2026-00124 for Round #1 (25.0 MT Limestone)", "status": "COMPLIANT"},
            {"timestamp": (datetime.now() - timedelta(minutes=50)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Automated Scale Weighment", "details": "Gross: 36.5 MT, Tare: 12.8 MT -> Net: 23.7 MT (Compliant)", "status": "COMPLIANT"},
            {"timestamp": (datetime.now() - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"), "title": "Mine Exit & Transit", "details": "Dispatched to Neemrana Cement Works via NH-48", "status": "COMPLIANT"}
        ])

        # Trips
        cur.executemany("""
        INSERT OR IGNORE INTO trips (id, trip_number, permit_id, truck_id, mine_id, round_number, status, start_time, planned_distance_km, actual_distance_km, max_recorded_speed_kmh, avg_speed_kmh, timeline_events_json, risk_score, risk_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'TRIP-2026-00501', 1, 1, 1, 1, 'IN_TRANSIT', (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), 78.0, 48.5, 68.0, 42.0, timeline_1, 92, 'CRITICAL'),
            (2, 'TRIP-2026-00502', 2, 2, 2, 1, 'IN_TRANSIT', (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"), 42.0, 22.0, 52.0, 38.0, timeline_2, 15, 'LOW'),
            (3, 'TRIP-2026-00503', 3, 3, 1, 2, 'SUSPICIOUS', (datetime.now() - timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S"), 95.0, 18.0, 60.0, 35.0, '[]', 75, 'HIGH'),
            (4, 'TRIP-2026-00504', 4, 4, 3, 1, 'IN_TRANSIT', (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"), 155.0, 32.0, 96.0, 88.0, '[]', 65, 'HIGH')
        ])

        # Weighments
        cur.executemany("""
        INSERT OR IGNORE INTO weighments (id, trip_id, permit_id, truck_id, weighbridge_code, weighbridge_name, gross_weight_mt, tare_weight_mt, net_weight_mt, permitted_weight_mt, difference_mt, is_overweight, measurement_source, measurement_status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'AUTOMATED_WEIGHBRIDGE_SCALE', 'VERIFIED', ?)
        """, [
            (1, 1, 1, 1, 'WB-ALW-01', 'Alwar Mining Exit Weighbridge #1', 42.5, 11.5, 31.0, 20.0, 11.0, 1, (datetime.now() - timedelta(hours=1, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")),
            (2, 2, 2, 2, 'WB-KOT-02', 'Kotputli Lease Perimeter Weighbridge', 36.5, 12.8, 23.7, 25.0, -1.3, 0, (datetime.now() - timedelta(minutes=50)).strftime("%Y-%m-%d %H:%M:%S")),
            (3, 4, 4, 4, 'WB-REW-01', 'Rewari Industrial Toll Weighbridge', 43.8, 14.0, 29.8, 30.0, -0.2, 0, (datetime.now() - timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S"))
        ])

        # Geofences
        cur.executemany("""
        INSERT OR IGNORE INTO geofences (id, name, zone_type, polygon_coordinates_json, severity)
        VALUES (?, ?, ?, ?, ?)
        """, [
            (1, 'Sabi Riverbed Restricted Mining Zone', 'RESTRICTED_RIVERBED', '[[27.8000, 76.3800], [27.8600, 76.3900], [27.8500, 76.4600], [27.7900, 76.4400]]', 'CRITICAL'),
            (2, 'NH-48 Legal Mineral Transport Corridor', 'CORRIDOR', '[[27.5500, 76.6000], [27.7500, 76.4500], [28.0000, 76.6500], [28.2500, 76.8500]]', 'HIGH'),
            (3, 'Sariska Tiger Reserve Northern Buffer', 'ECOLOGICAL_BUFFER', '[[27.4000, 76.5000], [27.5200, 76.5200], [27.5000, 76.6200], [27.3800, 76.5800]]', 'CRITICAL')
        ])

        # Alerts
        cur.executemany("""
        INSERT OR IGNORE INTO alerts (id, alert_code, trip_id, truck_id, permit_id, alert_type, severity, risk_score, description, evidence_json, status, assigned_to_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'ALT-2026-00101', 1, 1, 1, 'WEIGHT_ANOMALY', 'CRITICAL', 30, 'Weighbridge Net Weight 31.0 MT exceeds e-Rawaana permitted limit 20.0 MT (+11.0 MT / +55.0% overload).', '{"permitted_mt": 20.0, "actual_mt": 31.0, "difference_mt": 11.0, "weighbridge": "WB-ALW-01", "tolerance_exceeded": true}', 'NEW', 2),
            (2, 'ALT-2026-00102', 1, 1, 1, 'ROUTE_DEVIATION', 'HIGH', 20, 'Vehicle deviated 1,420m outside permitted NH-48 mineral transit corridor toward unmonitored rural link.', '{"deviation_m": 1420, "allowed_corridor_m": 350, "last_lat": 27.8520, "last_lng": 76.4530, "corridor": "NH-48"}', 'NEW', 2),
            (3, 'ALT-2026-00103', 1, 1, 1, 'GPS_BLACKOUT', 'HIGH', 20, 'GPS heartbeat lost for 14 minutes immediately adjacent to Sabi Riverbed Restricted Mining Zone.', '{"blackout_duration_min": 14, "proximity_zone": "Sabi Riverbed Restricted Mining Zone", "last_ping_lat": 27.8520, "last_ping_lng": 76.4530}', 'NEW', 2),
            (4, 'ALT-2026-00104', 3, 3, 3, 'PERMIT_REUSE', 'CRITICAL', 30, 'e-Rawaana TRP-2026-00088 is being presented by Truck OD02BA8812 after already being marked CONSUMED 10 hours ago.', '{"permit_number": "TRP-2026-00088", "original_status": "CONSUMED", "scanned_truck": "OD02BA8812"}', 'NEW', 2),
            (5, 'ALT-2026-00105', 4, 4, 4, 'IMPOSSIBLE_TRANSIT', 'HIGH', 30, 'Transit telemetry indicates average speed of 88.0 km/h with 96.0 km/h bursts on mountainous terrain (Maximum legal tipper speed: 85 km/h).', '{"avg_speed_kmh": 88.0, "max_speed_kmh": 96.0, "legal_limit_kmh": 85.0}', 'ACKNOWLEDGED', 2),
            (6, 'ALT-2026-00106', None, None, None, 'PRODUCTION_MISMATCH', 'HIGH', 30, 'Mine MN-RJ-JHJ-09 (Khetri Zone) has dispatched 64,200 MT exceeding its authorized annual mining quota of 60,000 MT (+4,200 MT unpermitted extraction).', '{"mine_code": "MN-RJ-JHJ-09", "authorized_quota_mt": 60000.0, "current_dispatch_mt": 64200.0, "excess_mt": 4200.0}', 'NEW', 1)
        ])

        # Investigations
        cur.executemany("""
        INSERT OR IGNORE INTO investigations (id, case_id, alert_id, trip_id, truck_id, permit_id, lead_officer_id, title, status, initial_findings, officer_notes, final_decision, penalty_amount_inr, pdf_report_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'SMG-2026-00041', 1, 1, 1, 1, 2, 'Enforcement Case: Overweight Dispatch & Route Deviation - Truck HR26AB1234', 'UNDER_INVESTIGATION', 'Vehicle HR26AB1234 dispatched from Aravalli Quarry Block A with +11 MT excess Quartzite. Vehicle subsequently diverted 1.4km from legal corridor into rural link road toward Sabi riverbed with intermittent GPS loss.', 'Enforcement squad intercepted vehicle at Kotputli bypass junction. Physical weighment verified 31.2 MT net load. Driver failed to present valid extension permit. Notice served under Section 21 of MMDR Act.', 'Vehicle impounded at Behror police yard pending compounding fee and environmental damage assessment.', 175000.0, 'static/reports/dossier_SMG-2026-00041.pdf')
        ])

        # Drivers
        cur.executemany("""
        INSERT OR IGNORE INTO drivers (id, driver_name, license_number, contact_phone, assigned_truck_id, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (1, 'Vikram Singh', 'DL-0420180091234', '+91 98123 45678', 1, 'ACTIVE'),
            (2, 'Ramesh Gurjar', 'RJ-1420190082341', '+91 94141 89765', 2, 'ACTIVE'),
            (3, 'Sunil Yadav', 'OD-0220200073412', '+91 99370 12345', 3, 'ACTIVE'),
            (4, 'Balwinder Singh', 'HR-3820170064523', '+91 98188 67890', 4, 'ACTIVE'),
            (5, 'Manoj Meena', 'RJ-3220210055634', '+91 97820 44556', 5, 'ACTIVE'),
            (6, 'Dharmendra Sharma', 'DL-1L20160046745', '+91 98111 22334', 6, 'ACTIVE'),
            (7, 'Satish Kumar', 'UP-1620220037856', '+91 98710 55443', 7, 'ACTIVE'),
            (8, 'Imran Khan', 'RJ-0220190028967', '+91 99291 77665', 8, 'ACTIVE')
        ])

        # Weighbridges
        cur.executemany("""
        INSERT OR IGNORE INTO weighbridges (id, code, name, location, mine_id, operator_name, capacity_mt, status, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'WB-ALW-01', 'Alwar Mining Exit Weighbridge #1', 'Alwar Bypass, NH-248A', 1, 'Aravalli Quartzite Consortium', 100.0, 'OPERATIONAL', 27.5680, 76.6180),
            (2, 'WB-KOT-02', 'Kotputli Lease Perimeter Weighbridge', 'Kotputli-Neemrana Link, NH-48', 2, 'Shree Cement Raw Materials Div.', 120.0, 'OPERATIONAL', 27.7120, 76.2100),
            (3, 'WB-REW-01', 'Rewari Industrial Toll Weighbridge', 'Rewari Industrial Estate, Bawal Road', 3, 'Khol Mining Cooperative', 100.0, 'OPERATIONAL', 28.1820, 76.6150),
            (4, 'WB-JHJ-03', 'Khetri Gate Electronic Weighbridge', 'Singhana-Khetri Road, Jhunjhunu', 4, 'Hindustan Quarrying Partners', 100.0, 'OPERATIONAL', 28.0200, 75.7950)
        ])

        # Destinations
        cur.executemany("""
        INSERT OR IGNORE INTO destinations (id, name, destination_type, license_number, district, state, latitude, longitude, authorized_minerals, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'Bhiwadi Industrial Crushing Zone', 'CRUSHER', 'CR-RJ-BHW-088', 'Alwar', 'Rajasthan', 28.2100, 76.8600, 'Quartzite Aggregate', 'AUTHORIZED'),
            (2, 'Neemrana Cement Works Unit-2', 'CEMENT_PLANT', 'CP-RJ-NEE-014', 'Kotputli-Behror', 'Rajasthan', 27.9850, 76.3850, 'Limestone Raw Boulder', 'AUTHORIZED'),
            (3, 'Manesar Infrastructure Hub', 'CONSTRUCTION_SITE', 'INF-HR-GGM-102', 'Gurugram', 'Haryana', 28.3500, 76.9400, 'Quartzite Sand', 'AUTHORIZED'),
            (4, 'Jaipur Glass Containers Ltd', 'PROCESSING_PLANT', 'GL-RJ-JPR-045', 'Jaipur', 'Rajasthan', 26.9124, 75.7873, 'Silica Sand Grade-I', 'AUTHORIZED')
        ])

        # Checkpoints
        cur.executemany("""
        INSERT OR IGNORE INTO checkpoints (id, name, district, state, latitude, longitude, authorized_route, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 'Alwar Mining Border Checkpost', 'Alwar', 'Rajasthan', 27.6800, 76.5600, 'NH-248A / Alwar-Bhiwadi Route', 'ACTIVE'),
            (2, 'Behror Inter-State Flying Squad Post', 'Kotputli-Behror', 'Rajasthan', 27.8900, 76.2800, 'NH-48 Jaipur-Delhi Highway', 'ACTIVE'),
            (3, 'Bawal Toll Monitoring Checkpoint', 'Rewari', 'Haryana', 28.0800, 76.5900, 'NH-48 Mineral Transit Corridor', 'ACTIVE'),
            (4, 'Dharuhera Intercept Station', 'Rewari', 'Haryana', 28.2050, 76.7900, 'NH-48 Rewari-Bhiwadi Junction', 'ACTIVE')
        ])

        # Stock & Production Logs
        today_iso = datetime.now().strftime("%Y-%m-%d")
        cur.executemany("""
        INSERT OR IGNORE INTO stock_production (id, mine_id, mineral, record_date, opening_stock_mt, production_mt, dispatch_mt, closing_stock_mt, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 1, 'Quartzite', today_iso, 4200.0, 650.0, 480.0, 4370.0, 'Morning shift quarry blast output logged.'),
            (2, 2, 'Limestone', today_iso, 7800.0, 1100.0, 850.0, 8050.0, 'High-grade limestone benching extraction.'),
            (3, 3, 'Silica Sand', today_iso, 2900.0, 450.0, 380.0, 2970.0, 'Screened silica sand production lot.'),
            (4, 4, 'Copper Tailings / Quartz', today_iso, 5400.0, 800.0, 720.0, 5480.0, 'Crushed overburden dispatch.')
        ])

        # Audit Logs
        cur.executemany("""
        INSERT OR IGNORE INTO audit_logs (id, user_id, username, action, details, ip_address, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (1, 1, 'admin', 'SYSTEM_INIT', 'Spatial database engine and geofence corridors initialized successfully.', '127.0.0.1', '2026-09-10 08:30:00'),
            (2, 1, 'admin', 'QUOTA_AUDIT', 'Annual quota audit completed across 4 major state mining leaseholds.', '127.0.0.1', '2026-09-10 09:15:00'),
            (3, 2, 'officer1', 'CHECKPOINT_VERIFY', 'Vehicle HR26AB1234 verified via QR at Alwar Border Outpost.', '192.168.1.104', '2026-09-10 11:20:00'),
            (4, 2, 'officer1', 'ALERT_ELEVATION', 'Alert ALT-2026-00101 elevated to formal statutory case SMG-2026-00041.', '192.168.1.104', '2026-09-10 13:45:00'),
            (5, 3, 'operator1', 'PERMIT_DISPATCH', 'e-Rawaana SMG-2026-00125 generated for 20.0 MT Quartzite Aggregate.', '192.168.4.22', '2026-09-10 14:10:00')
        ])

        conn.commit()
        conn.close()
        try:
            self.run_auto_migrations()
        except Exception as e:
            logger.warning(f"Auto-migrations after fresh init encountered non-fatal error: {e}")
        logger.info("SQLite database initialized and seeded.")


# Singleton database instance
db = DatabaseManager()
