"""Database models and setup for Tool Availability Lookup."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config

# Ensure DB path parent exists
config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with db() as conn:
        cur = conn.cursor()
        # Users: role = 'infosec' | 'user' | 'admin' | 'auditor'
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('infosec', 'user', 'admin', 'auditor')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Verified inventory versions (Infosec uploads)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                row_count INTEGER NOT NULL
            )
        """)
        # Audit log: all uploads and scans
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                username TEXT NOT NULL,
                details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Scan cache: hash of input -> result path (for repeat queries)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scan_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_hash TEXT UNIQUE NOT NULL,
                result_excel_path TEXT,
                result_pdf_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create default users if none exist
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            from auth import hash_password
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("infosec", hash_password("infosec"), "infosec")
            )
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("user", hash_password("user"), "user")
            )
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", hash_password("admin"), "admin")
            )
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("auditor", hash_password("auditor"), "auditor")
            )

def get_latest_verified_path():
    """Return (stored_path, version) of latest verified inventory or (None, 0)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT stored_path, version FROM inventory_versions ORDER BY version DESC LIMIT 1"
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return Path(row[0]), row[1]
    return None, 0

def get_inventory_version_history(limit=20):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT version, filename, uploaded_by, uploaded_at, row_count
            FROM inventory_versions ORDER BY version DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cur.fetchall()]

def get_cached_scan(input_hash: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT result_excel_path, result_pdf_path FROM scan_cache WHERE input_hash = ?",
        (input_hash,)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {"excel": row[0], "pdf": row[1]}
    return None

def save_scan_cache(input_hash: str, result_excel_path: str, result_pdf_path: str):
    with db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO scan_cache (input_hash, result_excel_path, result_pdf_path)
            VALUES (?, ?, ?)
        """, (input_hash, result_excel_path, result_pdf_path))
