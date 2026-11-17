"""Authentication: one admin login (session cookie) + API tokens (Bearer)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import ApiToken

SESSION_COOKIE = "th_session"
TOKEN_PREFIX = "th_"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="th-session")


def check_credentials(username: str, password: str) -> bool:
    s = get_settings()
    # Evaluate both comparisons to keep timing independent of which one fails.
    ok_user = secrets.compare_digest(username.encode(), s.admin_username.encode())
    ok_pass = secrets.compare_digest(password.encode(), s.admin_password.encode())
    return ok_user and ok_pass


def set_session_cookie(response: Response, username: str) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        _serializer().dumps({"u": username}),
        max_age=s.session_max_age_days * 86400,
        httponly=True,
        samesite="lax",
        secure=s.secure_cookies,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _session_user(request: Request) -> str | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=get_settings().session_max_age_days * 86400)
    except BadSignature:
        return None
    user = data.get("u")
    return user if user == get_settings().admin_username else None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


async def _token_user(request: Request, session: AsyncSession) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    api_token = await session.scalar(
        select(ApiToken).where(
            ApiToken.token_hash == hash_token(token.strip()), ApiToken.revoked_at.is_(None)
        )
    )
    if api_token is None:
        return None
    api_token.last_used_at = datetime.now(UTC)
    await session.commit()
    return f"token:{api_token.name}"


async def require_auth(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> str:
    """Return the principal ("admin" or "token:<name>") or raise 401."""
    principal = _session_user(request) or await _token_user(request, session)
    if principal is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal
