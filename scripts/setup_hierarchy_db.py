"""
Setup and configure the real-world operational hierarchy in SQLite:
State (Haryana) -> Mine (HSIIDC Khanak Stone Mines) -> Sub-Mines (Contractors A1, A2...)
-> Operator A (operator1) & Operator B (operator2)
-> Trucks, Drivers, Permits, Trips, Weighments
"""
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DB_PATH = Path(__file__).resolve().parent.parent / "database" / "smartmineguard.db"

def setup_hierarchy():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 1. Add assigned_sub_mine_id to users if not present
    user_cols = [col[1] for col in c.execute("PRAGMA table_info(users)").fetchall()]
    if "assigned_sub_mine_id" not in user_cols:
        print("[*] Adding assigned_sub_mine_id to users table...")
        c.execute("ALTER TABLE users ADD COLUMN assigned_sub_mine_id INT REFERENCES quarry_blocks(id)")

    # 2. Add sub_mine_id to trucks if not present
    truck_cols = [col[1] for col in c.execute("PRAGMA table_info(trucks)").fetchall()]
    if "sub_mine_id" not in truck_cols:
        print("[*] Adding sub_mine_id to trucks table...")
        c.execute("ALTER TABLE trucks ADD COLUMN sub_mine_id INT REFERENCES quarry_blocks(id)")

    # 3. Add sub_mine_id to drivers if not present
    driver_cols = [col[1] for col in c.execute("PRAGMA table_info(drivers)").fetchall()]
    if "sub_mine_id" not in driver_cols:
        print("[*] Adding sub_mine_id to drivers table...")
        c.execute("ALTER TABLE drivers ADD COLUMN sub_mine_id INT REFERENCES quarry_blocks(id)")

    conn.commit()

    # 4. Check Haryana Mines in database
    # Mine 5 is HSIIDC Khanak Stone Mines (Bhiwani, Haryana)
    # Mine 3 is Khol Silica Sand & Stone Pit (Rewari, Haryana)
    # Let's ensure Sub-Mines exist under Mine 5
    khanak_submines = c.execute("SELECT * FROM quarry_blocks WHERE mine_id = 5").fetchall()
    if not khanak_submines:
        print("[*] Seeding Sub-Mines / Contractors under HSIIDC Khanak Stone Mines (Mine 5)...")
        c.execute("""
            INSERT INTO quarry_blocks (mine_id, block_code, block_name, leaseholder_name, operator_name, contact_phone, allocated_quota_mt, dispatched_mt, active_trucks_count, status)
            VALUES 
            (5, 'QB-HR-BHW-01', 'Khanak Blue Stone Pit 1A', 'Sharma Stone Aggregates Ltd.', 'Virendra Singh (Operator A)', '+91 98120 11223', 85000.0, 42350.0, 4, 'OPERATIONAL'),
            (5, 'QB-HR-BHW-02', 'Khanak Commercial Clinker Lot B', 'Apex Mining Transporters', 'Rajendra Kumar (Operator B)', '+91 98120 44556', 75000.0, 38100.0, 3, 'OPERATIONAL'),
            (5, 'QB-HR-BHW-03', 'Khanak Western Aggregate Highwall', 'Haryana Infrastructure Partners', 'Sukhbir Singh', '+91 98120 77889', 60000.0, 29400.0, 2, 'OPERATIONAL'),
            (5, 'QB-HR-BHW-04', 'Khanak Southern Road Metal Quarry', 'Mewat Aggregates Consortium', 'Kailash Chand', '+91 98120 99001', 30000.0, 14200.0, 2, 'OPERATIONAL')
        """)
        conn.commit()

    # Fetch submine IDs under Mine 5
    submines_5 = c.execute("SELECT id, block_code, block_name FROM quarry_blocks WHERE mine_id = 5 ORDER BY id ASC").fetchall()
    sub_mine_a1_id = submines_5[0]["id"]
    sub_mine_a2_id = submines_5[1]["id"]
    print(f"[*] Sub-Mine A1 ID: {sub_mine_a1_id} ({submines_5[0]['block_name']})")
    print(f"[*] Sub-Mine A2 ID: {sub_mine_a2_id} ({submines_5[1]['block_name']})")

    # 5. Ensure operator1 is bound to Sub-Mine A1 under Mine 5
    c.execute("""
        UPDATE users 
        SET assigned_mine_id = 5, assigned_sub_mine_id = ?, department = 'Khanak Blue Stone Pit 1A • Sharma Stone Aggregates'
        WHERE username = 'operator1'
    """, (sub_mine_a1_id,))

    # 6. Ensure operator2 exists and is bound to Sub-Mine A2 under Mine 5
    op2 = c.execute("SELECT * FROM users WHERE username = 'operator2'").fetchone()
    pw_hash = generate_password_hash("operator123")
    if not op2:
        print("[*] Creating user operator2 for Sub-Mine A2...")
        c.execute("""
            INSERT INTO users (username, password_hash, full_name, role, department, badge_number, email, phone, is_active, assigned_mine_id, assigned_sub_mine_id)
            VALUES ('operator2', ?, 'Rajendra Kumar (Operator B)', 'OPERATOR', 'Khanak Commercial Clinker Lot B • Apex Mining Transporters', 'OP-HR-BHW-02', 'operator2@hsiidc-mines.gov.in', '+91 98120 44556', 1, 5, ?)
        """, (pw_hash, sub_mine_a2_id))
    else:
        c.execute("""
            UPDATE users 
            SET assigned_mine_id = 5, assigned_sub_mine_id = ?, department = 'Khanak Commercial Clinker Lot B • Apex Mining Transporters'
            WHERE username = 'operator2'
        """, (sub_mine_a2_id,))

    # 7. Ensure officer1 is assigned to Mine 5 (HSIIDC Khanak Stone Mines)
    c.execute("""
        UPDATE users
        SET assigned_mine_id = 5, department = 'Mining Enforcement Squad Zone 4 (Bhiwani & Hisar Belt)'
        WHERE username = 'officer1'
    """)

    # 8. Ensure admin has assigned_mine_id = 5 as default view but statewide access
    c.execute("""
        UPDATE users
        SET assigned_mine_id = 5, department = 'Directorate of Mines & Geology, Haryana (State HQ)'
        WHERE username = 'admin'
    """)

    # 9. Assign trucks to Sub-Mine A1 and Sub-Mine A2
    # Truck HR26AB1234 (ID 1) -> Sub-Mine A1, Mine 5
    # Truck HR46D2823 (ID 29) -> Sub-Mine A1, Mine 5
    # Truck HR38EF9012 (ID 4) -> Sub-Mine A1, Mine 5
    # Truck RJ14GA5521 (ID 2) -> Sub-Mine A2, Mine 5
    # Truck UP16BT4055 (ID 7) -> Sub-Mine A2, Mine 5
    # Truck RJ14ZZ4690 (ID 66) -> Sub-Mine A2, Mine 5
    c.execute("UPDATE trucks SET assigned_mine_id = 5, sub_mine_id = ? WHERE id IN (1, 29, 4, 3, 5)", (sub_mine_a1_id,))
    c.execute("UPDATE trucks SET assigned_mine_id = 5, sub_mine_id = ? WHERE id IN (2, 7, 66, 67, 68)", (sub_mine_a2_id,))

    # 10. Update permits to link to sub_mine_id / quarry_block_id
    c.execute("UPDATE permits SET quarry_block_id = ?, mine_id = 5 WHERE truck_id IN (1, 29, 4, 3, 5)", (sub_mine_a1_id,))
    c.execute("UPDATE permits SET quarry_block_id = ?, mine_id = 5 WHERE truck_id IN (2, 7, 66, 67, 68)", (sub_mine_a2_id,))

    # 11. Assign drivers to sub_mines
    c.execute("UPDATE drivers SET sub_mine_id = ? WHERE assigned_truck_id IN (1, 29, 4, 3, 5)", (sub_mine_a1_id,))
    c.execute("UPDATE drivers SET sub_mine_id = ? WHERE assigned_truck_id IN (2, 7, 66, 67, 68)", (sub_mine_a2_id,))

    # 12. Also link trips to mine_id = 5 where truck is at mine 5
    c.execute("UPDATE trips SET mine_id = 5 WHERE truck_id IN (1, 29, 4, 3, 5, 2, 7, 66, 67, 68)")

    conn.commit()
    conn.close()
    print("[OK] Operational hierarchy database configuration completed successfully!")

if __name__ == "__main__":
    setup_hierarchy()
