import sys
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app, socketio
import threading

ASSETS_DIR = BASE_DIR / "static" / "manual_assets"
PORT = 5056
BASE_URL = f"http://127.0.0.1:{PORT}"

def run_server():
    socketio.run(app, host="127.0.0.1", port=PORT, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)

threading.Thread(target=run_server, daemon=True).start()
time.sleep(3.0)

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1440,920")
opts.add_argument("--disable-gpu")
driver = webdriver.Edge(options=opts)

def login(user, pw):
    driver.get(f"{BASE_URL}/login")
    time.sleep(1)
    driver.find_element(By.NAME, "username").send_keys(user)
    driver.find_element(By.NAME, "password").send_keys(pw)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(1.5)

try:
    login("admin", "admin123")
    
    # 06 Route reconstruction
    driver.get(f"{BASE_URL}/map")
    time.sleep(3.5)
    items = driver.find_elements(By.CSS_SELECTOR, ".truck-list-item, [onclick*='focusTruck']")
    if items:
        items[0].click()
        time.sleep(2.5)
        driver.save_screenshot(str(ASSETS_DIR / "06_route_reconstruction.png"))
        print("[SUCCESS] 06_route_reconstruction.png saved")

    # 18 Modal Add Permit
    driver.get(f"{BASE_URL}/admin/data")
    time.sleep(2.0)
    driver.execute_script("openModal('modal-add-permit');")
    time.sleep(1.5)
    driver.save_screenshot(str(ASSETS_DIR / "18_modal_add_permit.png"))
    print("[SUCCESS] 18_modal_add_permit.png saved")

finally:
    driver.quit()
