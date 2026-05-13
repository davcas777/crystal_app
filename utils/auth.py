"""Resolve the current user.

Databricks Apps forward authenticated user identity via request headers.
Streamlit exposes them through `st.context.headers`.  Falls back to a local
identity when running outside of Databricks Apps (development).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st


@dataclass
class User:
    email: str
    display_name: str


def _from_headers() -> User | None:
    try:
        headers = st.context.headers
    except Exception:  # noqa: BLE001
        return None
    if not headers:
        return None
    email = (
        headers.get("X-Forwarded-Email")
        or headers.get("x-forwarded-email")
        or headers.get("X-Forwarded-User")
        or headers.get("x-forwarded-user")
    )
    name = (
        headers.get("X-Forwarded-Preferred-Username")
        or headers.get("x-forwarded-preferred-username")
        or email
    )
    if email:
        return User(email=email.lower(), display_name=name or email)
    return None


def get_current_user() -> User:
    """Return the current authenticated user.

    Priority:
    1. Databricks Apps forwarded headers
    2. `LOCAL_USER_EMAIL` env var (for local dev)
    3. `anonymous@local`
    """
    user = _from_headers()
    if user:
        return user
    email = os.environ.get("LOCAL_USER_EMAIL", "anonymous@local")
    return User(email=email.lower(), display_name=email)
