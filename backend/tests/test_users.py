"""Users, roles, sessions, lockout, invites and password resets."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app import manage
from app.auth import verify_password
from app.db import SessionLocal
from app.models import Invite, Role, User
from tests.conftest import ADMIN_EMAIL, PASSWORD, TESTER_EMAIL, _client, create_user, login

NEW_PASSWORD = "a much better passphrase"


async def _user(email: str) -> User:
    async with SessionLocal() as s:
        return (await s.scalars(select(User).where(User.email == email))).one()


# --- Login -----------------------------------------------------------------------------


async def test_setup_status(anon: AsyncClient) -> None:
    assert (await anon.get("/api/auth/setup-status")).json() == {"has_users": False}
    await create_user("a@example.com", Role.admin)
    assert (await anon.get("/api/auth/setup-status")).json() == {"has_users": True}


async def test_login_me_logout(anon: AsyncClient, admin_user: User) -> None:
    r = await anon.post("/api/auth/login", json={"email": "  ADMIN@Example.com ", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    me = (await anon.get("/api/auth/me")).json()
    assert (me["email"], me["name"], me["role"], me["via"]) == (ADMIN_EMAIL, "Ada Admin", "admin", "session")
    assert "password_hash" not in me
    assert (await _user(ADMIN_EMAIL)).last_login_at is not None
    assert (await anon.post("/api/auth/logout")).status_code == 204
    assert (await anon.get("/api/auth/me")).status_code == 401


async def test_login_errors_are_generic(anon: AsyncClient, admin_user: User) -> None:
    wrong = await anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "nope nope nope"})
    unknown = await anon.post("/api/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


async def test_deactivated_user_cannot_log_in(anon: AsyncClient) -> None:
    await create_user("gone@example.com", is_active=False)
    r = await anon.post("/api/auth/login", json={"email": "gone@example.com", "password": PASSWORD})
    assert r.status_code == 401


async def test_lockout_after_failed_attempts(anon: AsyncClient, admin_user: User, client: AsyncClient) -> None:
    for _ in range(5):
        r = await anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong password"})
        assert r.status_code == 401
    # Locked: even the right password is refused now.
    r = await anon.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
    assert r.status_code == 401 and "locked" in r.json()["detail"]

    users = {u["email"]: u for u in (await client.get("/api/users")).json()}
    assert users[ADMIN_EMAIL]["locked"] is True
    # Admin (already signed in elsewhere) unlocks; login works again.
    await client.patch(f"/api/users/{users[ADMIN_EMAIL]['id']}", json={"unlock": True})
    await login(anon, ADMIN_EMAIL)


async def test_lock_expires(anon: AsyncClient, admin_user: User) -> None:
    async with SessionLocal() as s:
        await s.execute(update(User).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
        await s.commit()
    await login(anon, ADMIN_EMAIL)


async def test_ip_rate_limit(anon: AsyncClient) -> None:
    codes = [
        (await anon.post("/api/auth/login", json={"email": f"x{i}@example.com", "password": "x"})).status_code
        for i in range(21)
    ]
    assert codes[:20] == [401] * 20 and codes[20] == 429


# --- Sessions --------------------------------------------------------------------------


async def test_password_change_signs_out_other_sessions(admin_user: User) -> None:
    async with _client() as a, _client() as b:
        await login(a, ADMIN_EMAIL)
        await login(b, ADMIN_EMAIL)
        bad = await a.post("/api/auth/password", json={"current_password": "wrong", "new_password": NEW_PASSWORD})
        assert bad.status_code == 400
        weak = await a.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
        assert weak.status_code == 400 and "at least 10" in weak.json()["detail"]
        ok = await a.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        assert ok.status_code == 200
        assert (await a.get("/api/auth/me")).status_code == 200  # this browser stays signed in
        assert (await b.get("/api/auth/me")).status_code == 401  # the other one is out
        await login(b, ADMIN_EMAIL, NEW_PASSWORD)


async def test_logout_other_sessions(admin_user: User) -> None:
    async with _client() as a, _client() as b:
        await login(a, ADMIN_EMAIL)
        await login(b, ADMIN_EMAIL)
        assert (await a.post("/api/auth/logout-others")).status_code == 200
        assert (await a.get("/api/auth/me")).status_code == 200
        assert (await b.get("/api/auth/me")).status_code == 401


async def test_deactivation_is_immediate(client: AsyncClient, tester: AsyncClient) -> None:
    tester_id = (await tester.get("/api/auth/me")).json()["id"]
    assert (await tester.get("/api/projects")).status_code == 200
    r = await client.patch(f"/api/users/{tester_id}", json={"is_active": False})
    assert r.json()["is_active"] is False
    assert (await tester.get("/api/projects")).status_code == 401
    # Reactivating doesn't revive the old session.
    await client.patch(f"/api/users/{tester_id}", json={"is_active": True})
    assert (await tester.get("/api/projects")).status_code == 401
    await login(tester, TESTER_EMAIL)


async def test_delete_user(client: AsyncClient, tester: AsyncClient, make) -> None:  # type: ignore[no-untyped-def]
    me = (await client.get("/api/auth/me")).json()["id"]
    assert (await client.delete(f"/api/users/{me}")).status_code == 400  # not yourself
    assert (await tester.delete(f"/api/users/{me}")).status_code == 403  # admins only
    assert (await client.delete("/api/users/999999")).status_code == 404

    tester_id = (await tester.get("/api/auth/me")).json()["id"]
    p = await make.project()
    run = (await tester.post(f"/api/projects/{p['id']}/runs", json={"name": "By the tester"})).json()
    token = (await tester.post("/api/tokens", json={"name": "ci"})).json()
    await client.post(f"/api/users/{tester_id}/reset-link")

    assert (await client.delete(f"/api/users/{tester_id}")).status_code == 204
    assert tester_id not in [u["id"] for u in (await client.get("/api/users")).json()]
    assert (await tester.get("/api/projects")).status_code == 401  # signed out
    # What they made stays; their token and reset link don't.
    assert (await client.get(f"/api/runs/{run['id']}")).status_code == 200
    async with _client() as anon:
        r = await anon.get("/api/projects", headers={"Authorization": f"Bearer {token['token']}"})
        assert r.status_code == 401
    assert not (await client.get("/api/invites")).json()
    # The email can be invited again.
    await create_user(TESTER_EMAIL, Role.tester, name="Tom Tester")
    await login(tester, TESTER_EMAIL)


async def test_profile_name(tester: AsyncClient) -> None:
    r = await tester.patch("/api/auth/me", json={"name": "  Tamara  "})
    assert r.json()["name"] == "Tamara"


# --- Roles -----------------------------------------------------------------------------


async def test_tester_permissions(tester: AsyncClient, client: AsyncClient) -> None:
    for method, url in [("get", "/api/users"), ("get", "/api/invites"), ("patch", "/api/users/1"),
                        ("post", "/api/users/1/reset-link")]:
        r = await getattr(tester, method)(url, **({"json": {}} if method != "get" else {}))
        assert r.status_code == 403, (method, url)
    assert (await tester.post("/api/invites", json={"email": "x@example.com"})).status_code == 403

    # Normal QA work is allowed.
    p = (await tester.post("/api/projects", json={"name": "P"})).json()
    s = (await tester.post(f"/api/projects/{p['id']}/suites", json={"name": "S"})).json()
    sec = (await tester.post(f"/api/suites/{s['id']}/sections", json={"name": "Sec"})).json()
    c = (await tester.post("/api/cases", json={"section_id": sec["id"], "title": "T"})).json()
    run = (await tester.post(f"/api/projects/{p['id']}/runs", json={"name": "R", "case_ids": [c["id"]]})).json()
    assert run["created_by_name"] == "Tom Tester"
    res = await tester.post(f"/api/runs/{run['id']}/results", json={"case_id": c["id"], "status": "passed"})
    assert res.json()["recorded_by"] == "Tom Tester"
    rc = (await client.get(f"/api/runs/{run['id']}/cases")).json()[0]
    assert rc["last_result"]["recorded_by"] == "Tom Tester"
    hist = (await client.get(f"/api/cases/{c['id']}/history")).json()[0]
    assert hist["last_result"]["recorded_by"] == "Tom Tester"

    # ...but deleting a project is admin-only.
    assert (await tester.delete(f"/api/projects/{p['id']}")).status_code == 403
    assert (await client.delete(f"/api/projects/{p['id']}")).status_code == 204


async def test_last_admin_is_protected(client: AsyncClient, admin_user: User) -> None:
    me = (await client.get("/api/auth/me")).json()
    for body in ({"role": "tester"}, {"is_active": False}):
        r = await client.patch(f"/api/users/{me['id']}", json=body)
        assert r.status_code == 400
    other = await create_user("second@example.com", Role.admin)
    # Two admins: demoting the other one is fine, then it's the last again.
    assert (await client.patch(f"/api/users/{other.id}", json={"role": "tester"})).status_code == 200


# --- Tokens ----------------------------------------------------------------------------


async def test_tokens_are_per_user(client: AsyncClient, tester: AsyncClient) -> None:
    mine = (await tester.post("/api/tokens", json={"name": "my ci"})).json()
    await client.post("/api/tokens", json={"name": "admin ci"})
    assert [t["name"] for t in (await tester.get("/api/tokens")).json()] == ["my ci"]
    all_tokens = {t["name"]: t["owner"] for t in (await client.get("/api/tokens")).json()}
    assert all_tokens == {"my ci": "Tom Tester", "admin ci": "Ada Admin"}

    admin_token = next(t for t in (await client.get("/api/tokens")).json() if t["name"] == "admin ci")
    assert (await tester.delete(f"/api/tokens/{admin_token['id']}")).status_code == 404
    # Admins can revoke anyone's token.
    assert (await client.delete(f"/api/tokens/{mine['id']}")).status_code == 204


async def test_token_acts_as_owner_and_dies_with_deactivation(client: AsyncClient, tester: AsyncClient) -> None:
    token = (await tester.post("/api/tokens", json={"name": "ci"})).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    async with _client() as bot:
        me = (await bot.get("/api/auth/me", headers=headers)).json()
        assert (me["email"], me["role"], me["via"]) == (TESTER_EMAIL, "tester", "token")
        assert (await bot.get("/api/users", headers=headers)).status_code == 403
        tester_id = me["id"]
        await client.patch(f"/api/users/{tester_id}", json={"is_active": False})
        assert (await bot.get("/api/projects", headers=headers)).status_code == 401


async def test_admin_token_cannot_manage_users(client: AsyncClient) -> None:
    token = (await client.post("/api/tokens", json={"name": "ci"})).json()["token"]
    async with _client() as bot:
        h = {"Authorization": f"Bearer {token}"}
        assert (await bot.get("/api/projects", headers=h)).status_code == 200
        assert (await bot.get("/api/users", headers=h)).status_code == 403
        assert (await bot.post("/api/invites", headers=h, json={"email": "x@example.com"})).status_code == 403
        r = await bot.post("/api/auth/password", headers=h,
                           json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
        assert r.status_code == 403


# --- Invites ---------------------------------------------------------------------------


async def test_invite_flow(client: AsyncClient, anon: AsyncClient) -> None:
    link = (await client.post("/api/invites", json={"email": "New.Person@Example.com", "role": "tester"})).json()
    assert link["path"] == f"/invite/{link['token']}" and link["email"] == "new.person@example.com"
    assert [i["email"] for i in (await client.get("/api/invites")).json()] == ["new.person@example.com"]

    info = (await anon.get(f"/api/invites/accept/{link['token']}")).json()
    assert (info["purpose"], info["email"], info["role"]) == ("invite", "new.person@example.com", "tester")

    url = f"/api/invites/accept/{link['token']}"
    assert (await anon.post(url, json={"name": "New", "password": "short"})).status_code == 400
    assert (await anon.post(url, json={"password": NEW_PASSWORD})).status_code == 400  # name required
    r = await anon.post(url, json={"name": "New Person", "password": NEW_PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "tester"
    assert (await anon.get("/api/auth/me")).json()["email"] == "new.person@example.com"  # signed in

    # One-time: the link is gone, and no longer pending.
    assert (await anon.get(url)).status_code == 404
    assert (await anon.post(url, json={"name": "X", "password": NEW_PASSWORD})).status_code == 404
    assert (await client.get("/api/invites")).json() == []

    async with _client() as c:
        await login(c, "new.person@example.com", NEW_PASSWORD)


async def test_invite_rules(client: AsyncClient, anon: AsyncClient, admin_user: User) -> None:
    assert (await client.post("/api/invites", json={"email": ADMIN_EMAIL})).status_code == 409
    assert (await client.post("/api/invites", json={"email": "not-an-email"})).status_code == 422

    revoked = (await client.post("/api/invites", json={"email": "r@example.com"})).json()
    assert (await client.delete(f"/api/invites/{revoked['id']}")).status_code == 204
    assert (await anon.get(f"/api/invites/accept/{revoked['token']}")).status_code == 404

    expired = (await client.post("/api/invites", json={"email": "e@example.com", "role": "admin"})).json()
    async with SessionLocal() as s:
        await s.execute(update(Invite).where(Invite.id == expired["id"])
                        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        await s.commit()
    r = await anon.post(f"/api/invites/accept/{expired['token']}", json={"name": "E", "password": NEW_PASSWORD})
    assert r.status_code == 404

    assert (await anon.get("/api/invites/accept/inv_made-up")).status_code == 404


async def test_admin_invite_creates_admin(client: AsyncClient, anon: AsyncClient) -> None:
    link = (await client.post("/api/invites", json={"email": "boss@example.com", "role": "admin"})).json()
    r = await anon.post(f"/api/invites/accept/{link['token']}", json={"name": "Boss", "password": NEW_PASSWORD})
    assert r.json()["role"] == "admin"
    assert (await anon.get("/api/users")).status_code == 200


async def test_password_reset_link(client: AsyncClient, tester: AsyncClient, anon: AsyncClient) -> None:
    tester_id = (await tester.get("/api/auth/me")).json()["id"]
    link = (await client.post(f"/api/users/{tester_id}/reset-link")).json()
    info = (await anon.get(f"/api/invites/accept/{link['token']}")).json()
    assert (info["purpose"], info["name"]) == ("reset", "Tom Tester")

    r = await anon.post(f"/api/invites/accept/{link['token']}", json={"password": NEW_PASSWORD})
    assert r.status_code == 200 and r.json()["email"] == TESTER_EMAIL
    assert (await tester.get("/api/auth/me")).status_code == 401  # old sessions are out
    user = await _user(TESTER_EMAIL)
    assert verify_password(user.password_hash, NEW_PASSWORD)
    assert (await anon.post(f"/api/invites/accept/{link['token']}", json={"password": NEW_PASSWORD})).status_code == 404


async def test_tampered_or_stale_cookie(anon: AsyncClient, admin_user: User) -> None:
    anon.cookies.set("th_session", "eyJ1aWQiOjF9.forged.sig")
    assert (await anon.get("/api/projects")).status_code == 401


# --- manage CLI ----------------------------------------------------------------------


@pytest.fixture
def stdin(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def set_(text: str) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(text))
    return set_


async def test_manage_create_admin_and_reset(stdin, capsys) -> None:  # type: ignore[no-untyped-def]
    stdin("first admin password\n")
    await manage.create_admin(manage.build_parser().parse_args(
        ["create-admin", "--email", "Root@Example.com", "--name", "Root", "--password-stdin"]))
    user = await _user("root@example.com")
    assert user.role == Role.admin and verify_password(user.password_hash, "first admin password")

    stdin("x\n")
    with pytest.raises(manage.Abort, match="already exists"):
        await manage.create_admin(manage.build_parser().parse_args(
            ["create-admin", "--email", "root@example.com", "--name", "R", "--password-stdin"]))

    stdin("short\n")
    with pytest.raises(manage.Abort, match="at least 10"):
        await manage.reset_password(manage.build_parser().parse_args(
            ["reset-password", "--email", "root@example.com", "--password-stdin"]))

    stdin("second admin password\n")
    await manage.reset_password(manage.build_parser().parse_args(
        ["reset-password", "--email", "root@example.com", "--password-stdin"]))
    after = await _user("root@example.com")
    assert verify_password(after.password_hash, "second admin password")
    assert after.session_version == user.session_version + 1

    await manage.list_users(manage.build_parser().parse_args(["list-users"]))
    assert "root@example.com" in capsys.readouterr().out
