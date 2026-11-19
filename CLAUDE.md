# TestHarbor: context for Claude

TestHarbor is a self-hosted, open-source test case management tool, in the spirit of TestRail and BrowserStack Test Management.

- One instance serves one company.
- People work in it through the web UI. Automated tests report into it through a REST API, a CLI and an agent.

Read this file first, then `docs/PLAN.md`. It holds the design decisions and notes from every phase so far, Phase 1 to 14.

## Ground rules

- **Owner's notes.** `CLAUDE.local.md` (gitignored, if present) has the owner's preferences and local notes. Follow it.
- **Pushing.** Never push unless asked. Commit after each finished piece of work, on the current branch, and say which branch it was.
- **Private data.** Never commit real customer exports or data; use synthetic fixtures (`backend/tests/fixtures/`).
- **Credentials.** They live in `.env` (gitignored), never in `.env.example`.
- **First admin.** Only `docker compose exec backend python -m app.manage create-admin`. There are no admin credentials in env.
- **Data for checks.** Use throwaway projects (names starting with "E2E" are cleaned up by the e2e teardown), not existing data.
- **UI changes.** Check them visually with Playwright screenshots (see Verification), and check that nothing overflows at phone width.

## Stack and layout

| Path | What |
|---|---|
| `backend/` | Python 3.12, FastAPI, async SQLAlchemy 2.0 (asyncpg), Alembic, Pydantic v2, Postgres 16 |
| `frontend/` | Next.js 16 App Router, TypeScript, Tailwind v4, shadcn/ui (Radix), TanStack Query, dnd-kit, cmdk |
| `frontend/e2e/` | Playwright tests (separate package, run in the `e2e` compose service) |
| `cli/` | `testcli` (stdlib only): `upload` reports, `agent` runs tests on request, plus a pytest plugin (`@pytest.mark.case`) |
| `docs/` | `PLAN.md` (design and phase notes), `integration.md` (connecting autotests), `deployment.md`, `ci/` examples |
| `deploy/` | Caddyfile (HTTPS in prod) and `backup.sh` |

Backend map (`backend/app/`):

| Area | Where |
|---|---|
| Tables | `models.py` |
| API shapes | `schemas.py` |
| Shared queries (filters, sorting helpers, `record_result`, `remember_roles`) | `services.py` |
| CSV import (aliases, value mapping, BrowserStack/TestRail) | `case_import.py` |
| Report parsing | `junit.py`, `playwright_report.py` |
| Login, sessions, API tokens | `auth.py` |
| Admin commands | `manage.py` |
| Endpoints | `routers/*.py`; `jobs.py` handles "Run autotests" jobs and agents |

Frontend map (`frontend/src/`):

| Area | Where |
|---|---|
| API client and types | `lib/api.ts`, `lib/types.ts` |
| Pages | `app/(app)/projects/[projectId]/{cases,runs,settings}` |
| Feature components | `components/{cases,runs}` |
| Searchable pickers | `components/combobox.tsx` |
| Light / dark / system theme | `lib/theme.ts` |
| Auth gate, and `/api` rewrites to the backend | `proxy.ts`, `next.config.ts` |

## Running and testing

Everything runs in Docker. Node and npm are not installed on the host.

- **Ports.** `.env` sets `FRONTEND_PORT=3001` and `BACKEND_PORT=8001`. Use http://localhost:3001; the API is under `/api` and the docs at `/docs`.
- **Code is baked into the images, not mounted.** After changing code, rebuild with `docker compose up -d --build [backend|frontend]`.
- **Backend tests on the current source** (no rebuild needed). `make test-backend` instead runs the code baked into the image:
  ```sh
  docker compose run --rm -T -v "$PWD/backend:/app" --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 backend pytest -q
  ```
- **CLI tests:** `make test-cli`.
- **e2e:** `make e2e`, against the running stack. Rebuild the frontend first. It resets `e2e-admin@testharbor.local` to a random password.
- **Frontend typecheck:**
  ```sh
  docker run --rm -v "$PWD/frontend:/app" -w /app --user "$(id -u):$(id -g)" node:22-alpine npx tsc --noEmit
  ```
- **New migration.** Edit `models.py`, then:
  ```sh
  docker compose run --rm --no-deps -T -v "$PWD/backend:/app" --user "$(id -u):$(id -g)" backend alembic revision --autogenerate --rev-id 00NN -m "..."
  ```
  Review the result and add data steps if needed. Migrations apply on backend start. `tests/test_models.py` fails if models and migrations drift.
- **Adding an npm package:** `docker run … node:22-alpine npm install <pkg>@<exact version>` in `frontend/`.

At the time of writing, all tests pass: backend about 135, CLI 17, e2e 7.

## Verification (visual)

Take screenshots with the e2e container:

1. Write a spec into a scratch dir. It can import `./helpers` (`login`, `seedProject`).
2. Mount the dir as `/shots` and run as your own user: `--user "$(id -u):$(id -g)" -e HOME=/tmp`. Otherwise Docker creates root-owned dirs.
3. Copy the spec into `tests/zz-*.spec.ts`, run it, delete it, then Read the PNGs.

`seedProject` names projects "E2E …", so the teardown removes them.

## Domain notes

- **Hierarchy.** Project → Suite → Section tree → TestCase (shown as `C<id>`).
  - Runs hold `run_cases` (current status) and `test_results` (append-only history; the latest result wins).
  - Every route that takes a case ID accepts both `C142` and `142`.
- **Case fields.**
  - Built-in: state, owner, sprint, applicable roles (`roles`), automation status / progress / complexity, `updated_by`, description, `external_id` (for example BrowserStack's `TC-770`; re-import matches on it).
  - Custom fields: a JSONB list of `{name, value}`.
- **Applicable Roles** are kept per project (`projects.roles`). `role_key()` treats "Super Admin (SA)" as the same role as "Super Admin", and `remember_roles` unifies spellings across the project.
- **Imports.** CSV from TestHarbor, BrowserStack or TestRail (`case_import.py`), with a dry-run preview. JUnit XML and Playwright JSON go to `POST /api/projects/{id}/runs/import-junit`.
  - Playwright JSON carries the test IDs, which link each result to its test in the HTML report through the run's `report_url`.
- **Run autotests.** A job is queued in TestHarbor, and `testcli agent` on the machine with the tests claims it, runs its local command (adding `--grep` for selected case IDs), streams the log and uploads the report.
  - The server never sends commands, only case IDs. Keep it that way.
- **Auth.**
  - Roles are admin and tester. Passwords are hashed with argon2id.
  - Sessions are signed cookies, with a `session_version` for revocation. There is a lockout after failed logins.
  - Bearer API tokens act as their owner.
  - Managing users and tokens requires a session, not a token.

## Conventions and gotchas

- **Enums** are stored as VARCHAR with a CHECK constraint (`_enum()` in `models.py`). Adding a value needs a migration.
- **`eager_defaults=True`**, so timestamps come back after insert and update. Never lazy-load in async code; use `lazy="joined"` or explicit loads.
- **API style.**
  - On PATCH, `null` clears only the fields listed in `CLEARABLE_FIELDS`. Other fields ignore `null`.
  - Clear errors: 422 for bad input, 409 for conflicts, 404 for a missing project or case.
- **Frontend.**
  - Keep components in the shadcn style and use the color tokens in `globals.css`, so dark mode works.
  - Dialogs are built on `components/ui/dialog.tsx`. Its content is a grid whose children are `min-w-0`, so long content must scroll instead of stretching the dialog.
- **Docs.** Keep `README.md`, `docs/integration.md` and `docs/PLAN.md` up to date when behaviour changes. Add a phase section to PLAN.md for a new feature.
