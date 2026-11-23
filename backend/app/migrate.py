"""Bring the schema up to date (`alembic upgrade head`), with a dump of the database first.

Runs on every backend start (docker-entrypoint.sh). When the database is behind the code, that is an
update brought new migrations, the database is dumped to $BACKUP_DIR/pre-migrate before anything
changes. If the dump fails, nothing is migrated and the backend does not start.

A new, empty database is migrated without a dump. PRE_MIGRATE_BACKUP=false turns the dump off.
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    return cfg


async def current_revision(url: str) -> str | None:
    """The database's schema revision; None for a database that was never migrated."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            if not (await conn.execute(text("SELECT to_regclass('alembic_version')"))).scalar():
                return None
            return (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    finally:
        await engine.dispose()


def _chown(path: Path, owner: os.stat_result) -> None:
    try:
        os.chown(path, owner.st_uid, owner.st_gid)
    except PermissionError:
        pass


def dump(url: str, folder: Path, label: str, keep: int) -> Path:
    """pg_dump the database into folder (owned like the folder, readable by its owner only)."""
    u = make_url(url)
    folder.mkdir(parents=True, exist_ok=True)
    owner = folder.parent.stat()  # the backups folder's owner gets the files, so they can be copied off
    _chown(folder, owner)
    path = folder / f"testharbor-{datetime.now():%Y%m%d-%H%M%S}-{label}.dump"
    tmp = path.with_name(path.name + ".tmp")
    env = {
        **os.environ,
        "PGHOST": u.host or "localhost",
        "PGPORT": str(u.port or 5432),
        "PGUSER": u.username or "",
        "PGPASSWORD": u.password or "",
        "PGDATABASE": u.database or "",
    }
    old_umask = os.umask(0o077)
    try:
        subprocess.run(
            [os.environ.get("PG_DUMP", "pg_dump"), "--format=custom", f"--file={tmp}"], env=env, check=True
        )
    finally:
        os.umask(old_umask)
    tmp.rename(path)
    _chown(path, owner)
    for old in sorted(folder.glob("testharbor-*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        old.unlink()
    return path


def main() -> int:
    url = get_settings().database_url
    cfg = alembic_config(url)
    heads = ScriptDirectory.from_config(cfg).get_heads()
    current = asyncio.run(current_revision(url))
    behind = current is not None and current not in heads
    if behind and os.environ.get("PRE_MIGRATE_BACKUP", "true").lower() != "false":
        folder = Path(os.environ.get("BACKUP_DIR", "/backups")) / "pre-migrate"
        try:
            path = dump(url, folder, f"{current}-to-{'+'.join(heads)}", int(os.environ.get("KEEP_PRE_MIGRATE", "10")))
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"migrate: the dump before migrating failed, so nothing was migrated: {e}", file=sys.stderr)
            return 1
        print(f"migrate: schema {current} -> {', '.join(heads)}; the database was dumped to {path}", flush=True)
    command.upgrade(cfg, "head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
