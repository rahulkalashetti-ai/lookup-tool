"""Configuration for ToolHub."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Security
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

# Limits per PRD
MAX_INVENTORY_ROWS = 10_000
MAX_SCAN_ROWS = 5_000
SCAN_TIMEOUT_SECONDS = 120  # 2 min

# Paths
UPLOAD_FOLDER = BASE_DIR / "data" / "uploads"
VERIFIED_FOLDER = BASE_DIR / "data" / "verified"
RESULTS_FOLDER = BASE_DIR / "data" / "results"
VERSION_FOLDER = BASE_DIR / "data" / "versions"
DB_PATH = BASE_DIR / "data" / "app.db"

# Create dirs
for d in (UPLOAD_FOLDER, VERIFIED_FOLDER, RESULTS_FOLDER, VERSION_FOLDER, BASE_DIR / "data"):
    d.mkdir(parents=True, exist_ok=True)

# Excel columns (must match your sheet)
REQUIRED_COLUMNS = ["Name", "Vendor Name"]
OPTIONAL_COLUMNS = [
    "Workflow Status",
    "Requester",
    "Reason for delay",
    "Created At",
    "Request Age",
    "Application Active/In Use?",
    "Vendor Account Manager Email Address",
]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Matching thresholds for AI scan (availability decision)
MATCH_THRESHOLD_AVAILABLE = 85   # % similarity → Available
MATCH_THRESHOLD_REVIEW = 60      # % similarity → Requires review
# Below MATCH_THRESHOLD_REVIEW → Unavailable
