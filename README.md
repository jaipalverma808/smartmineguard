# SmartMineGuard
### Mining & Mineral Transport Monitoring System
**Statutory Intelligence & Enforcement Platform for Mineral Transportation Surveillance**

---

## 1. Project Overview
**SmartMineGuard** is a pure-software intelligence and enforcement platform engineered for State Mining Departments, Directorate of Mines & Geology, and law enforcement authorities. It creates an automated surveillance layer over mineral movements by integrating **e-Rawaana transit passes**, **AIS-140 GPS telemetry**, **automated weighbridge logs**, and **mine leasehold extraction quotas**.

> **Design Philosophy & Integrity:**
> SmartMineGuard is **100% deterministic software**. It strictly uses **NO AI / NO Machine Learning / NO LLMs**. Every detection is calculated via explainable mathematical and spatial algorithms, ensuring legal defensibility and administrative accountability under the Mines and Minerals (Development and Regulation) Act (MMDR).

---

## 2. Problem Statement
Illegal mining and unpermitted mineral transit cause vast revenue loss, environmental degradation, and infrastructure damage across major mining corridors. Key vulnerabilities include:
- **Overloading & Axle Damage:** Tipper trucks carrying excess payload beyond permitted limits.
- **Corridor Deviation:** Vehicles departing from authorized highway corridors into illegal riverbed extraction zones or private crushers.
- **GPS Blackouts & Jamming:** Deliberate tampering or signal disruption near eco-sensitive zones.
- **Permit Recycling / Short-Looping:** Presenting already consumed e-Rawaana passes for multiple unrecorded trips.
- **Leasehold Quota Mismatches:** Mines extracting and dispatching tonnage far in excess of statutory environmental clearances.

---

## 3. The SmartMineGuard Solution
SmartMineGuard connects the entire transportation chain into a unified audit trail:
$$\text{e-Rawaana Permit} \longrightarrow \text{Truck RFID} \longrightarrow \text{Live GPS} \longrightarrow \text{Weighbridge} \longrightarrow \text{Detection Engine} \longrightarrow \text{Risk Score} \longrightarrow \text{Alert} \longrightarrow \text{Field Verification} \longrightarrow \text{Evidence Dossier}$$

---

## 4. Key Features
1. **Role-Based Authentication:** Distinct portal profiles for Admin, Field Enforcement Officers, and Lease Operators with password hashing (scrypt).
2. **Operational Dashboard:** Real database-driven metrics (Active Trucks, Active Permits, Pending Alerts, Critical Cases, Anomaly Breakdown).
3. **Live GIS Monitoring (Leaflet.js):** Real-time spatial map rendering mine leases, legal transit corridor buffers, restricted riverbed geofences, and color-coded vehicle markers.
4. **Deterministic Detection Engine:** Readable Python algorithms evaluating 6 primary statutory violation rules.
5. **Explainable Risk Scoring (0–100):** Itemized breakdown of contributing penalty points with clear risk bands (Low, Medium, High, Critical).
6. **Real-time GPS Simulation & Telemetry:** Background simulator moving virtual fleet trucks along realistic Indian mining corridors with Flask-SocketIO streaming.
7. **Roadside Officer Verification (PWA/Mobile-Ready):** Roadside checkpoint interface with camera QR scanner and instant permit validity reconciliation.
8. **Statutory Case Management:** Direct elevation of surveillance alerts into formal inquiry files with timeline evidence logs and officer notes.
9. **Official Evidence Dossier PDF (ReportLab):** Court-ready administrative dossier containing vehicle profile, weighment comparison, statutory violation breakdown, and officer signature blocks.
10. **Dual-Mode Database Engine:** Native PostgreSQL + PostGIS support with automated zero-setup SQLite spatial fallback for seamless out-of-the-box demonstration.

---

## 5. Technology Stack
- **Backend:** Python 3.13, Flask 3.0, Flask-SocketIO 5.6
- **Database:** PostgreSQL + PostGIS (`database/schema.sql`, `database/seed.sql`) / SQLite Spatial Emulation (`services/db.py`)
- **Frontend:** HTML5, Jinja2, Vanilla CSS (`static/css/style.css`), Tailwind CSS (CDN), Vanilla JavaScript (ES6)
- **GIS & Mapping:** Leaflet.js 1.9
- **Data Visualization:** Chart.js 4.4
- **PDF Generation:** ReportLab 5.0
- **QR Code Scanning:** Html5-QRCode & QRCode.js

---

## 6. Directory Structure
```
smartmineguard/
│
├── app.py                      # Main Flask application, routes, APIs, and SocketIO server
├── config.py                   # System configuration, detection thresholds, and risk weights
├── requirements.txt            # Python dependencies (Flask, Flask-SocketIO, reportlab, etc.)
├── .env.example                # Sample environment variables
├── README.md                   # Complete documentation and SIH demo walkthrough
│
├── database/
│   ├── schema.sql              # PostgreSQL + PostGIS schema definitions
│   └── seed.sql                # Synthetic realistic Indian mining seed dataset
│
├── services/
│   ├── db.py                   # Database abstraction layer (PostgreSQL/PostGIS + SQLite fallback)
│   ├── detection.py            # Deterministic rule-based detection engine (6 statutory rules)
│   ├── risk_engine.py          # Explainable 0-100 normalized risk calculation
│   ├── gps_simulator.py        # Background multi-truck GPS movement simulator
│   └── report_generator.py     # Official administrative Evidence Dossier PDF builder
│
├── templates/
│   ├── base.html               # Official administrative portal layout with top navigation
│   ├── login.html              # Government-style secure officer login
│   ├── dashboard.html          # Operational metrics, live risk overview, quick alerts
│   ├── map.html                # Fullscreen Leaflet GIS monitoring map with corridors & inspector
│   ├── trucks.html             # Searchable fleet directory and individual audit ledger
│   ├── permits.html            # e-Rawaana permit tracking with interactive QR modal
│   ├── trips.html              # Transit logs and weighbridge variance reconciliation
│   ├── alerts.html             # Alert Center with acknowledge and elevation controls
│   ├── investigations.html     # Formal statutory inquiry files and officer note logs
│   ├── analytics.html          # Chart.js compliance and production-vs-dispatch charts
│   ├── reports.html            # Dossier query and PDF download hub
│   └── officer.html            # Roadside camera QR scanner and instant verification
│
├── static/
│   ├── css/
│   │   └── style.css           # Government portal styling, table density, status badges
│   └── js/
│       ├── app.js              # Global utilities, toast notifications, SocketIO listeners
│       ├── dashboard.js        # Dashboard real-time counters & Chart.js widgets
│       ├── map.js              # Leaflet spatial engine (pins, corridors, drawer)
│       ├── trucks.js           # Client-side instant fleet search
│       ├── alerts.js           # Alert lifecycle actions (acknowledge, investigate)
│       └── officer.js          # Roadside camera QR scanner and field decision handler
│
└── tests/
    └── test_detection.py       # Unit tests verifying all detection rules & risk normalization
```

---

## 7. Installation & Quick Start

### Step 1: Clone or Navigate to Directory
```powershell
cd "c:\Users\vc\OneDrive\Desktop\SID 2 antigravtiy new with simple code"
```

### Step 2: Install Python Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Run the Application
```powershell
python app.py
```
Open your browser and navigate to:
```
http://localhost:5000
```

---

## 8. Database Setup (PostgreSQL + PostGIS vs Standalone Mode)

### Production PostgreSQL + PostGIS Mode:
1. Ensure PostgreSQL and PostGIS are installed and running.
2. Create the database:
   ```sql
   CREATE DATABASE smartmineguard;
   ```
3. Set your connection string in `.env` or environment variables:
   ```env
   DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/smartmineguard
   ```
4. Initialize and seed:
   ```bash
   psql -d smartmineguard -f database/schema.sql
   psql -d smartmineguard -f database/seed.sql
   ```

### Zero-Friction Standalone Demo Mode (Default):
SmartMineGuard includes an embedded spatial engine in `services/db.py`. If PostgreSQL is not active on your machine, the system **automatically initializes an SQLite database** (`database/smartmineguard.db`) and executes spatial haversine / cross-track corridor calculations natively in Python. **No database installation is required for evaluation!**

---

## 9. Demo Access Credentials
| Role | Username | Password | Department / Authority |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | Directorate of Mines & Geology HQ |
| **Enforcement Officer** | `officer1` | `officer123` | Mining Enforcement Squad Zone 4 |
| **Mine Operator** | `operator1` | `operator123` | Aravalli Quartzite Quarry Consortium |

---

## 10. SIH Demonstration Workflow (Step-by-Step)

Judges and evaluators can experience the full statutory enforcement lifecycle in under 3 minutes:

1. **Sign In:** Navigate to `http://localhost:5000/login` and log in as `officer1` / `officer123`.
2. **Dashboard Overview:** Notice the live operational metrics loaded directly from the database.
3. **Open GIS Monitoring:** Click **Live GIS Map** in the navigation bar.
4. **Locate Target Vehicle:** Click **"Locate Target Truck (HR26AB1234)"**.
   - Notice vehicle details: Permitted 20.0 MT Quartzite under e-Rawaana `SMG-2026-00125`.
5. **Trigger SIH Demo Scenario:** In the top navigation bar, click the **"SIH Demo Scenarios"** dropdown:
   - Click **"1. Overweight (+11 MT Overload)"**: Weighbridge logs 31.0 MT against 20.0 MT permitted (+55% overload). Detection flags `WEIGHT_ANOMALY` (+30 Risk).
   - Click **"2. Route Corridor Deviation"**: Vehicle departs from legal NH-48 corridor into rural bypass. Detection flags `ROUTE_DEVIATION` (+20 Risk).
   - Click **"3. GPS Blackout"**: Telemetry lost near Sabi Riverbed Restricted Zone. Detection flags `GPS_BLACKOUT` (+20 Risk).
6. **Observe Real-Time Escalation:**
   - Notice the risk score jumps to **92/100 (CRITICAL)** with exact itemized reasons.
   - Real-time toast alert pops up across connected sessions.
7. **Elevate to Investigation:**
   - Click **Alerts Center** &rarr; locate Alert `ALT-2026-00101` &rarr; click **"Elevate to Case"**.
   - The system automatically registers case file `SMG-2026-00041` and compiles the initial dossier.
8. **Download Court-Admissible Evidence Dossier:**
   - Click **"Download Official Evidence Dossier (PDF)"**.
   - View the generated PDF featuring official typography, vehicle profile, weighment variance audit, QR code, and officer signature blocks.
9. **Test Roadside Field QR Verification:**
   - Click **Officer QR Verify** in the navigation bar.
   - Click **"Test Overload Truck (SMG-2026-00125)"** or **"Test Reused/Consumed (TRP-2026-00088)"**.
   - Instant statutory audit displays clear red warning: *"PERMIT REUSE WARNING: This e-Rawaana has already been consumed."*

---

## 11. Deterministic Detection Rules

SmartMineGuard implements 6 explainable Python algorithms:

| Rule Name | Detection Logic | Primary Threshold |
| :--- | :--- | :--- |
| **Weight Anomaly** | `actual_net > permitted_weight * (1 + tolerance)` or `actual > axle_cap` | > 5% tolerance |
| **Route Corridor Deviation** | Perpendicular cross-track distance to polyline axis | > 350 meters |
| **GPS Blackout** | Time since last AIS-140 ping while trip status is in transit | > 60 seconds (escalates near sensitive zones) |
| **Permit Reuse** | Scan of consumed or expired permit, or vehicle mismatch | `status in ('CONSUMED', 'EXPIRED')` |
| **Impossible Transit** | `distance_km / elapsed_hours > max_speed` | > 85 km/h avg |
| **Production Mismatch** | `current_dispatch_mt > authorized_annual_quota_mt` | Extraction quota exceeded |

---

## 12. Automated Test Suite
To execute the automated unit test suite:
```powershell
python -m unittest discover -s tests -v
```
**Test Results:**
```
test_gps_blackout_healthy ... ok
test_gps_blackout_near_sensitive_zone ... ok
test_impossible_transit ... ok
test_production_dispatch_mismatch ... ok
test_risk_score_normalization_and_breakdown ... ok
test_route_corridor_deviation ... ok
test_route_corridor_within_buffer ... ok
test_weight_anomaly_normal ... ok
test_weight_anomaly_overload ... ok

Ran 9 tests in 0.010s — OK
```

---

## 13. Regulatory Compliance Notice
SmartMineGuard is an administrative decision-support platform designed to assist enforcement authorities. The system flags "Suspicious Activity" and "Potential Violations" based on statutory rules. Formal compounding notices and vehicle impoundments are executed under Section 21 of the MMDR Act following physical inspection by authorized officers.