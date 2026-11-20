"""Server-side account management (run inside the backend container).

    docker compose exec backend python -m app.manage create-admin
    docker compose exec backend python -m app.manage reset-password --email anna@example.com
    docker compose exec backend python -m app.manage unlock --email anna@example.com
    docker compose exec backend python -m app.manage list-users
    docker compose exec backend python -m app.manage create-agent-token   # a token for a test runner

For scripts, pass the password on stdin with `--password-stdin` (use `exec -T`).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.auth import generate_token, hash_password, hash_token, normalize_email, password_problem
from app.db import SessionLocal, engine
from app.models import ApiToken, Role, User

AGENT_EMAIL = "agent@testharbor.local"


class Abort(Exception):
    pass


def _ask(prompt: str, default: str | None = None) -> str:
    if not sys.stdin.isatty():
        raise Abort(f"{prompt.strip(': ')} is required (pass it as an option when not running interactively)")
    value = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return value or (default or "")


def _read_password(args: argparse.Namespace, email: str) -> str:
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        if not sys.stdin.isatty():
            raise Abort("No TTY: use --password-stdin (and `docker compose exec -T`)")
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise Abort("Passwords don't match")
    if problem := password_problem(password, email):
        raise Abort(problem)
    return password


async def create_admin(args: argparse.Namespace) -> None:
    email = normalize_email(args.email or _ask("Email"))
    if "@" not in email:
        raise Abort("A valid email is required")
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None and not args.update:
            raise Abort(f"User {email} already exists (use reset-password, or --update to make it an active admin)")
        name = args.name or (user.name if user else None) or _ask("Name", email.split("@")[0])
        password = _read_password(args, email)
        if user is None:
            user = User(email=email, name=name, role=Role.admin, password_hash=hash_password(password))
            session.add(user)
            action = "created"
        else:
            user.name, user.role, user.is_active = name, Role.admin, True
            user.password_hash = hash_password(password)
            user.session_version += 1
            user.failed_logins, user.locked_until = 0, None
            action = "updated"
        await session.commit()
        print(f"Admin {email} {action}. Sign in at your TestHarbor URL.")


async def _get_user(session, email: str) -> User:  # type: ignore[no-untyped-def]
    user = await session.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        raise Abort(f"No user with email {email}")
    return user


async def reset_password(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        user = await _get_user(session, args.email)
        user.password_hash = hash_password(_read_password(args, user.email))
        user.session_version += 1  # signs out all sessions
        user.failed_logins, user.locked_until = 0, None
        await session.commit()
        print(f"Password for {user.email} changed; all their sessions were signed out.")


async def unlock(args: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        user = await _get_user(session, args.email)
        user.failed_logins, user.locked_until = 0, None
        await session.commit()
        print(f"{user.email} unlocked.")


async def list_users(_: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        users = list(await session.scalars(select(User).order_by(User.id)))
    if not users:
        print("No users. Create the first admin: python -m app.manage create-admin")
    for u in users:
        state = "active" if u.is_active else "deactivated"
        print(f"{u.id:>4}  {u.email:<40} {u.role.value:<7} {state:<12} {u.name}")


async def create_agent_token(args: argparse.Namespace) -> None:
    """A token for `testcli agent`, owned by a service user nobody signs in as (role Tester)."""
    import secrets

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == AGENT_EMAIL))
        if user is None:
            user = User(email=AGENT_EMAIL, name="Autotests agent", role=Role.tester,
                        password_hash=hash_password(secrets.token_urlsafe(48)))  # unknown to anyone
            session.add(user)
            await session.flush()
        token = generate_token()
        session.add(ApiToken(user_id=user.id, name=args.name, token_hash=hash_token(token), prefix=token[:10]))
        await session.commit()
    if args.quiet:
        print(token)
    else:
        print(f"Token for {args.name!r} (user {AGENT_EMAIL}); it is shown only now:\n\n  {token}\n")
        print("Revoke it in Settings › API tokens of that user, or create another one with this command.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m app.manage", description="TestHarbor account management")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-admin", help="create an admin account (e.g. the first one)")
    c.add_argument("--email")
    c.add_argument("--name")
    c.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    c.add_argument("--update", action="store_true",
                   help="if the email exists: make it an active admin and set the password")
    c.set_defaults(func=create_admin)

    r = sub.add_parser("reset-password", help="set a new password and sign out the user everywhere")
    r.add_argument("--email", required=True)
    r.add_argument("--password-stdin", action="store_true")
    r.set_defaults(func=reset_password)

    u = sub.add_parser("unlock", help="clear a login lockout")
    u.add_argument("--email", required=True)
    u.set_defaults(func=unlock)

    sub.add_parser("list-users", help="list accounts").set_defaults(func=list_users)

    t = sub.add_parser("create-agent-token", help="an API token for `testcli agent` (a service user, role Tester)")
    t.add_argument("--name", default="test runner", help="what the token is for (shown in the token list)")
    t.add_argument("--quiet", action="store_true", help="print only the token")
    t.set_defaults(func=create_agent_token)
    return p


async def _run(args: argparse.Namespace) -> None:
    try:
        await args.func(args)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(_run(args))
    except Abort as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\naborted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
