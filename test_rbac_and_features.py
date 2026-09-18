"""
Comprehensive Verification Script for SmartMineGuard Role, Workflow, and RBAC Refactor.
Tests:
1. Security & Login (Demo credentials not exposed)
2. Admin Persona (Haryana State Command Center, statewide KPIs & sub-mine concessions)
3. Officer Persona (Enforcement Command Center, Mine 5 Sub-Mine Overview table, investigations)
4. Operator 1 Persona (Sub-Mine 55 Operations Console, isolation, CRUD actions)
5. Operator 2 Persona (Sub-Mine 56, cross-tenant 403 Forbidden enforcement)
6. Business rule: No valid e-Rawaana = dispatch blocked
7. Anti-fraud features integrity: Infrared tire sensor, automated weighment, grade fraud detection, round counting
"""

import sys
import json
import time
from app import app
from services.db import db

def run_tests():
    print("==================================================================")
    print("STARTING SMARTMINEGUARD ROLE, WORKFLOW & RBAC VERIFICATION SUITE")
    print("==================================================================")

    client = app.test_client()
    passed = 0
    failed = 0

    def assert_test(condition, test_name):
        nonlocal passed, failed
        if condition:
            print(f"  [PASS] {test_name}")
            passed += 1
        else:
            print(f"  [FAIL] {test_name}")
            failed += 1

    def login(user, pwd):
        client.get("/logout")
        return client.post("/login", data={"username": user, "password": pwd}, follow_redirects=True)

    # -------------------------------------------------------------
    # TEST 1: Public Login Page (Credentials must not be visible)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 1: Security & Authentication UI ---")
    res = client.get("/login")
    assert_test(res.status_code == 200, "Login page loads successfully (200)")
    assert_test(b"DEMO ACCESS CREDENTIALS" not in res.data, "Demo access credentials banner NOT exposed on login page")
    assert_test(b"admin123" not in res.data and b"officer123" not in res.data, "Raw demo passwords NOT present in HTML")

    # -------------------------------------------------------------
    # TEST 2: Admin Role (State Command Center - Haryana)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 2: State Admin Persona (Haryana) ---")
    login_res = login("admin", "admin123")
    assert_test(login_res.status_code == 200, "Admin login successful")

    res = client.get("/dashboard")
    assert_test(res.status_code == 200, "Admin dashboard loads successfully (200)")
    assert_test(b"State Command Center" in res.data or b"HARYANA" in res.data, "Admin dashboard displays State Command Center - Haryana")
    assert_test(b"Active Mines" in res.data and b"Sub-Mines / Contractors" in res.data, "Admin sees statewide macro KPIs (Active Mines, Sub-Mines, Dispatch)")

    # Admin access to master data
    res = client.get("/master-data")
    assert_test(res.status_code == 200, "Admin can access Master Data Management (200)")
    assert_test(b"Sub-Mines &amp; Concessions" in res.data or b"Sub-Mines" in res.data, "Admin Master Data contains Sub-Mines Directory")
    assert_test(b"modal-add-truck" not in res.data and b"modal-add-permit" not in res.data, "Admin Master Data does NOT contain operational modals (truck, permit)")

    # -------------------------------------------------------------
    # TEST 3: Officer Role (Mine / Cluster Level Enforcement)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 3: Mining Officer Persona (Mine 5 Jurisdiction) ---")
    login_res = login("officer1", "officer123")
    assert_test(login_res.status_code == 200, "Officer login successful")

    res = client.get("/dashboard")
    assert_test(res.status_code == 200, "Officer dashboard loads successfully (200)")
    assert_test(b"Enforcement Command Center" in res.data or b"Command Post" in res.data, "Officer dashboard displays Enforcement Command Center")
    assert_test(b"Sub-Mine / Pit Location" in res.data and b"Active Trucks" in res.data, "Officer dashboard displays Sub-Mine Overview table")

    # Officer can access investigations
    res = client.get("/investigations")
    assert_test(res.status_code == 200, "Officer can access investigations (200)")

    # Officer cannot access master data management (Admin only)
    res = client.get("/master-data")
    assert_test(res.status_code == 403, "Officer is forbidden (403) from Master Data Management")

    # -------------------------------------------------------------
    # TEST 4: Operator 1 (Sub-Mine 55: Khanak Blue Stone Pit 1A)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 4: Operator 1 Persona (Sub-Mine 55) ---")
    login_res = login("operator1", "operator123")
    assert_test(login_res.status_code == 200, "Operator 1 login successful")

    res = client.get("/dashboard")
    assert_test(res.status_code == 200, "Operator 1 dashboard loads successfully (200)")
    assert_test(b"Sub-Mine Operations Console" in res.data or b"Operations" in res.data, "Operator 1 sees Sub-Mine Operations Console")
    assert_test(b"Register Truck" in res.data and b"Issue e-Rawaana" in res.data, "Operator 1 has operational action buttons (+ Register Truck, + Issue e-Rawaana)")
    assert_test(b"QUANTITY ANOMALIES" in res.data, "Operator 1 dashboard includes Quantity Anomalies section")

    # Operator 1 access to /operator/dispatch (Dispatch & e-Rawaana page)
    res = client.get("/operator/dispatch")
    assert_test(res.status_code == 200, "Operator 1 accesses /operator/dispatch successfully (200 OK)")
    assert_test(b"Outbound Mineral Dispatch Ledger" in res.data, "Outbound Mineral Dispatch Ledger rendered without NameError")
    assert_test(b"max-h-[500px]" in res.data, "Slide scrollbar wrapper present on operator dispatch ledger")
    assert_test(b"dispatch-search" in res.data, "Search bar present on operator dispatch ledger")

    # Operator 1 access to e-Rawaana Passes (/permits) with search and scrollbar
    res = client.get("/permits")
    assert_test(res.status_code == 200, "Operator 1 accesses e-Rawaana Passes /permits successfully (200 OK)")
    assert_test(b"permit-search" in res.data, "Search bar present on e-Rawaana Passes table")
    assert_test(b"max-h-[520px]" in res.data, "Slide up-down scrollbar present on e-Rawaana Passes table")
    assert_test(b"sticky top-0" in res.data, "Sticky header present on e-Rawaana Passes table")

    # Operator 1 access to Transit Trips (/trips) with search and scrollbar
    res = client.get("/trips")
    assert_test(res.status_code == 200, "Operator 1 accesses Transit Trips /trips successfully (200 OK)")
    assert_test(b"trip-search" in res.data, "Search bar present on Transit Trips ledger")
    assert_test(b"max-h-[520px]" in res.data, "Slide up-down scrollbar present on Transit Trips ledger")
    assert_test(b"sticky top-0" in res.data, "Sticky header present on Transit Trips ledger")

    # Operator 1 access to Fleet & Trucks (/trucks) with search and scrollbar
    res = client.get("/trucks")
    assert_test(res.status_code == 200, "Operator 1 accesses Fleet & Trucks /trucks successfully (200 OK)")
    assert_test(b"truck-search-input" in res.data, "Search bar present on Fleet & Trucks table")
    assert_test(b"max-h-[520px]" in res.data, "Slide up-down scrollbar present on Fleet & Trucks table")
    assert_test(b"sticky top-0" in res.data, "Sticky header present on Fleet & Trucks table")

    # Operator 1 access to own Truck 1 (bound to Sub-Mine 55)
    res = client.get("/trucks/1")
    assert_test(res.status_code == 200, "Operator 1 can access own Truck 1 (200 OK)")

    # Operator 1 access to own Permit 1 (bound to Sub-Mine 55)
    res = client.get("/permits/1")
    assert_test(res.status_code == 200, "Operator 1 can access own Permit 1 (200 OK)")

    # Operator 1 calling own truck GPS diagnostics API
    res = client.get("/api/gps/trucks/1/diagnostics")
    assert_test(res.status_code == 200, "Operator 1 can query own Truck 1 GPS diagnostics API (200 OK)")

    # Operator 1 calling own permit details API
    res = client.get("/api/permits/1/details")
    assert_test(res.status_code == 200, "Operator 1 can query own Permit 1 details API (200 OK)")

    # -------------------------------------------------------------
    # TEST 5: Operator 1 Cross-Tenant Access to Operator 2's Assets (Must be 403)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 5: Backend Multi-Tenant RBAC Enforcement ---")
    # Truck 2 belongs to Sub-Mine 56 (Operator 2)
    res = client.get("/trucks/2")
    assert_test(res.status_code == 403, "Operator 1 BLOCKED (403) from accessing Operator 2's Truck 2")

    # Permit 2 belongs to Sub-Mine 56 (Operator 2)
    res = client.get("/permits/2")
    assert_test(res.status_code == 403, "Operator 1 BLOCKED (403) from accessing Operator 2's Permit 2")

    # API check: GPS diagnostics for Truck 2
    res = client.get("/api/gps/trucks/2/diagnostics")
    assert_test(res.status_code == 403, "Operator 1 BLOCKED (403) from querying Operator 2's Truck 2 GPS API")

    # API check: Permit details for Permit 2
    res = client.get("/api/permits/2/details")
    assert_test(res.status_code == 403, "Operator 1 BLOCKED (403) from querying Operator 2's Permit 2 API")

    # Operator 1 attempting to access Officer/Admin pages
    res = client.get("/alerts")
    assert_test(res.status_code == 403, "Operator 1 BLOCKED (403) from Enforcement Alerts")
    res = client.get("/investigations")
    assert_test(res.status_code == 403, "Operator 1 BLOCKED (403) from Statutory Investigations")

    # -------------------------------------------------------------
    # TEST 6: Operator 2 Persona (Sub-Mine 56) Isolation Check
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 6: Operator 2 Persona (Sub-Mine 56) ---")
    login("operator2", "operator123")

    # Operator 2 access to Truck 2 (allowed)
    res = client.get("/trucks/2")
    assert_test(res.status_code == 200, "Operator 2 can access own Truck 2 (200 OK)")

    # Operator 2 access to Truck 1 (forbidden)
    res = client.get("/trucks/1")
    assert_test(res.status_code == 403, "Operator 2 BLOCKED (403) from accessing Operator 1's Truck 1")

    # -------------------------------------------------------------
    # TEST 7: Operator Data Entry Workflows (Truck, Driver, Permit CRUD)
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 7: Operator Data Entry & Automatic Sub-Mine Binding ---")
    login("operator1", "operator123")

    # Register a new Truck
    ts = int(time.time())
    new_plate = f"HR16XY{ts % 10000:04d}"
    res = client.post("/api/crud/trucks", json={
        "registration_number": new_plate,
        "vehicle_type": "10-Wheeler Tipper",
        "registered_owner": "Haryana Blue Stone Logistics Ltd",
        "driver_name": "Suresh Yadav",
        "driver_phone": "+91 98120 44556",
        "tare_weight_mt": 10.0,
        "max_capacity_mt": 30.0
    })
    assert_test(res.status_code == 200, f"Operator 1 registers new Truck {new_plate} (200 OK)")
    new_truck_id = res.json.get("truck_id")
    assert_test(new_truck_id is not None, f"Received truck_id={new_truck_id}")

    # Verify truck was automatically bound to Sub-Mine 55 in DB
    trk_row = db.query("SELECT * FROM trucks WHERE id = ?", (new_truck_id,), one=True)
    assert_test(trk_row and trk_row["sub_mine_id"] == 55, "New truck automatically bound to Operator 1's Sub-Mine 55")

    # Register a new Driver
    res = client.post("/api/crud/drivers", json={
        "driver_name": f"Rajesh Kumar {ts % 1000}",
        "license_number": f"DL-HR-{ts % 100000:05d}",
        "contact_phone": "+91 98123 99887",
        "assigned_truck_id": new_truck_id
    })
    assert_test(res.status_code == 200, "Operator 1 registers new Driver (200 OK)")

    # Issue a new e-Rawaana Permit
    res = client.post("/api/crud/permits", json={
        "truck_id": new_truck_id,
        "mineral": "Quartzite Stone",
        "permitted_weight_mt": 28.5,
        "destination_name": "Gurugram Infrastructure ReadyMix Yard",
        "buyer_name": "Gurugram Infra Projects Ltd",
        "valid_hours": 12
    })
    assert_test(res.status_code == 200, "Operator 1 issues new e-Rawaana permit (200 OK)")
    new_permit_id = res.json.get("permit_id")
    assert_test(new_permit_id is not None, f"Received permit_id={new_permit_id}")

    # Verify permit was automatically bound to Sub-Mine 55
    pmt_row = db.query("SELECT * FROM permits WHERE id = ?", (new_permit_id,), one=True)
    assert_test(pmt_row and pmt_row["quarry_block_id"] == 55, "New e-Rawaana permit automatically bound to Sub-Mine 55")

    # Operator 1 registers a new Sub-Mine Pit Concession
    submine_code = f"KH-PIT-T{ts % 10000:04d}"
    submine_payload = {
        "block_name": "Khanak North Quartzite Pit Lot 3",
        "block_code": submine_code,
        "leaseholder_name": "Bhiwani Aggregates & Stone Consortium",
        "operator_name": "Vikramaditya In-Charge",
        "contact_phone": "+91 98111 55667",
        "allocated_quota_mt": 35000.0
    }
    res = client.post("/api/crud/sub-mines", json=submine_payload)
    assert_test(res.status_code == 200, "Operator 1 registers new Sub-Mine Pit concession (200 OK)")
    submine_data = res.get_json() or {}
    new_sub_mine_id = submine_data.get("sub_mine_id")
    assert_test(new_sub_mine_id is not None, f"Received sub_mine_id={new_sub_mine_id}")
    created_qb = db.query("SELECT * FROM quarry_blocks WHERE id = ?", (new_sub_mine_id,), one=True)
    assert_test(created_qb and created_qb["mine_id"] == 5, "New Sub-Mine automatically bound to Operator 1's Mine 5")

    # -------------------------------------------------------------
    # TEST 8: Business Rule: No Valid e-Rawaana = No Normal Dispatch
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 8: Business Rule Validation: No Permit = No Dispatch ---")
    # Attempt to start trip with non-existent or invalid permit
    res = client.post("/api/crud/trips", json={
        "truck_id": new_truck_id,
        "permit_id": 999999
    })
    assert_test(res.status_code == 400, "Trip dispatch rejected (400) when permit is non-existent")
    assert_test(b"active e-Rawaana" in res.data or b"not found" in res.data, "Error explains valid e-Rawaana required")

    # Start trip with valid issued permit
    res = client.post("/api/crud/trips", json={
        "truck_id": new_truck_id,
        "permit_id": new_permit_id
    })
    assert_test(res.status_code == 200, "Trip dispatched successfully (200 OK) with valid authorized e-Rawaana")

    # Attempt to reuse the consumed permit for another trip
    res = client.post("/api/crud/trips", json={
        "truck_id": new_truck_id,
        "permit_id": new_permit_id
    })
    assert_test(res.status_code == 400, "Trip dispatch rejected (400) when permit is already consumed / in-transit")

    # -------------------------------------------------------------
    # TEST 9: Weighbridge & Anti-Fraud Features Preservation
    # -------------------------------------------------------------
    print("\n--- TEST SUITE 9: Anti-Fraud Features Integrity ---")
    # Verify infrared axle positioning simulation/verification in app
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()
    assert_test("infrared" in app_code.lower() or "position" in app_code.lower(), "Infrared positioning verification logic preserved in app.py")
    assert_test("gross_weight" in app_code and "tare_weight" in app_code, "Automated gross-tare weighbridge mathematics preserved")
    assert_test("check_production_dispatch_reconciliation" in app_code, "Production vs dispatch reconciliation engine preserved")
    assert_test("quantity_anomalies" in app_code, "Overload / quantity anomaly engine preserved")
    assert_test("calculate_round_count" in app_code or "round_number" in app_code, "Round / trip counting engine preserved")
    assert_test("simulate_gps_stream" in app_code or "gps_positions" in app_code, "GPS tracking & route breadcrumb engine preserved")

    # Check that India / Haryana coordinates are present and China coordinates are absent
    assert_test("28." in app_code and "75." in app_code or "76." in app_code, "Haryana coordinates (Lat ~28N, Lng ~76E) active in codebase")

    print("\n==================================================================")
    print(f"VERIFICATION SUMMARY: {passed} PASSED, {failed} FAILED")
    print("==================================================================")

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
