"""Authentication and authorization.

- Users log in with email + password (argon2id). The session cookie is signed and carries
  {uid, sv}; every request re-checks the user in the DB (active, session_version), so password
  changes, "sign out everywhere" and deactivation take effect immediately.
- API tokens (Bearer) belong to a user and act with that user's role.
- Roles: admin (everything) and tester (everything except user management and deleting projects).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import ApiToken, Role, User

SESSION_COOKIE = "th_session"
TOKEN_PREFIX = "th_"
MIN_PASSWORD_LENGTH = 10
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15

_hasher = PasswordHasher()  # argon2id with library defaults
# Verified against when the email is unknown, so timing doesn't reveal which accounts exist.
_DUMMY_HASH = _hasher.hash(secrets.token_hex(16))


# --- Passwords -----------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problem(password: str, email: str = "") -> str | None:
    """Return a human-readable reason if the password is not acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > 256:
        return "Password is too long"
    if email and password.strip().lower() == email.strip().lower():
        return "Password must not be the same as the email"
    return None


def normalize_email(email: str) -> str:
    return email.strip().lower()


# --- Tokens --------------------------------------------------------------------------


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token(prefix: str = TOKEN_PREFIX) -> str:
    return prefix + secrets.token_urlsafe(32)


# --- Sessions ------------------------------------------------------------------------


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="th-session")


def set_session_cookie(response: Response, user: User) -> None:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        _serializer().dumps({"uid": user.id, "sv": user.session_version}),
        max_age=s.session_max_age_days * 86400,
        httponly=True,
        samesite="lax",
        secure=s.secure_cookies,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@dataclass
class Principal:
    user: User
    via: Literal["session", "token"]
    token_name: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.user.role == Role.admin


async def _session_principal(request: Request, session: AsyncSession) -> Principal | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        data = _serializer().loads(raw, max_age=get_settings().session_max_age_days * 86400)
    except BadSignature:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("uid"), int):
        return None
    user = await session.get(User, data["uid"])
    if user is None or not user.is_active or user.session_version != data.get("sv"):
        return None
    return Principal(user=user, via="session")


async def _token_principal(request: Request, session: AsyncSession) -> Principal | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    row = (
        await session.execute(
            select(ApiToken, User)
            .join(User, User.id == ApiToken.user_id)
            .where(
                ApiToken.token_hash == hash_token(token.strip()),
                ApiToken.revoked_at.is_(None),
                User.is_active.is_(True),
            )
        )
    ).first()
    if row is None:
        return None
    api_token, user = row
    api_token.last_used_at = datetime.now(UTC)
    await session.commit()
    return Principal(user=user, via="token", token_name=api_token.name)


async def current_principal(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Principal:
    principal = await _session_principal(request, session) or await _token_principal(request, session)
    if principal is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
        )
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_session(principal: CurrentPrincipal) -> Principal:
    """Account management needs a real login, not an API token (a leaked CI token
    must not be able to mint new tokens or change passwords)."""
    if principal.via != "session":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action requires signing in; API tokens can't do it")
    return principal


def require_admin(principal: CurrentPrincipal) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return principal


def require_admin_session(principal: Annotated[Principal, Depends(require_session)]) -> Principal:
    return require_admin(principal)


# Backwards-compatible name used by routers for "any signed-in user".
require_auth = current_principal


# --- Login rate limiting -------------------------------------------------------------


class IpRateLimiter:
    """Small in-memory sliding-window limiter for login attempts per client IP.

    Per-account lockout (in the DB) is the main protection; this only slows down spraying
    many accounts from one address. State is per backend process.
    """

    def __init__(self, limit: int = 20, window_s: float = 60) -> None:
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 10_000:  # bound memory
            self.hits.clear()
        return True

    def reset(self) -> None:
        self.hits.clear()


login_limiter = IpRateLimiter()
