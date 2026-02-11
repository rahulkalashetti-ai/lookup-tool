"""Audit logging for compliance (PRD §3.3, §4)."""
from database import db

def log(action: str, username: str, details: str = ""):
    with db() as conn:
        conn.execute(
            "INSERT INTO audit_log (action, username, details) VALUES (?, ?, ?)",
            (action, username, details)
        )

def get_logs(limit=200):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT action, username, details, timestamp FROM audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cur.fetchall()]
