# SmartMineGuard — Production Deployment Security Checklist

Use this checklist before promoting SmartMineGuard to staging or production environments.

---

### Phase 1: Environment & Credentials Isolation
- [x] **No hardcoded secrets in source code**: Verified across `app.py`, `config.py`, and `services/`.
- [x] **Git Repository Hygiene**: `.env` is listed in `.gitignore`; `.env.example` provides placeholder values only.
- [x] **Strong Secret Key**: Production uses a 64+ character random string generated via `secrets.token_hex(32)`.
- [x] **Distinct Passwords**: Admin, Officer, and Operator accounts use unique, strong credentials in production.
- [x] **Database Isolation**: PostgreSQL/PostGIS credentials accessed exclusively via `DATABASE_URL` or environment variables over TLS/SSL.

### Phase 2: Role-Based Access Control & Multi-Tenancy
- [x] **Server-Side RBAC**: `@login_required(roles=[...])` enforced on all protected endpoints.
- [x] **IDOR Matrix Enforced**:
  - `validate_user_truck_access(truck_id)`
  - `validate_user_permit_access(permit_id)`
  - `validate_user_trip_access(trip_id)`
  - `validate_user_weighment_access(weighment_id)`
  - `validate_user_investigation_access(inv_id)`
- [x] **Operator Fleet Boundary**: Operators strictly confined to trucks and passes belonging to their assigned sub-mine/pit concession.
- [x] **Officer Jurisdiction Boundary**: Officers strictly locked to their assigned mine; cannot modify state-wide master infrastructure or manage portal users.

### Phase 3: Request & Transport Security
- [x] **CSRF Defense Active**: Cryptographic session tokens checked on all `POST`, `PUT`, `DELETE`, `PATCH` requests.
- [x] **Global AJAX Coverage**: Interceptor in `static/js/app.js` attaches `X-CSRF-Token` to all `fetch()` calls.
- [x] **Session Cookie Hardening**:
  - `SESSION_COOKIE_HTTPONLY = True`
  - `SESSION_COOKIE_SAMESITE = 'Lax'`
  - `SESSION_COOKIE_SECURE = True` (automatically activated in production)
- [x] **Security Headers Configured**:
  - `Content-Security-Policy`: Whitelisted for Leaflet, Tailwind, Chart.js, HTML5-QRCode.
  - `X-Frame-Options: SAMEORIGIN`: Protection against clickjacking.
  - `X-Content-Type-Options: nosniff`: Protection against MIME confusion attacks.
  - `Permissions-Policy: camera=(self)`: Allows QR barcode scanner while restricting mic/sensors.
  - `Strict-Transport-Security`: HSTS enabled for production HTTPS.

### Phase 4: Data & File Protection
- [x] **SQL Injection Defense**: 100% parameterized queries using `?` (SQLite) / `%s` (PostgreSQL).
- [x] **Path Traversal Jail**: Download routes resolve canonical file paths (`is_relative_to`) in `Config.REPORTS_DIR`.
- [x] **File Name Sanitization**: Generated downloads use `werkzeug.utils.secure_filename`.
- [x] **Zero File Upload Vulnerability**: Verified absence of unrestricted upload handlers.

### Phase 5: Error Handling & Auditing
- [x] **Traceback Masking**: Raw Python stack traces suppressed from browser in production (`DEBUG=False`).
- [x] **Custom Error Handlers**: Defined for 400, 403, 404, 429, and 500 (returning clean JSON for API calls and government-styled HTML for pages).
- [x] **Immutable Audit Trail**: Structured event logging to `audit_logs` table recording user, IP, action, entity, and timestamp.
- [x] **Destructive Deletion Safeguards**: Active or in-transit e-Rawaana permits and journeys cannot be deleted.

---

### Production Switch Command:
```bash
# Set in production environment (.env):
ENVIRONMENT=production
DEBUG=false
DEMO_MODE=false
SESSION_COOKIE_SECURE=true
```
