"""
SmartMineGuard Manual Screenshot Capture Utility
Launches a test server instance and uses Selenium Headless Edge to capture
high-resolution screenshots of all real UI pages and states for the user manual.
"""
import os
import sys
import time
import threading
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

# Ensure base directory in path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app, socketio

sys.stdout.reconfigure(line_buffering=True)

ASSETS_DIR = BASE_DIR / "static" / "manual_assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

PORT = 5055
BASE_URL = f"http://127.0.0.1:{PORT}"

def run_server():
    socketio.run(app, host="127.0.0.1", port=PORT, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

def start_background_server():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(3.0)
    print(f"[*] Server started at {BASE_URL}")

def setup_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1440,920")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--log-level=3")
    driver = webdriver.Edge(options=opts)
    driver.set_window_size(1440, 920)
    return driver

def login_as(driver, username, password):
    driver.get(f"{BASE_URL}/login")
    time.sleep(1)
    user_input = driver.find_element(By.NAME, "username")
    pass_input = driver.find_element(By.NAME, "password")
    user_input.clear()
    user_input.send_keys(username)
    pass_input.clear()
    pass_input.send_keys(password)
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    submit_btn.click()
    time.sleep(1.5)

def capture_all():
    start_background_server()
    driver = setup_driver()

    try:
        print("[*] Capturing Public Portal...")
        driver.get(f"{BASE_URL}/")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "01_public_landing.png"))

        # Select a mine in public portal to show mine details
        try:
            sel = driver.find_element(By.ID, "public_mine_selector")
            for opt in sel.find_elements(By.TAG_NAME, "option"):
                if opt.get_attribute("value"):
                    opt.click()
                    time.sleep(1.5)
                    break
            driver.save_screenshot(str(ASSETS_DIR / "02_public_mine_selected.png"))
        except Exception as e:
            print(f"Warning on mine selection: {e}")

        # Capture Login Screen
        print("[*] Capturing Login Screen...")
        driver.get(f"{BASE_URL}/login")
        time.sleep(1)
        driver.save_screenshot(str(ASSETS_DIR / "03_login_screen.png"))

        # Log in as Admin
        print("[*] Capturing Admin Views...")
        login_as(driver, "admin", "admin123")
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "04_admin_dashboard.png"))

        # Capture Live GIS Map
        print("[*] Capturing Live GIS Map...")
        driver.get(f"{BASE_URL}/map")
        time.sleep(3)
        driver.save_screenshot(str(ASSETS_DIR / "05_live_gis_map.png"))

        # Click truck in side panel to show route reconstruction
        try:
            truck_items = driver.find_elements(By.CSS_SELECTOR, ".truck-item, [onclick*='selectTruck']")
            if truck_items:
                truck_items[0].click()
                time.sleep(2.5)
                driver.save_screenshot(str(ASSETS_DIR / "06_route_reconstruction.png"))
        except Exception as e:
            print(f"Warning on map truck select: {e}")

        # Trucks Fleet
        print("[*] Capturing Trucks Fleet & Detail...")
        driver.get(f"{BASE_URL}/trucks")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "07_trucks_fleet.png"))

        driver.get(f"{BASE_URL}/trucks/1")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "08_truck_detail.png"))

        # Permits
        print("[*] Capturing Permits...")
        driver.get(f"{BASE_URL}/permits")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "09_permits_ledger.png"))

        # Click View QR Modal
        try:
            qr_btn = driver.find_element(By.CSS_SELECTOR, "[onclick*='showQRModal']")
            if qr_btn:
                qr_btn.click()
                time.sleep(1.5)
                driver.save_screenshot(str(ASSETS_DIR / "10_permit_qr_modal.png"))
                # Close modal
                driver.find_element(By.CSS_SELECTOR, "[onclick*='hideQRModal']").click()
                time.sleep(0.5)
        except Exception as e:
            print(f"Warning on QR modal: {e}")

        # Transit Trips
        print("[*] Capturing Transit Trips...")
        driver.get(f"{BASE_URL}/trips")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "11_transit_trips.png"))

        # Alerts Center
        print("[*] Capturing Alerts Center...")
        driver.get(f"{BASE_URL}/alerts")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "12_alerts_center.png"))

        # Investigations
        print("[*] Capturing Investigations...")
        driver.get(f"{BASE_URL}/investigations")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "13_investigations.png"))

        # Officer QR Verification
        print("[*] Capturing Officer QR Verification...")
        driver.get(f"{BASE_URL}/verify-qr")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "14_qr_verification.png"))

        # Analytics
        print("[*] Capturing Analytics...")
        driver.get(f"{BASE_URL}/analytics")
        time.sleep(2.5)
        driver.save_screenshot(str(ASSETS_DIR / "15_analytics_dashboard.png"))

        # Reports & Dossiers
        print("[*] Capturing Reports & Dossiers...")
        driver.get(f"{BASE_URL}/reports")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "16_reports_dossiers.png"))

        # Master Data Console
        print("[*] Capturing Master Data Management...")
        driver.get(f"{BASE_URL}/admin/data")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "17_master_data_console.png"))

        # Open Issue Permit Modal in Master Data
        try:
            issue_permit_btn = driver.find_element(By.CSS_SELECTOR, "[onclick*='modal-add-permit']")
            if issue_permit_btn:
                issue_permit_btn.click()
                time.sleep(1.5)
                driver.save_screenshot(str(ASSETS_DIR / "18_modal_add_permit.png"))
                driver.find_element(By.CSS_SELECTOR, "#modal-add-permit button[type='button']").click()
                time.sleep(0.5)
        except Exception as e:
            print(f"Warning on permit modal: {e}")

        # User Management
        print("[*] Capturing User Management...")
        driver.get(f"{BASE_URL}/admin/users")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "19_user_management.png"))

        # Officer Dashboard
        print("[*] Capturing Officer Dashboard...")
        login_as(driver, "officer1", "officer123")
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "20_officer_dashboard.png"))

        # Operator Dashboard
        print("[*] Capturing Operator Dashboard...")
        login_as(driver, "operator1", "operator123")
        driver.get(f"{BASE_URL}/dashboard")
        time.sleep(2)
        driver.save_screenshot(str(ASSETS_DIR / "21_operator_dashboard.png"))

        print("[✓] All 21 interface screenshots captured successfully!")

    finally:
        driver.quit()
        print("[*] Driver closed.")

if __name__ == "__main__":
    capture_all()
