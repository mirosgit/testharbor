"""Migrations must not lose data: a lint for destructive steps, and the newest migration run on real-looking data.

Migrations run by themselves when the backend starts, on databases that hold people's work. A step that
drops a table or column, or deletes rows, needs a `# data-loss-ok: <why>` comment in its upgrade(), so it
is a reviewed decision and not an accident. See CLAUDE.md, "Migrations".
"""

import ast
import asyncio
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app import migrate
from app.config import get_settings
from app.db import engine
from app.seed import seed

TEST_DB = get_settings().database_url  # conftest points it at the test database
VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
DESTRUCTIVE_OPS = {"drop_table", "drop_column"}  # op.* calls that throw data away
DESTRUCTIVE_SQL = re.compile(r"\b(DELETE\s+FROM|TRUNCATE|DROP\s+(TABLE|COLUMN))\b", re.I)


def _destructive_steps(path: Path) -> list[str]:
    source = path.read_text()
    upgrade = next(
        (n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None
    )
    if upgrade is None:
        return []
    found = []
    for node in ast.walk(upgrade):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        if name in DESTRUCTIVE_OPS:
            found.append(f"op.{name}")
        elif name == "alter_column" and any(k.arg == "type_" for k in node.keywords):
            found.append("op.alter_column(type_=…) (a narrower type can cut values)")
        elif name == "execute" and node.args:
            sql = ast.get_source_segment(source, node.args[0]) or ""
            if DESTRUCTIVE_SQL.search(sql):
                found.append(f"op.execute({sql[:60]})")
    return found


@pytest.mark.parametrize("path", sorted(VERSIONS.glob("*.py")), ids=lambda p: p.stem)
def test_destructive_migration_steps_are_marked(path: Path) -> None:
    steps = _destructive_steps(path)
    upgrade_src = path.read_text().split("def downgrade", 1)[0]
    if steps and "# data-loss-ok:" not in upgrade_src:
        pytest.fail(
            f"{path.name} throws data away in upgrade(): {', '.join(steps)}. Move the data first, or drop it in "
            "a later release once nothing uses it, and add '# data-loss-ok: <why>' to upgrade()."
        )


async def _snapshot() -> dict[str, tuple[int, set[str]]]:
    """Per table: the number of rows and the columns."""
    out = {}
    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
            )
        ).scalars().all()
        for t in tables:
            cols = (
                await conn.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": t}
                )
            ).scalars().all()
            out[t] = ((await conn.execute(text(f'SELECT count(*) FROM "{t}"'))).scalar_one(), set(cols))
    return out


async def _hash(table: str, cols: set[str]) -> str:
    """A hash of all rows of the table, over the given columns."""
    row = ", ".join(f'"{c}"' for c in sorted(cols))
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT md5(coalesce(string_agg(r::text, '|' ORDER BY r::text), '')) "
                    f'FROM (SELECT ROW({row}) AS r FROM "{table}") s'
                )
            )
        ).scalar_one()


async def test_newest_migration_keeps_existing_data(session, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Demo data at the previous schema; the newest migration keeps every row and every value."""
    await seed(session)
    await session.commit()
    cfg = migrate.alembic_config(TEST_DB)
    newest = ScriptDirectory.from_config(cfg).get_current_head()
    await asyncio.to_thread(command.downgrade, cfg, "-1")
    try:
        before = await _snapshot()
        hashes = {t: await _hash(t, cols) for t, (_, cols) in before.items()}
        assert sum(n for n, _ in before.values()) > 0

        monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
        assert await asyncio.to_thread(migrate.main) == 0

        after = await _snapshot()
        for table, (count, cols) in before.items():
            assert table in after, f"{newest} dropped the table {table}"
            assert after[table][0] == count, f"{newest} changed the number of rows in {table}"
            if cols <= after[table][1]:  # dropped columns can't be compared; the lint above catches those
                assert await _hash(table, cols) == hashes[table], f"{newest} changed existing values in {table}"
        # The database was behind, so it was dumped first.
        assert list((tmp_path / "pre-migrate").glob("testharbor-*.dump"))
    finally:
        await asyncio.to_thread(command.upgrade, cfg, "head")


async def test_no_migration_without_a_dump(session, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """If the dump before migrating fails, the schema is left as it was."""
    cfg = migrate.alembic_config(TEST_DB)
    script = ScriptDirectory.from_config(cfg)
    await asyncio.to_thread(command.downgrade, cfg, "-1")
    try:
        monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
        monkeypatch.setenv("PG_DUMP", "false")
        assert await asyncio.to_thread(migrate.main) == 1
        current = await migrate.current_revision(TEST_DB)
        assert current == script.get_revision(script.get_current_head()).down_revision
    finally:
        await asyncio.to_thread(command.upgrade, cfg, "head")


async def test_up_to_date_database_is_not_dumped(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("PG_DUMP", "false")  # would fail if it were called
    assert await asyncio.to_thread(migrate.main) == 0
    assert not (tmp_path / "pre-migrate").exists()
