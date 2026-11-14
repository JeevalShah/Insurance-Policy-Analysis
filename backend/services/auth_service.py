"""
auth_service.py

Zero-dependency, cryptographically secure authentication and user management
service for the Sentra Engine.
Uses standard library sqlite3, hashlib (PBKDF2), hmac, and secrets.
"""

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from functools import wraps
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Configurable secret key from environment
SECRET_KEY = os.environ.get("SENTRA_SECRET_KEY", "sentra-engine-prod-secret-key-change-in-env-2026")
TOKEN_EXPIRATION_SECONDS = int(os.environ.get("SENTRA_TOKEN_TTL", 86400 * 7))  # 7 days
PBKDF2_ITERATIONS = 100_000


class AuthService:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "auth.db")
        else:
            self.db_path = db_path
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    token TEXT PRIMARY KEY,
                    revoked_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            conn.commit()

    def _hash_password(self, password: str, salt_bytes: bytes) -> str:
        derived = hashlib.pbkdf2_hmac(
            hash_name="sha256",
            password=password.encode("utf-8"),
            salt=salt_bytes,
            iterations=PBKDF2_ITERATIONS,
            dklen=32
        )
        return derived.hex()

    def generate_token(self, user_id: str) -> str:
        now = int(time.time())
        expires_at = now + TOKEN_EXPIRATION_SECONDS
        nonce = secrets.token_hex(8)
        payload = f"{user_id}:{expires_at}:{nonce}"
        sig = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        raw_token = f"{payload}:{sig}"
        return base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")

    def verify_token(self, token_str: str) -> Optional[Dict[str, Any]]:
        if not token_str or not isinstance(token_str, str):
            return None

        # Check if revoked
        try:
            with self._connection() as conn:
                cur = conn.execute("SELECT 1 FROM revoked_tokens WHERE token = ?", (token_str,))
                if cur.fetchone():
                    return None
        except Exception as e:
            logger.error(f"Error checking revoked tokens: {e}")
            return None

        try:
            raw = base64.urlsafe_b64decode(token_str.encode("utf-8")).decode("utf-8")
            parts = raw.split(":")
            if len(parts) != 4:
                return None
            user_id, expires_at_str, nonce, signature = parts
            expires_at = int(expires_at_str)

            if time.time() > expires_at:
                return None

            payload = f"{user_id}:{expires_at}:{nonce}"
            expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected_sig):
                return None

            user = self.get_user_by_id(user_id)
            return user
        except Exception:
            return None

    def revoke_token(self, token_str: str) -> bool:
        try:
            with self._connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO revoked_tokens (token, revoked_at) VALUES (?, ?)",
                    (token_str, time.time())
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to revoke token: {e}")
            return False

    def signup(self, username: str, email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        username = (username or "").strip()
        email = (email or "").strip().lower()

        if len(username) < 3:
            return None, None, "Username must be at least 3 characters."
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return None, None, "Invalid email address format."
        if len(password) < 6:
            return None, None, "Password must be at least 6 characters."

        salt_bytes = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt_bytes)
        salt_hex = salt_bytes.hex()
        user_id = f"user_{secrets.token_hex(12)}"
        now = time.time()

        try:
            with self._connection() as conn:
                conn.execute(
                    "INSERT INTO users (user_id, username, email, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username, email, password_hash, salt_hex, now)
                )
                conn.commit()
        except sqlite3.IntegrityError as e:
            err_str = str(e).lower()
            if "username" in err_str:
                return None, None, "Username is already registered."
            if "email" in err_str:
                return None, None, "Email is already registered."
            return None, None, "Username or email is already registered."

        user = {
            "user_id": user_id,
            "username": username,
            "email": email,
            "created_at": now
        }
        token = self.generate_token(user_id)
        return user, token, None

    def login(self, username_or_email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        ident = (username_or_email or "").strip().lower()
        if not ident or not password:
            return None, None, "Username/email and password are required."

        with self._connection() as conn:
            cur = conn.execute(
                "SELECT user_id, username, email, password_hash, salt, created_at FROM users WHERE lower(username) = ? OR lower(email) = ?",
                (ident, ident)
            )
            row = cur.fetchone()

        if not row:
            return None, None, "Invalid credentials."

        salt_bytes = bytes.fromhex(row["salt"])
        computed_hash = self._hash_password(password, salt_bytes)
        if not hmac.compare_digest(computed_hash, row["password_hash"]):
            return None, None, "Invalid credentials."

        user = {
            "user_id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "created_at": row["created_at"]
        }
        token = self.generate_token(row["user_id"])
        return user, token, None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT user_id, username, email, created_at FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "created_at": row["created_at"]
        }


# Global auth service instance
auth_service = AuthService()


def get_token_from_request() -> Optional[str]:
    """Extracts bearer token from Authorization header or fallback HttpOnly cookie."""
    try:
        from flask import request
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        cookie_token = request.cookies.get("sentra_token")
        if cookie_token:
            return cookie_token.strip()
    except Exception:
        pass
    return None


def require_auth(f):
    """
    Decorator for Flask routes requiring authenticated user.
    Populates g.current_user and g.user_id or returns 401.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import jsonify, g
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Authentication required. Please log in."}), 401

        user = auth_service.verify_token(token)
        if not user:
            return jsonify({"error": "Invalid or expired token. Please log in again."}), 401

        g.current_user = user
        g.user_id = user["user_id"]
        g.token = token
        return f(*args, **kwargs)
    return decorated_function


def optional_auth(f):
    """
    Decorator for Flask routes that support both authenticated and anonymous callers.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import g
        token = get_token_from_request()
        g.current_user = None
        g.user_id = None
        g.token = None
        if token:
            user = auth_service.verify_token(token)
            if user:
                g.current_user = user
                g.user_id = user["user_id"]
                g.token = token
        return f(*args, **kwargs)
    return decorated_function
