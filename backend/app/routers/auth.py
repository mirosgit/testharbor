from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    LOCKOUT_MINUTES,
    MAX_FAILED_LOGINS,
    CurrentPrincipal,
    Principal,
    clear_session_cookie,
    hash_password,
    login_limiter,
    needs_rehash,
    normalize_email,
    password_problem,
    require_session,
    set_session_cookie,
    verify_password,
)
from app.db import get_session
from app.models import User
from app.schemas import LoginIn, MeOut, PasswordChange, ProfilePatch, SetupStatus, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]
SessionPrincipal = Annotated[Principal, Depends(require_session)]

INVALID = "Invalid email or password"


def _me(p: Principal) -> MeOut:
    return MeOut(**UserOut.model_validate(p.user).model_dump(), via=p.via)


@router.get("/setup-status", response_model=SetupStatus)
async def setup_status(session: Session) -> SetupStatus:
    """Whether any user exists (the login page shows how to create the first admin)."""
    return SetupStatus(has_users=bool(await session.scalar(select(func.count()).select_from(User))))


@router.post("/login", response_model=MeOut)
async def login(body: LoginIn, request: Request, response: Response, session: Session) -> MeOut:
    ip = request.client.host if request.client else "unknown"
    if not login_limiter.check(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts, try again in a minute")

    user = await session.scalar(select(User).where(User.email == normalize_email(body.email)))
    now = datetime.now(UTC)
    ok = verify_password(user.password_hash if user else None, body.password)

    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    if user.locked_until and user.locked_until > now:
        # Same generic answer whether or not the password was right.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"{INVALID}. Too many failed attempts: the account is locked for up to {LOCKOUT_MINUTES} minutes",
        )
    if not ok:
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_logins = 0
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    await session.commit()
    set_session_cookie(response, user)
    return _me(Principal(user=user, via="session"))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    clear_session_cookie(response)


@router.get("/me", response_model=MeOut)
async def me(principal: CurrentPrincipal) -> MeOut:
    return _me(principal)


@router.patch("/me", response_model=MeOut)
async def update_profile(body: ProfilePatch, principal: SessionPrincipal, session: Session) -> MeOut:
    user = await session.merge(principal.user)
    user.name = body.name.strip()
    await session.commit()
    return _me(Principal(user=user, via="session"))


@router.post("/password", response_model=MeOut)
async def change_password(
    body: PasswordChange, principal: SessionPrincipal, response: Response, session: Session
) -> MeOut:
    """Change your password. Signs out all other sessions."""
    user = await session.merge(principal.user)
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if problem := password_problem(body.new_password, user.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    user.password_hash = hash_password(body.new_password)
    user.session_version += 1
    await session.commit()
    set_session_cookie(response, user)  # keep this browser signed in
    return _me(Principal(user=user, via="session"))


@router.post("/logout-others", response_model=MeOut)
async def logout_other_sessions(principal: SessionPrincipal, response: Response, session: Session) -> MeOut:
    """Invalidate every session of the current user except this one."""
    user = await session.merge(principal.user)
    user.session_version += 1
    await session.commit()
    set_session_cookie(response, user)
    return _me(Principal(user=user, via="session"))
