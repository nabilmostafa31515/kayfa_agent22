"""End-user authentication for the Kayfa chat (signup / login).

Backed by the `users` collection (see database/users_repository). The signed-in
user is held in st.session_state and exposed via current_user(); its `id` is the
`user_id` the app stamps on messages, leads, cost records and behavior traces.

Mirrors the manager_auth API so the two feel consistent:
    current_user() -> dict | None        ({id, email, name, role})
    is_authenticated() -> bool
    login(email, password) -> (ok, msg)
    signup(name, email, password) -> (ok, msg)   (auto-logs-in on success)
    logout()
    require_user() -> dict                # page gate: gate + st.stop() if out
    auth_gate()                           # Login / Sign-up tabs
    logout_button()                       # sidebar account + sign-out
"""

from __future__ import annotations

import logging
import os

import streamlit as st

from src.database import users_repository as users
from src.database.traces_repository import record_trace

logger = logging.getLogger(__name__)

_AUTH_KEY = "_user_auth"   # bool — is a user session open
_USER_KEY = "_user"        # dict — the signed-in user (id/email/name/role)

# Roles that may reach the manager area. Plain end-users have role "user".
MANAGER_ROLES = ("manager", "admin")


# ── Session ─────────────────────────────────────────────────────────────────────
def is_authenticated() -> bool:
    return bool(st.session_state.get(_AUTH_KEY, False))


def current_user() -> dict | None:
    return st.session_state.get(_USER_KEY) if is_authenticated() else None


def current_user_id() -> str:
    u = current_user()
    return u["id"] if u else ""


def _open_session(user: dict) -> None:
    st.session_state[_AUTH_KEY] = True
    st.session_state[_USER_KEY] = user


def logout() -> None:
    u = current_user()
    if u:
        record_trace(u["id"], "logout")
    st.session_state.pop(_AUTH_KEY, None)
    st.session_state.pop(_USER_KEY, None)


def has_role(*roles: str) -> bool:
    u = current_user()
    return bool(u and u.get("role") in roles)


# ── Manager seeding (single source of truth for the manager account) ─────────────
def _get_secret(key: str, default: str | None = None) -> str | None:
    """st.secrets first (for Streamlit Cloud), then the environment."""
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)


_seeded = False


def seed_managers_from_env() -> None:
    """Ensure a manager account exists in the users table, sourced from env:

        MANAGER_EMAIL     (default admin@kayfa.io)
        MANAGER_PASSWORD  (required — without it no manager is seeded)
        MANAGER_NAME      (optional display name)

    Idempotent and cheap (runs once per process). This is what lets the manager
    dashboards use the *same* auth system as end-users — a manager is just a
    user with role "manager"."""
    global _seeded
    if _seeded:
        return
    _seeded = True
    email = (_get_secret("MANAGER_EMAIL") or "admin@kayfa.io").strip().lower()
    password = _get_secret("MANAGER_PASSWORD")
    name = _get_secret("MANAGER_NAME") or "Kayfa Manager"
    if not password:
        logger.warning("MANAGER_PASSWORD not set — no manager account seeded.")
        return
    try:
        existing = users.get_user_by_email(email)
        if existing is None:
            users.create_user(email, password, name=name, role="manager")
            logger.info("Seeded manager account: %s", email)
        elif existing.get("role") not in MANAGER_ROLES:
            # An account with this email exists but isn't a manager — promote it.
            users.set_role(existing["id"], "manager")
            logger.info("Promoted %s to manager", email)
    except Exception as e:
        logger.error("Manager seed failed: %s", e)


# ── Actions ─────────────────────────────────────────────────────────────────────
def login(email: str, password: str) -> tuple[bool, str]:
    try:
        user = users.authenticate(email, password)
    except Exception as e:
        logger.error(f"Login error: {e}")
        return False, "تعذّر الاتصال بقاعدة البيانات — Could not reach the database."
    if not user:
        return False, "البريد أو كلمة المرور غير صحيحة — Wrong email or password."
    _open_session(user)
    record_trace(user["id"], "login", props={"role": user.get("role", "user")})
    logger.info("User login: %s", user["email"])
    return True, ""


def signup(name: str, email: str, password: str) -> tuple[bool, str]:
    try:
        user_id = users.create_user(email, password, name=name)
    except users.EmailExistsError:
        return False, "هذا البريد مسجّل بالفعل — This email is already registered."
    except ValueError as e:
        code = str(e)
        if code == "INVALID_EMAIL":
            return False, "بريد إلكتروني غير صالح — Enter a valid email address."
        if code == "WEAK_PASSWORD":
            return False, "كلمة المرور قصيرة (6 أحرف على الأقل) — Password too short (min 6)."
        return False, "بيانات غير صالحة — Invalid input."
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return False, "تعذّر إنشاء الحساب — Could not create the account."
    _open_session({"id": user_id, "email": email.strip().lower(),
                   "name": name.strip(), "role": "user"})
    record_trace(user_id, "signup")
    logger.info("User signup: %s", email.strip().lower())
    return True, ""


# ── UI ─────────────────────────────────────────────────────────────────────────
def _login_form() -> None:
    with st.form("auth_login_form", clear_on_submit=False):
        email = st.text_input("📧 البريد الإلكتروني · Email", key="li_email")
        password = st.text_input("🔒 كلمة المرور · Password", type="password", key="li_pw")
        submitted = st.form_submit_button("تسجيل الدخول · Sign in",
                                          type="primary", use_container_width=True)
    if submitted:
        ok, msg = login(email, password)
        if ok:
            st.rerun()
        else:
            st.error(f"❌ {msg}")


def _signup_form() -> None:
    with st.form("auth_signup_form", clear_on_submit=False):
        name = st.text_input("👤 الاسم · Name", key="su_name")
        email_s = st.text_input("📧 البريد الإلكتروني · Email", key="su_email")
        pw_s = st.text_input("🔒 كلمة المرور (6 أحرف على الأقل) · Password (min 6)",
                             type="password", key="su_pw")
        submitted_s = st.form_submit_button("إنشاء الحساب · Create account",
                                            type="primary", use_container_width=True)
    if submitted_s:
        ok, msg = signup(name, email_s, pw_s)
        if ok:
            st.rerun()
        else:
            st.error(f"❌ {msg}")


def auth_gate(
    title: str = "تسجيل الدخول إلى كيفا",
    subtitle: str = "سجّل الدخول أو أنشئ حساباً للدردشة مع مساعد كيفا — Sign in or create an account to chat",
    allow_signup: bool = True,
) -> None:
    """Render the auth screen and rerun on success.

    With ``allow_signup`` (the chat) it shows Login + Sign-up tabs. Without it
    (the manager area, where accounts aren't self-served) it shows login only."""
    from src.ui.branding import brand_mark

    st.markdown(
        "<div class='k-login'>"
        f"<div class='k-login__brand'>{brand_mark(72)}</div>"
        f"<h2 class='k-login__title'>{title}</h2>"
        f"<p class='k-login__sub'>{subtitle}</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if allow_signup:
            tab_login, tab_signup = st.tabs(["🔑 دخول · Login", "✨ حساب جديد · Sign up"])
            with tab_login:
                _login_form()
            with tab_signup:
                _signup_form()
        else:
            _login_form()


def require_user() -> dict:
    """Page guard. Call at the top of the chat page: returns the signed-in user,
    or renders the auth gate and halts the page (st.stop()) when not signed in."""
    user = current_user()
    if user:
        return user
    st.markdown(
        "<div class='k-gate-note'>🔒 سجّل الدخول للدردشة مع مساعد كيفا."
        "<br><span>Please sign in to chat with the Kayfa assistant.</span></div>",
        unsafe_allow_html=True,
    )
    auth_gate()
    st.stop()


def require_role(*roles: str, note_html: str | None = None) -> dict:
    """Role guard for restricted areas (e.g. the manager dashboards).

    - Signed in with one of ``roles`` → returns the user.
    - Signed in but lacking the role → 'no access' note + sign-out, then halts.
    - Not signed in → login-only gate, then halts.
    Same single session/users table as end-users — auth built once, used for both.
    """
    seed_managers_from_env()
    user = current_user()
    if user and user.get("role") in roles:
        return user
    if user:  # signed in, wrong role
        st.markdown(
            "<div class='k-gate-note'>🚫 حسابك لا يملك صلاحية الوصول إلى هذه المنطقة."
            "<br><span>Your account doesn't have access to this area.</span></div>",
            unsafe_allow_html=True,
        )
        logout_button()
        st.stop()
    # not signed in
    st.markdown(
        note_html or
        "<div class='k-gate-note'>🔒 هذه المنطقة مخصّصة لمدير كيفا — سجّل الدخول للمتابعة."
        "<br><span>This area is restricted to the Kayfa manager. Please sign in.</span></div>",
        unsafe_allow_html=True,
    )
    auth_gate(
        title="تسجيل دخول المدير",
        subtitle="Manager sign-in — Kayfa dashboards",
        allow_signup=False,
    )
    st.stop()


def logout_button() -> None:
    """Show the signed-in account + a sign-out button in the sidebar.

    The role is shown so a manager sees they're in the manager session."""
    user = current_user()
    if not user:
        return
    is_mgr = user.get("role") in MANAGER_ROLES
    role_label = "مدير · Manager" if is_mgr else "عميل · User"
    with st.sidebar:
        label = user.get("name") or user.get("email", "")
        st.markdown(
            "<div class='k-signed-in'>👤 "
            f"<b>{label}</b><span> · {role_label}</span></div>",
            unsafe_allow_html=True,
        )
        if st.button("🚪 تسجيل الخروج · Sign out", key="_user_logout",
                     use_container_width=True):
            logout()
            st.rerun()
