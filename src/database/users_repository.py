"""End-user accounts for the Kayfa chat (signup / login).

A `users` collection in MongoDB Atlas. Passwords are stored as a per-user
random salt + PBKDF2-HMAC-SHA256 hash (stdlib only — no bcrypt dependency).
The string form of each user's `_id` is the `user_id` stamped on their messages,
leads, cost records and behavior traces.

A `role` field is stored (default "user") so manager/admin roles can build on the
same table later.

Public API:
    create_user(email, password, name="", role="user") -> str (user_id)
    authenticate(email, password) -> dict | None     (public user, no pw fields)
    get_user_by_id(user_id) -> dict | None
    get_user_by_email(email) -> dict | None
    email_exists(email) -> bool
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from .mongodb import get_db

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PBKDF2_ROUNDS = 200_000

# Raised on a duplicate signup so the UI can show a friendly message.
class EmailExistsError(ValueError):
    pass


def _users():
    return get_db()["users"]


_indexed = False


def _ensure_indexes() -> None:
    global _indexed
    if _indexed:
        return
    try:
        _users().create_index([("email", ASCENDING)], unique=True, name="uniq_email")
    except Exception as e:  # index creation is best-effort; never block auth
        logger.warning(f"Could not ensure users.email index: {e}")
    _indexed = True


# ── Password hashing (PBKDF2, stdlib) ────────────────────────────────────────────
def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return salt.hex(), dk.hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
    except (ValueError, TypeError):
        return False
    _, candidate = _hash_password(password, salt)
    return hmac.compare_digest(candidate, hash_hex or "")


# ── Serialization ─────────────────────────────────────────────────────────────
def _public(doc: dict) -> dict:
    """Strip secrets and expose a stable `id` (string _id) the app stamps."""
    return {
        "id": str(doc["_id"]),
        "email": doc.get("email", ""),
        "name": doc.get("name", ""),
        "role": doc.get("role", "user"),
        "created_at": doc.get("created_at"),
    }


# ── CRUD ─────────────────────────────────────────────────────────────────────
def email_exists(email: str) -> bool:
    return _users().find_one({"email": email.strip().lower()}) is not None


def create_user(email: str, password: str, name: str = "", role: str = "user") -> str:
    """Insert a new account and return its user_id. Raises EmailExistsError if
    the email is already registered, or ValueError on invalid input."""
    _ensure_indexes()
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("INVALID_EMAIL")
    if len(password) < 6:
        raise ValueError("WEAK_PASSWORD")

    salt_hex, hash_hex = _hash_password(password)
    doc = {
        "email": email,
        "name": name.strip(),
        "role": role,
        "pw_salt": salt_hex,
        "pw_hash": hash_hex,
        "created_at": datetime.now(timezone.utc),
        "last_login_at": None,
    }
    try:
        result = _users().insert_one(doc)
    except DuplicateKeyError:
        raise EmailExistsError(email)
    logger.info(f"User created: {result.inserted_id} ({email})")
    return str(result.inserted_id)


def authenticate(email: str, password: str) -> dict | None:
    """Return the public user dict on valid credentials, else None."""
    doc = _users().find_one({"email": email.strip().lower()})
    if not doc or not _verify_password(password, doc.get("pw_salt", ""), doc.get("pw_hash", "")):
        return None
    _users().update_one(
        {"_id": doc["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc)}}
    )
    return _public(doc)


def get_user_by_id(user_id: str) -> dict | None:
    try:
        doc = _users().find_one({"_id": ObjectId(user_id)})
    except (InvalidId, TypeError):
        return None
    return _public(doc) if doc else None


def get_user_by_email(email: str) -> dict | None:
    doc = _users().find_one({"email": email.strip().lower()})
    return _public(doc) if doc else None


def set_role(user_id: str, role: str) -> bool:
    """Set a user's role (e.g. promote to 'manager'). Returns True if updated."""
    try:
        result = _users().update_one({"_id": ObjectId(user_id)}, {"$set": {"role": role}})
    except (InvalidId, TypeError):
        return False
    return result.modified_count > 0
