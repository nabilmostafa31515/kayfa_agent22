"""Manager authentication — a thin role-based layer over the unified `user_auth`.

Auth is built once (the MongoDB `users` table + a single session); a "manager" is
simply a user whose role is in MANAGER_ROLES. This module stays as a compatibility
surface so the dashboard pages keep importing `manager_auth` unchanged, while all
the real work lives in user_auth.

The manager account is seeded from the environment (idempotent):
    MANAGER_EMAIL     (default admin@kayfa.io)
    MANAGER_PASSWORD  (required to seed)
    MANAGER_NAME      (optional)

Public API (unchanged for callers):
    is_authenticated() -> bool
    current_user() -> str | None     # manager display name
    logout()
    login_form(title=..., subtitle=...) -> bool
    require_manager()
    logout_button()
"""

from __future__ import annotations

from src.auth import user_auth
from src.auth.user_auth import (  # re-exported for callers
    MANAGER_ROLES,
    logout,
    logout_button,
    seed_managers_from_env,
)


def is_authenticated() -> bool:
    """True when the signed-in user has a manager-level role."""
    return user_auth.has_role(*MANAGER_ROLES)


def current_user() -> str | None:
    """Manager display name (name or email), or None if not a signed-in manager."""
    u = user_auth.current_user()
    if u and u.get("role") in MANAGER_ROLES:
        return u.get("name") or u.get("email")
    return None


def login_form(
    title: str = "تسجيل دخول المدير",
    subtitle: str = "Manager sign-in — Kayfa dashboards",
) -> bool:
    """Render the manager (login-only) sign-in screen; reruns on success."""
    seed_managers_from_env()
    user_auth.auth_gate(title=title, subtitle=subtitle, allow_signup=False)
    return False


def require_manager() -> None:
    """Page gate for the manager dashboards: manager role required, else halt."""
    user_auth.require_role(*MANAGER_ROLES)
