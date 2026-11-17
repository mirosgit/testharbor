# TestHarbor: MVP plan

A self-hosted test case management tool and lightweight TestRail alternative. It has one workspace and one admin login, and API tokens for automation. The main goal is a solid autotest integration.

## Stack and layout

```
/backend    FastAPI, SQLAlchemy 2.0 async (asyncpg), Alembic, Pydantic v2, pytest
/frontend   Next.js App Router + TS, Tailwind, shadcn/ui, TanStack Query, dnd-kit, Playwright
/cli        pip package `testharbor-cli`: `testcli` command + pytest plugin (one install)
/docs       PLAN.md, integration guide, CI examples
docker-compose.yml   db (postgres:16) + backend (:8000) + frontend (:3000)
```

- The frontend proxies `/api/*` to the backend through a Next.js rewrite. Browser and API share one origin, so the session cookie works without any CORS setup.
- On start, the backend container runs `alembic upgrade head`. If `SEED_DEMO=true` (the compose default) and the DB is empty, it also seeds the demo data.
- OpenAPI docs are served by the backend at `http://localhost:8000/docs`.

## Data model

| Table | Key fields |
|---|---|
| projects | id, name, description, timestamps |
| suites | id, project_id, name, description |
| sections | id, suite_id, parent_id (nullable, self-FK), name, position |
| test_cases | id (shown as `C{id}`), section_id, title, preconditions, steps JSONB `[{action, expected}]`, expected_result, priority enum, type enum, tags `text[]` (GIN index), automation_status enum, automation_key (indexed, unique per project), position, timestamps |
| test_runs | id, project_id, name, description, source (manual/ci), branch, commit, build_url, closed, created_at |
| run_cases | run_id, case_id, current_status (cached latest status, default `untested`). This is run membership. |
| test_results | id, run_id, case_id, status, duration_ms, error_message, stack_trace, comment, created_at. Append-only history. |
| api_tokens | id, name, token_hash (sha256), prefix, created_at, last_used_at, revoked_at |

Enums:
- priority: low/medium/high/critical
- type: functional/regression/smoke/acceptance/performance/security/other
- automation_status: manual/automated/to_be_automated
- result status: passed/failed/blocked/skipped/retest/untested

## Phases (one commit each, on branch `mvp`)

1. **Skeleton.** Monorepo dirs, docker compose, backend app factory/config, models, first Alembic migration, idempotent seed: 1 demo project, 2 suites, nested sections, ~30 cases, 3–4 runs with mixed results.
2. **Core API + tests.** CRUD for projects/suites/sections/cases. Section tree endpoint, move case (section + position), case search/filter (title ILIKE, tags overlap, priority, type, automation status) with pagination, CSV/JSON import/export. pytest uses a separate `testharbor_test` DB.
3. **Frontend core.** Login, project list, suite page with the section tree on the left and the case list on the right, dnd-kit drag of cases onto sections, case editor (steps table with add/reorder/delete, markdown textarea with preview), filter bar.
4. **Manual runs.** Create a run from a whole suite, chosen sections, or the current filter. Run page has a progress bar and counts, per-case status and comment, and result history in a side panel. A case page shows its run history. Runs can be closed.
5. **Automation.**
   - API tokens: create, show once, revoke.
   - `POST /api/projects/{id}/runs/import-junit`, with the mapping logic.
   - `testcli upload`.
   - pytest plugin (`@pytest.mark.case("C142")`).
   - Docs for GitHub Actions and Bitbucket Pipelines.
   - Tests use real sample XML files from pytest, Playwright and Maven Surefire.
6. **Polish.** README (quick start, screenshots placeholder, autotest guide, roadmap), empty and loading states, Playwright smoke tests (login, create case, run a manual run).

## JUnit import rules

- Request: multipart `file`, plus query params `run_name`, `branch`, `commit`, `build_url`, `auto_create`, and optional `run_id`. Without `run_id` the import creates a new CI run. With `run_id` it appends to an open run, which is useful for parallel CI shards.
- Each `<testcase>` is mapped to cases in this order:
  1. **Case ID.** First from the `<property name="case_id" value="C142">` property (comma-separated values allowed). If there is no property, the importer looks for `C\d+` in the test name, preceded by a start, `_` or a non-alphanumeric character. A test that references several IDs records a result for each.
  2. **automation_key.** Candidate keys are compared in order:
     - an `automation_key` property (the pytest plugin writes the nodeid)
     - `classname::name`
     - `classname.name`
     - the pytest-style path `a/b.py::name`, rebuilt from the dotted classname
  3. **auto_create=true.** Creates a case in suite **"Unsorted"**, section **"Automated"**. Both are created on demand. The new case gets automation_status=automated and automation_key=`classname::name`, or the property value if present.
  4. Otherwise the test is reported as unmatched and no result is stored.
- Status mapping:
  - `<failure>` → failed
  - `<error>` → failed, with an "error" prefix in the message
  - `<skipped>` → skipped
  - anything else → passed
- Each result stores the duration, the message, and the stack trace or system-out.
- Response: `{run_id, matched, created, unmatched: [{name, classname}], results_total}`.
- Uploading to a closed run returns 409.

## Decisions on ambiguous points

- **Case number.** `C142` is the global primary key, as in TestRail. Case numbers are not counted per project.
- **Auth.**
  - The admin username and password come from env vars. Login sets an httpOnly signed session cookie.
  - The API accepts either that cookie or `Authorization: Bearer <token>`.
  - Tokens are stored only as hashes. Each token is shown once when it is created.
- **Steps.** Stored as JSONB on the case, not in a separate table. Cases have no versioning, and results don't snapshot case content.
- **Tags.** Postgres `text[]` with no tag table. The UI autocompletes from distinct tags already in use.
- **Run membership.** A `run_cases` row caches the latest status, so progress bars come from a single GROUP BY. The full history stays in `test_results`. A run can include cases from several suites in its project.
- **Closed runs.** Read-only, both in the UI and through the API.
- **Deleting.**
  - Deleting a section deletes its subsections and cases, after a confirm dialog that shows the counts.
  - Deleting a case removes it from runs and deletes its results.
- **Search.** Uses ILIKE on title (plus an exact `C123` lookup), not full-text search.
- **CSV format.**
  - Columns: `id, section_path ("Auth > Login"), title, preconditions, steps, expected_result, priority, type, tags, automation_status, automation_key`.
  - Steps are one cell with one step per line, written as `action => expected`.
  - Tags are comma-separated.
  - On import, sections are created from the path. A row whose `id` already exists in the suite updates that case; any other row creates a new case.
- **JSON export.** Lossless: the same structure as the API.
- **Markdown.** A textarea with Write/Preview tabs (react-markdown + remark-gfm), not a WYSIWYG editor.
- **CLI.** Reads `TESTHARBOR_URL` and `TESTHARBOR_TOKEN`. `--project` takes the project id. The pytest plugin ships in the same package through a `pytest11` entry point.
- **Backend tests.** Run with `docker compose run --rm backend pytest`, or locally against any Postgres via `TEST_DATABASE_URL`.

## Notes from implementation

- **Phase 1.** The frontend uses Next.js 16 and React 19 with TypeScript 5.9. TypeScript 7 is out, but Next does not support it yet.
- **Phase 1.** Host ports can be changed with `FRONTEND_PORT`, `BACKEND_PORT` and `DB_PORT`, for example when 8000 is already taken. OpenAPI docs are served at `:8000/docs` and are also proxied at `:3000/docs`.
