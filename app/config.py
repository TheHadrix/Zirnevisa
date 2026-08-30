import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "app" / "static"
UPLOAD_DIR = STATIC_DIR / "uploads"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Security & Auth
SECRET_KEY = os.getenv("SECRET_KEY", "zirnovisa-super-secret-key-change-in-prod-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days
COOKIE_NAME = "zirnovisa_session"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./zirnovisa.db")

# Limits & Quotas
GUEST_DAILY_LIMIT = 3
VIP_DAILY_LIMIT = 10
MAX_SRT_CHARACTERS = 30000  # 30K characters limit per file
CLEANUP_DELAY_SECONDS = 120  # 2 minutes retention before deletion

# Default Admin Seed
DEFAULT_ADMIN_EMAIL = "admin@zirnovisa.ir"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

# SMTP Email Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))  # 465 for SSL, 587 for TLS
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
OTP_EXPIRE_MINUTES = 5
