"""Authentication and role-based access for Tool Availability Lookup."""
import hashlib
import functools
from flask import session, redirect, url_for, request

from database import get_connection

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{password}{'tool-lookup-salt'}".encode()).hexdigest()

def verify_user(username: str, password: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, role FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password))
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "role": row[2]}
    return None

def login_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return wrapped

def role_required(*allowed_roles):
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.url))
            if session.get("role") not in allowed_roles:
                return "Forbidden: insufficient role", 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

def current_user():
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role"),
    }
