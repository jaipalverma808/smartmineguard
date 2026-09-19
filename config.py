"""
SmartMineGuard - Configuration Module
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY", "smartmineguard-secure-secret-key-2026")
    
    # Administrative & Statutory User Accounts (Read securely from .env)
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
    ADMIN_NAME = os.getenv("ADMIN_NAME", "Sanjay Verma, IAS")
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "sanjay.verma@mines.gov.in")
    ADMIN_PHONE = os.getenv("ADMIN_PHONE", "+91 98100 11223")

    OFFICER_USERNAME = os.getenv("OFFICER_USERNAME", "officer1")
    OFFICER_PASSWORD = os.getenv("OFFICER_PASSWORD", "officer123")
    OFFICER_NAME = os.getenv("OFFICER_NAME", "Inspector Rajesh K. Meena")
    OFFICER_EMAIL = os.getenv("OFFICER_EMAIL", "rajesh.meena@enforcement.gov.in")
    OFFICER_PHONE = os.getenv("OFFICER_PHONE", "+91 94140 22334")

    OPERATOR_USERNAME = os.getenv("OPERATOR_USERNAME", "operator1")
    OPERATOR_PASSWORD = os.getenv("OPERATOR_PASSWORD", "operator123")
    OPERATOR_NAME = os.getenv("OPERATOR_NAME", "Virendra Singh Rathore")
    OPERATOR_EMAIL = os.getenv("OPERATOR_EMAIL", "virendra@aravalliminerals.com")
    OPERATOR_PHONE = os.getenv("OPERATOR_PHONE", "+91 99280 33445")

    # PostgreSQL Configuration (Read strictly from .env, zero hardcoded secrets)
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "smartmineguard")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    
    # Serverless runtime detection (Vercel, AWS Lambda)
    IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

    # SQLite Fallback Path (enables zero-friction local and serverless run)
    if IS_SERVERLESS:
        SQLITE_PATH = Path("/tmp") / "smartmineguard.db"
        REPORTS_DIR = Path("/tmp") / "reports"
    else:
        SQLITE_PATH = BASE_DIR / "database" / "smartmineguard.db"
        REPORTS_DIR = BASE_DIR / "static" / "reports"

    # Session & Cookie Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1")
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME_SECONDS", 28800))  # 8 hours
    
    # Server configuration
    PORT = int(os.getenv("PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    
    # Detection Engine Thresholds (Rule-Based, Deterministic)
    WEIGHT_TOLERANCE_PERCENT = float(os.getenv("WEIGHT_TOLERANCE_PERCENT", 5.0))
    ROUTE_CORRIDOR_METERS = float(os.getenv("ROUTE_CORRIDOR_METERS", 350.0))
    GPS_BLACKOUT_SECONDS = int(os.getenv("GPS_BLACKOUT_SECONDS", 60))
    MAX_REASONABLE_SPEED_KMH = float(os.getenv("MAX_REASONABLE_SPEED_KMH", 85.0))
    
    # Risk Scoring Weights (Normalized to 0 - 100)
    WEIGHT_ANOMALY_RISK = 30
    ROUTE_DEVIATION_RISK = 20
    GPS_BLACKOUT_RISK = 20
    PERMIT_REUSE_RISK = 30
    IMPOSSIBLE_TRANSIT_RISK = 30
    PRODUCTION_MISMATCH_RISK = 30
    SUSPICIOUS_ZONE_RISK = 15

