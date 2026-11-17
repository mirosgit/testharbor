"""Users and invite / password-reset links (admin), plus the public accept endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    Principal,
    generate_token,
    hash_password,
    hash_token,
    normalize_email,
    password_problem,
    require_admin_session,
    set_session_cookie,
)
from app.db import get_session
from app.models import Invite, InvitePurpose, Role, User
from app.schemas import (
    AdminUserOut,
    InviteAccept,
    InviteIn,
    InviteInfo,
    InviteLink,
    InviteOut,
    MeOut,
    UserOut,
    UserPatch,
)
from app.services import get_or_404

INVITE_TTL = timedelta(hours=72)

router = APIRouter(prefix="/api", tags=["users"])
Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[Principal, Depends(require_admin_session)]


def _admin_out(u: User) -> AdminUserOut:
    locked = bool(u.locked_until and u.locked_until > datetime.now(UTC))
    return AdminUserOut.model_validate(u).model_copy(update={"locked": locked})


async def _active_admins(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count()).select_from(User).where(User.role == Role.admin, User.is_active.is_(True))
    ) or 0


def _link(invite: Invite, token: str) -> InviteLink:
    return InviteLink(**InviteOut.model_validate(invite).model_dump(), token=token, path=f"/invite/{token}")


async def _new_link(session: AsyncSession, **fields: object) -> InviteLink:
    token = generate_token("inv_")
    invite = Invite(token_hash=hash_token(token), expires_at=datetime.now(UTC) + INVITE_TTL, **fields)
    session.add(invite)
    await session.commit()
    return _link(invite, token)


# --- Admin: users ----------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(_: Admin, session: Session) -> list[AdminUserOut]:
    users = await session.scalars(select(User).order_by(User.is_active.desc(), User.name, User.id))
    return [_admin_out(u) for u in users]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(user_id: int, body: UserPatch, admin: Admin, session: Session) -> AdminUserOut:
    user = await get_or_404(session, User, user_id)
    demoting = body.role is not None and body.role != Role.admin and user.role == Role.admin
    deactivating = body.is_active is False and user.is_active
    if user.id == admin.user.id and (demoting or deactivating):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can't demote or deactivate yourself")
    if (demoting or deactivating) and user.role == Role.admin and user.is_active and await _active_admins(session) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one active admin is required")

    if body.name is not None:
        user.name = body.name.strip()
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        user.session_version += 1  # sign out immediately when deactivated
        if body.is_active:
            user.failed_logins, user.locked_until = 0, None
    if body.unlock:
        user.failed_logins, user.locked_until = 0, None
    await session.commit()
    return _admin_out(user)


@router.post("/users/{user_id}/reset-link", response_model=InviteLink, status_code=status.HTTP_201_CREATED)
async def create_reset_link(user_id: int, admin: Admin, session: Session) -> InviteLink:
    """One-time link (72 h) the user opens to set a new password. Send it to them yourself."""
    user = await get_or_404(session, User, user_id)
    if not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reactivate the user first")
    return await _new_link(session, purpose=InvitePurpose.reset, email=user.email, role=user.role,
                           user_id=user.id, created_by_id=admin.user.id)


# --- Admin: invites ------------------------------------------------------------------


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(_: Admin, session: Session) -> list[Invite]:
    """Pending (unused, unrevoked, unexpired) links."""
    rows = await session.scalars(
        select(Invite)
        .where(Invite.used_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > datetime.now(UTC))
        .order_by(Invite.created_at.desc())
    )
    return list(rows)


@router.post("/invites", response_model=InviteLink, status_code=status.HTTP_201_CREATED)
async def create_invite(body: InviteIn, admin: Admin, session: Session) -> InviteLink:
    email = normalize_email(body.email)
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    return await _new_link(session, purpose=InvitePurpose.invite, email=email, role=body.role,
                           created_by_id=admin.user.id)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(invite_id: int, _: Admin, session: Session) -> None:
    invite = await get_or_404(session, Invite, invite_id)
    if invite.revoked_at is None and invite.used_at is None:
        invite.revoked_at = datetime.now(UTC)
        await session.commit()


# --- Public: accept a link -------------------------------------------------------------


async def _valid_invite(session: AsyncSession, token: str, lock: bool = False) -> Invite:
    stmt = select(Invite).where(Invite.token_hash == hash_token(token))
    invite = await session.scalar(stmt.with_for_update() if lock else stmt)  # one use, even if raced
    if (
        invite is None
        or invite.used_at is not None
        or invite.revoked_at is not None
        or invite.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid or has expired. Ask your admin for a new one.")
    return invite


@router.get("/invites/accept/{token}", response_model=InviteInfo)
async def invite_info(token: str, session: Session) -> InviteInfo:
    invite = await _valid_invite(session, token)
    name = None
    if invite.user_id:
        user = await session.get(User, invite.user_id)
        name = user.name if user else None
    return InviteInfo(purpose=invite.purpose, email=invite.email, role=invite.role, name=name,
                      expires_at=invite.expires_at)


@router.post("/invites/accept/{token}", response_model=MeOut)
async def accept_invite(token: str, body: InviteAccept, response: Response, session: Session) -> MeOut:
    """Create the account (invite) or set a new password (reset), then sign in."""
    invite = await _valid_invite(session, token, lock=True)
    if problem := password_problem(body.password, invite.email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    if invite.purpose == InvitePurpose.reset:
        user = await session.get(User, invite.user_id) if invite.user_id else None
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "This account is no longer active")
        user.password_hash = hash_password(body.password)
        user.session_version += 1  # sign out everywhere else
        user.failed_logins, user.locked_until = 0, None
        if body.name and body.name.strip():
            user.name = body.name.strip()
    else:
        if not body.name or not body.name.strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name is required")
        if await session.scalar(select(User.id).where(User.email == invite.email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user = User(email=invite.email, name=body.name.strip(), role=invite.role,
                    password_hash=hash_password(body.password))
        session.add(user)

    now = datetime.now(UTC)
    invite.used_at = now
    user.last_login_at = now
    await session.commit()
    set_session_cookie(response, user)
    return MeOut(**UserOut.model_validate(user).model_dump(), via="session")
