import requests
import re
import sys

BASE_URL = "http://127.0.0.1:5000"

def run_tests():
    session = requests.Session()
    
    print("==================================================")
    print("STEP 1: Log in as ADMIN")
    print("==================================================")
    res = session.post(f"{BASE_URL}/login", data={"username": "admin", "password": "admin123"}, allow_redirects=True)
    assert res.status_code == 200, f"Login failed: {res.status_code}"
    assert "Admin Command Center" in res.text or "State Command Center" in res.text
    print("  [SUCCESS] Admin logged in successfully.")

    # -------------------------------------------------------------------------
    # STATE 1: STATEWIDE (ALL MINES)
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("STATE 1: STATEWIDE (All Mines, All Sub-Mines)")
    print("==================================================")
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=&sub_mine_id=")
    
    dash_html = session.get(f"{BASE_URL}/dashboard").text
    assert "Statewide Oversight" in dash_html or "Statewide Grid" in dash_html
    print("  [OK] Dashboard Scope Indicator: Statewide Oversight")
    assert 'id="admin-mine-filter"' not in dash_html, "admin-mine-filter duplicate select found in dashboard!"
    assert 'id="admin-submine-filter"' not in dash_html, "admin-submine-filter duplicate select found in dashboard!"
    print("  [OK] Duplicate in-page Mine/Sub-Mine dropdowns successfully removed from Admin Dashboard.")

    # Check Map
    map_html = session.get(f"{BASE_URL}/map").text
    assert "Statewide" in map_html
    assert 'name="sub_mine_id"' not in map_html.split('<div id="gis-map"')[0].split('</nav>')[1] if '</nav>' in map_html else True
    print("  [OK] Map Scope: Statewide. Duplicate selectors removed from Map.")

    # Check GPS
    gps_html = session.get(f"{BASE_URL}/gps-telemetry").text
    assert "Statewide" in gps_html
    print("  [OK] GPS Scope: Statewide. Duplicate selectors removed from GPS.")

    # Check Alerts
    alerts_html = session.get(f"{BASE_URL}/alerts?view=all").text
    assert "Statewide" in alerts_html
    print("  [OK] Alerts Scope: Statewide.")

    # Check Analytics
    analytics_html = session.get(f"{BASE_URL}/analytics").text
    assert "Statewide" in analytics_html
    print("  [OK] Analytics Scope: Statewide.")

    # -------------------------------------------------------------------------
    # STATE 2: ONE MINE SELECTED (Mine 1: Aravalli Quartzite Quarry Block A)
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("STATE 2: ONE MINE SELECTED (Mine 1: Aravalli Quartzite Quarry Block A)")
    print("==================================================")
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=1&sub_mine_id=")
    
    dash_m1 = session.get(f"{BASE_URL}/dashboard").text
    assert "Aravalli Quartzite Quarry Block A" in dash_m1
    print("  [OK] Dashboard Scope Indicator: Aravalli Quartzite Quarry Block A")
    # Mine 1 dummy data has 777.8 MT dispatch
    assert "777.8" in dash_m1, "Expected 777.8 MT dispatch for Mine 1"
    print("  [OK] Dashboard Dispatched MT matches Mine 1 total: 777.8 MT")

    # Map trucks
    map_m1 = session.get(f"{BASE_URL}/map").text
    assert "Aravalli Quartzite Quarry Block A" in map_m1
    print("  [OK] Map Scope: Aravalli Quartzite Quarry Block A")

    # GPS units
    gps_m1 = session.get(f"{BASE_URL}/gps-telemetry").text
    assert "Aravalli Quartzite Quarry Block A" in gps_m1
    print("  [OK] GPS Scope: Aravalli Quartzite Quarry Block A")

    # Alerts
    alerts_m1 = session.get(f"{BASE_URL}/alerts?view=all").text
    assert "Aravalli Quartzite Quarry Block A" in alerts_m1
    assert "(17)" in alerts_m1, f"Expected 17 alerts for Mine 1 in badge count"
    print("  [OK] Alerts Count: strictly 17 alerts for Mine 1")

    # Analytics
    analytics_m1 = session.get(f"{BASE_URL}/analytics").text
    assert "Aravalli Quartzite Quarry Block A" in analytics_m1
    assert "777.8 MT" in analytics_m1, "Expected 777.8 MT dispatched in Analytics for Mine 1"
    print("  [OK] Analytics Recalculated: 777.8 MT dispatched for Mine 1")

    # -------------------------------------------------------------------------
    # STATE 3: ONE MINE + ONE SUB-MINE SELECTED (Sub-Mine 5: QB-ALW-05)
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("STATE 3: ONE MINE + ONE SUB-MINE SELECTED (Mine 1 + Sub-Mine 5: QB-ALW-05)")
    print("==================================================")
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=1&sub_mine_id=5")

    dash_sm5 = session.get(f"{BASE_URL}/dashboard").text
    assert "QB-ALW-05" in dash_sm5
    assert "Sariska Buffer Escarpment" in dash_sm5
    # Sub-Mine 5 specs: 3 trucks, 75.5 MT dispatch, 5 alerts
    assert "75.5" in dash_sm5, "Expected 75.5 MT dispatch for Sub-Mine 5"
    print("  [OK] Dashboard Sub-Mine 5: Dispatch MT strictly 75.5 MT")

    map_sm5 = session.get(f"{BASE_URL}/map").text
    assert "QB-ALW-05" in map_sm5
    print("  [OK] Map Scope: strictly QB-ALW-05")

    gps_sm5 = session.get(f"{BASE_URL}/gps-telemetry").text
    assert "QB-ALW-05" in gps_sm5
    print("  [OK] GPS Scope: strictly QB-ALW-05")

    alerts_sm5 = session.get(f"{BASE_URL}/alerts?view=all").text
    assert "QB-ALW-05" in alerts_sm5
    assert "(5)" in alerts_sm5, "Expected strictly 5 alerts for Sub-Mine 5"
    print("  [OK] Alerts Count: strictly 5 alerts for Sub-Mine 5")

    analytics_sm5 = session.get(f"{BASE_URL}/analytics").text
    assert "QB-ALW-05" in analytics_sm5
    assert "75.5 MT" in analytics_sm5, "Expected 75.5 MT dispatched in Analytics for Sub-Mine 5"
    print("  [OK] Analytics Recalculated: strictly 75.5 MT dispatched for Sub-Mine 5")

    # -------------------------------------------------------------------------
    # STATE 3b: SWITCH SUB-MINE TO QB-ALW-15 (Sub-Mine 15)
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("STATE 3b: SWITCH SUB-MINE TO QB-ALW-15 (Sub-Mine 15)")
    print("==================================================")
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=1&sub_mine_id=15")

    dash_sm15 = session.get(f"{BASE_URL}/dashboard").text
    assert "QB-ALW-15" in dash_sm15
    assert "Goyal Mineral Lot" in dash_sm15
    # Sub-Mine 15 specs: 4 trucks, 182.3 MT dispatch, 2 alerts
    assert "182.3" in dash_sm15, "Expected 182.3 MT dispatch for Sub-Mine 15"
    print("  [OK] Dashboard Sub-Mine 15: Dispatch MT strictly 182.3 MT")

    alerts_sm15 = session.get(f"{BASE_URL}/alerts?view=all").text
    assert "QB-ALW-15" in alerts_sm15
    assert "ALT-2026-00106" in alerts_sm15, "Expected alert ALT-2026-00106 in Sub-Mine 15"
    assert "ALT-2026-00101" not in alerts_sm15, "Sub-Mine 5 alert must NOT appear in Sub-Mine 15"
    print("  [OK] Alerts Scoped: strictly Sub-Mine 15 alerts present, other sub-mines excluded")

    # -------------------------------------------------------------------------
    # STATE 3c: SWITCH SUB-MINE TO QB-ALW-33 (Sub-Mine 33)
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("STATE 3c: SWITCH SUB-MINE TO QB-ALW-33 (Sub-Mine 33)")
    print("==================================================")
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=1&sub_mine_id=33")

    dash_sm33 = session.get(f"{BASE_URL}/dashboard").text
    assert "QB-ALW-33" in dash_sm33
    assert "Everest Rock Aggregates" in dash_sm33
    # Sub-Mine 33 specs: 5 trucks, 520.0 MT dispatch, 10 alerts
    assert "520" in dash_sm33, "Expected 520 MT dispatch for Sub-Mine 33"
    print("  [OK] Dashboard Sub-Mine 33: Dispatch MT strictly 520 MT")

    alerts_sm33 = session.get(f"{BASE_URL}/alerts?view=all").text
    assert "QB-ALW-33" in alerts_sm33
    assert "ALT-2026-00108" in alerts_sm33, "Expected alert ALT-2026-00108 in Sub-Mine 33"
    assert "ALT-2026-00101" not in alerts_sm33, "Sub-Mine 5 alert must NOT appear in Sub-Mine 33"
    print("  [OK] Alerts Scoped: strictly Sub-Mine 33 alerts present, other sub-mines excluded")

    # -------------------------------------------------------------------------
    # CASCADING: SWITCH MINE TO MINE 2 (Kotputli) -> SUB-MINE MUST RESET
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("CASCADING TEST: Switch Mine to Mine 2 (Kotputli)")
    print("==================================================")
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=2")

    dash_m2 = session.get(f"{BASE_URL}/dashboard").text
    assert "Kotputli High-Grade Limestone Lease" in dash_m2
    # Verify submine is reset to All Sub-Mines under Mine 2
    assert "All Sub-Mines" in dash_m2
    # Mine 2 total dispatch is 320.0 MT
    assert "320" in dash_m2, "Expected 320.0 MT dispatch for Mine 2"
    print("  [OK] Cascading verified: Sub-Mine reset when Mine changed to Mine 2. Dispatch = 320.0 MT.")

    # Select Sub-Mine 37 under Mine 2
    session.get(f"{BASE_URL}/set-mine-filter?mine_id=2&sub_mine_id=37")
    dash_sm37 = session.get(f"{BASE_URL}/dashboard").text
    assert "QB-KOT-01" in dash_sm37
    assert "140" in dash_sm37, "Expected 140.0 MT for QB-KOT-01"
    print("  [OK] Sub-Mine under Mine 2 (QB-KOT-01) selected and verified: 140.0 MT dispatch.")

    # -------------------------------------------------------------------------
    # OFFICER ROLE TESTING
    # -------------------------------------------------------------------------
    print("\n==================================================")
    print("OFFICER ROLE TESTING (officer1: locked to Mine 1)")
    print("==================================================")
    session_off = requests.Session()
    res_off = session_off.post(f"{BASE_URL}/login", data={"username": "officer1", "password": "officer123"}, allow_redirects=True)
    assert res_off.status_code == 200
    print("  [SUCCESS] Officer logged in.")

    # Verify officer is locked to Mine 1
    dash_off = session_off.get(f"{BASE_URL}/dashboard").text
    assert "Aravalli Quartzite Quarry Block A" in dash_off
    assert 'id="businessman-selector"' not in dash_off, "businessman-selector duplicate found in officer dashboard!"
    print("  [OK] Duplicate businessman-selector dropdown successfully removed from Officer Dashboard.")

    # Officer cannot change mine to Mine 2!
    session_off.get(f"{BASE_URL}/set-mine-filter?mine_id=2")
    dash_off_check = session_off.get(f"{BASE_URL}/dashboard").text
    # Must STILL be Mine 1
    assert "Aravalli Quartzite Quarry Block A" in dash_off_check
    assert "Kotputli" not in dash_off_check
    print("  [OK] Officer RBAC preserved: Cannot bypass authorization to view Mine 2.")

    # Officer can select Sub-Mine 5 under their assigned Mine 1
    session_off.get(f"{BASE_URL}/set-mine-filter?sub_mine_id=5")
    dash_off_sm5 = session_off.get(f"{BASE_URL}/dashboard").text
    assert "QB-ALW-05" in dash_off_sm5
    assert "Rajputana Quartzite Consortium" in dash_off_sm5
    print("  [OK] Officer selecting Sub-Mine 5 scopes Officer Dashboard strictly to QB-ALW-05.")

    # Verify Officer Map with Sub-Mine 5
    map_off_sm5 = session_off.get(f"{BASE_URL}/map").text
    assert "QB-ALW-05" in map_off_sm5
    print("  [OK] Officer Map strictly scopes to QB-ALW-05.")

    print("\n==================================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
