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
- **Phase 2.** The tag filter matches cases that have **all** selected tags. Priority, type and automation status match **any** of the selected values.
- **Phase 2.** Sections are returned as a flat list with `parent_id` and `position`, and clients build the tree from that.
- **Phase 2.** On import, a blank cell in an existing row keeps the case's current value.
- **Phase 2.** Bearer token checking is in place. Creating and revoking tokens comes in phase 5.
- **Phase 3.** The case detail and editor open in a side sheet next to the list. `?case=<id>` in the URL makes an open case linkable.
- **Phase 3.** Reorder steps with the up and down buttons. Drag-and-drop is only used for moving cases.
- **Phase 3.** Drag a case onto a tree node or a group header to move it to that section, or onto a row to put it at that position. If the dragged case is selected, all selected cases move together.
- **Phase 3.** The `cn` import that the shadcn CLI wrote was rewritten to `@/lib/utils`. The CLI had added an unrelated npm package named `cn`, which was removed.
- **Phase 4.** Runs can be created from selected cases, the current view (section and filters), a whole suite, or picked sections. Selections are combined server-side.
- **Phase 4.** The run page has quick status buttons per row, bulk status changes, and an execution side panel. "Save & next untested" moves to the next case that has no result. A closed run is read-only and can be reopened.
- **Phase 4.** Extra API beyond the spec: add cases to a run, remove a case from a run, and post results in bulk.
- **Phase 5.** One upload can contain several files (repeat the `file` field), and they all go into one run. `run_id` appends to an existing open run.
- **Phase 5.** When several tests map to one case in an upload (for example parametrized tests), every result is stored. The worst status is written last, so it becomes the current status. Each result's comment holds the test name.
- **Phase 5.** A test whose case ID belongs to another project is reported as unmatched, with the reason.
- **Phase 5.** Importing never changes existing cases. It does not overwrite automation keys or statuses.
- **Phase 5.** The CLI uses only the standard library. It detects the branch, commit and build URL in GitHub, Bitbucket, GitLab and Jenkins. The pytest plugin ships in the same package and also writes each test's node id as `automation_key`.
- **Phase 5.** The sample JUnit files are real reports, regenerated in containers by `backend/tests/fixtures/junit/generators/generate.sh`, so they contain no host details.
- **Phase 6.** The Playwright smoke tests are a small standalone package in `frontend/e2e`, run with `docker compose --profile e2e run --rm e2e`. A global teardown deletes the data they create.
- **Phase 6.** The backend logs a warning at startup when `SECRET_KEY` or `ADMIN_PASSWORD` still have their default values.

---

# Phase 7: users, roles and invites (production access for teams)

Decisions:
- **One instance per company.** There is no multi-tenancy. All users of an instance see all of its projects.
- **Testers are added with invite links.** No SMTP is needed.
- **Two roles.** Admin and Tester.

## Data model (one new migration)

| Table | Fields |
|---|---|
| `users` | id, email (unique, lowercased), name, password_hash (**argon2id**), role `admin`/`tester`, is_active, session_version, failed_logins, locked_until, last_login_at, created_at |
| `invites` | id, email, role, token_hash (sha256), purpose `invite`/`reset`, created_by, expires_at (72 h), used_at, revoked_at |
| `api_tokens` | + `user_id`. A token acts as its owner with the owner's role and stops working when the owner is deactivated. Tokens that already exist are **deleted** by the migration, because they have no owner. |
| `test_results` | + `user_id`, so results show who recorded them. Results from CI uploads show the token owner. |
| `test_runs` | + `created_by_id` |

## Auth and security

- **First admin.** It is created **only** with a command on the server:
  ```
  docker compose exec backend python -m app.manage create-admin
  ```
  The command asks for the email, name and password interactively. `--password-stdin` is available for scripts.
  - There are no admin credentials in `.env` and no "first visitor becomes admin" setup page.
  - Until the first admin exists, the login page shows this command.
  - Recovery commands: `manage reset-password`, `manage unlock` and `manage list-users`.
- **Login.** Login is by email and password.
  - Hashing uses argon2id.
  - Unknown emails still go through a dummy hash check, so response timing doesn't reveal which emails exist.
  - The error message is always the same generic one.
- **Brute-force protection.**
  - After 5 failed attempts, the account is locked for 15 minutes.
  - On top of that, each IP gets a limit of about 20 attempts per minute, kept in memory.
- **Sessions.**
  - The signed cookie contains `{uid, session_version}` and is checked against the database on every request.
  - Changing a password, using "sign out of all sessions", or deactivating a user takes effect immediately, because each bumps `session_version`.
  - Cookies are httpOnly and SameSite=Lax. They also get the Secure flag when `SECURE_COOKIES=true`.
- **Invites and password resets.** Both are one-time links: the token is stored only as a hash, expires after 72 hours, and is used once. An admin can revoke a link.
  - Password reset without SMTP: the admin clicks "Reset password", gets a link and sends it to the tester themselves.
- **Password policy.** At least 10 characters, and not the same as the email.
- **Security headers** (Next.js): `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Referrer-Policy`, and a basic CSP. HSTS is set by the reverse proxy.

## Permissions

| Action | Admin | Tester |
|---|---|---|
| Cases, suites, sections, import/export | ✓ | ✓ |
| Runs, results, JUnit upload | ✓ | ✓ |
| Own API tokens | ✓ | ✓ |
| Delete projects | ✓ | – |
| Users: invite, change role, deactivate, delete, reset password | ✓ | – |
| See and revoke other users' tokens | ✓ | – |

An admin cannot demote, deactivate or delete themselves. The system always keeps at least one active admin.

Deleting a user (`DELETE /api/users/{id}`, added later) removes them for good: their API tokens and reset links go (cascade), and runs, results, jobs and agents they made stay with the user set to null, so the history no longer shows their name. Deactivating keeps the name and can be undone, so the UI suggests it in the confirmation. The e2e teardown deletes the users the tests invite.

## UI

- The login page asks for an email.
- `/invite/<token>` lets the invited person enter a name and a password, then logs them in.
- **Settings › Users** (admin only):
  - a list showing role, status and last login
  - "Invite user", which gives a link to copy
  - pending invites, with revoke
  - change role, deactivate or reactivate, reset password
- **Settings › Profile**: change name or password, and "sign out of all sessions".
- The UI shows who did what: the header shows the current user, results show who recorded them, and runs show who created them.

## Deployment (`docs/deployment.md`)

- `docker-compose.prod.yml` adds **Caddy**, which gets HTTPS certificates automatically from Let's Encrypt for your domain. Only ports 80 and 443 are open to the outside; the database and backend are only reachable inside the server.
- A checklist: generate `SECRET_KEY`, set `SECURE_COOKIES=true`, set the admin password, configure the firewall.
- Backups with `pg_dump` on a cron schedule, plus restore steps.
- How to update to a new version (`git pull` + `docker compose up -d --build`; migrations run on startup).

## Breaking change for current installs

`ADMIN_USERNAME` and `ADMIN_PASSWORD` are removed. After updating, run `manage create-admin`. Existing API tokens are deleted by the migration.

- Managing tokens, users and invites, and changing your password, require a browser session. An API token cannot do these things, so a leaked CI token can't create new tokens.
- `make e2e` creates or updates an `e2e-admin@testharbor.local` account with a random password on every run.

## Steps (one commit each)

- **7a. Backend:** the migration, users and invites, roles on every endpoint, sessions, lockout, the `manage` CLI, and tests:
  - permissions for each role
  - invite expiry and one-time use
  - lockout
  - sessions being invalidated
  - a deactivated user's tokens stopping working
- **7b. Frontend:** login, invite acceptance, Users and Profile pages, "who did it" in the UI, security headers, and updated e2e tests including the invite flow.
- **7c. Deployment:** `docker-compose.prod.yml` with Caddy, `docs/deployment.md`, and README updates.

## Notes from implementing Phase 7

- **Per-IP login limit.** It needs a reverse proxy to see real client IPs. Next.js rewrites forward the client's own `X-Forwarded-For` unchanged and don't add one of their own.
  - Without a reverse proxy, every request appears to come from the frontend container. This only weakens the per-IP limit; the per-account lockout still works.
  - In production, Caddy overwrites `X-Forwarded-For` with the real client IP. The prod compose file publishes only Caddy's ports.
- **Session lifetime.** Sessions now last 14 days instead of 30.

## Phase 8: import from other tools

- **Target section.** The import dialog asks where to put the cases: an existing section, or a new top-level section (named after the file by default; an existing one with the same name is reused).
  - With "keep folders" (the default), folders from the file are recreated inside that section. With it off, every case goes directly into it.
  - The API without a target keeps the old behaviour: folders at the top level, and cases without a folder go to "Imported".
- **Column matching.** Columns are matched by name, ignoring case and spacing, with aliases for TestHarbor, BrowserStack and TestRail exports.
  - Values are mapped to TestHarbor's options: `Cannot Be Automated` becomes manual, `1 - Critical` becomes critical, `Undefined` becomes the default.
  - Values that can't be mapped are imported with the default and listed as warnings. Columns with data that has nowhere to go are listed as ignored.
- **External ID.** A new `external_id` field on cases stores ids from other tools (`TC-770`). Re-importing the same file updates the matching cases in the suite instead of duplicating them, and search finds cases by external id.
  - An `ID` column in a foreign file, such as TestRail's `C123`, is always treated as an external id. Only TestHarbor's own export, recognised by its `section_path` column, uses `id` as a TestHarbor case id.
- **Text cleanup.** Hard-wrapped lines (the 4-space-indented continuation lines in BrowserStack exports) are joined back together. A `Description` column goes on top of the preconditions. Expected results stay one case-level list, because BrowserStack exports don't pair them with individual steps.
- **Delimiters.** Semicolon and tab delimited CSV files are detected.
- **Automation status.** When a BrowserStack file has both `Automation Status` and `Automation Status (custom)`, the standard column is used.
- **Test data.** The test fixture is a synthetic file in the same shape as a BrowserStack export. Real exports contain employee names and internal links, so they shouldn't be committed.

## Phase 9: custom fields

- **Model.** Cases have free-form custom fields, stored as JSONB in display order: `[{name, value}]`, with a GIN index. Names are unique per case (case-insensitive). Empty values are dropped.
  - Fields are not defined per project. That is enough for imported metadata (Owner, State, Sprint, Created At…).
  - Typed, project-level field definitions (required fields, dropdowns) could be added later.
- **Import.** CSV columns with data but no built-in field become custom fields.
  - The import dialog runs a dry run (`dry_run=true`) and shows them as checkboxes.
  - Tool-internal columns are unchecked by default: Folder ID, Template Type, Template Name, Project Name, Test Case URL.
  - Re-importing merges fields: imported fields replace fields with the same name, and fields added by hand are kept.
- **Export.** CSV export adds one column per field name, so an export can be imported back without losing fields.
- **Filtering.** API: `?field=Name=Value`, repeatable. Several values for one name match any of them; different names must all match. UI: the "Fields" filter.
- **Dates.** Superseded by Phase 10: Created At / Last Updated At now set the case's own timestamps.

## Phase 10: built-in case fields, dark theme

- **Model (migration 0005).** New columns on `test_cases`:
  - `state`: draft / active (default) / pending_review / outdated / rejected.
  - `owner`, `sprint`: free text, with suggestions. Owner suggestions include active users' names. It is deliberately not a user FK: imported owners are often people without an account.
  - `roles`: `varchar[]` with a GIN index. Case is kept as entered; duplicates are removed case-insensitively.
  - `automation_complexity`: not_applicable / low / medium / high.
  - `automation_progress`: not_automated / in_progress / automated / cannot_be_automated. BrowserStack's custom "Automation Status (custom)" column maps here; the standard "Automation Status" still maps to `automation_status`.
  - `updated_by`: display name, set on create/edit, or taken from "Last Updated By" on import.
- **Data migration.** Values that earlier imports kept as custom fields with these names are moved into the columns. Values that can't be mapped stay as custom fields.
- **Import.** Header aliases for the new fields. Values are mapped with tolerance for typos ("Not Aplicable"). Dates are parsed as ISO or US `MM/DD/YYYY HH:MM[:SS]`; no timezone means UTC. Created At / Last Updated At set `created_at` / `updated_at`. In TestHarbor's own CSV export every extra column is selected by default.
- **API.** Filters `state`, `automation_complexity`, `automation_progress`, `owner`, `sprint`, `role` (repeatable; owner/sprint/role values are not split on commas). `GET /api/projects/{id}/case-values` returns owners, sprints and roles for autocomplete.
- **UI.** The case editor has State, Owner, Sprint, Automation progress, Automation complexity and Roles. The case card shows them, plus Created and Last updated (with who). The list shows every case's state in its own column. The "Fields" filter lists the built-in fields first, then custom fields.
- **Dark theme.** It uses the existing `.dark` tokens. An inline `<head>` script applies the stored choice (`localStorage["testharbor-theme"]`: light, dark, or absent for system) before the first paint. The toggle is in the header and on the login/invite pages.

## Phase 11: project roles, bulk edit

- **Project roles (migration 0006).** `projects.roles` is a `varchar[]` in display order, seeded from roles already used on the project's cases. It is edited in the new project Settings page (`PATCH /api/projects/{id}` with `roles`).
  - `POST /api/projects/{id}/roles/rename` renames a role in the list and on all cases; renaming onto an existing role merges them.
  - Removing a role from the list leaves it on cases.
  - Roles set on cases (editor, API, import, bulk edit) that are not in the list are appended to it, so the list stays complete.
  - The case editor picks roles with checkboxes and can add a new one inline.
- **Bulk edit.** `POST /api/cases/bulk-update` takes `{case_ids, set: {...}, add_tags, remove_tags, add_roles, remove_roles}`.
  - Omitted fields stay unchanged; `null` clears owner, sprint, automation progress and automation complexity.
  - All cases must be in one project.
  - Sets "last updated by".
  - UI: "Edit" in the selection bar opens a dialog where every field defaults to "Keep as is".
- **Import target.** The default is now "Top level (folders from the file)": `Billing>Invoices` becomes `Billing › Invoices` at the top of the suite, not inside a wrapper section. "New section…" and existing sections are still offered.

## Phase 12: pickers, sorting, pagination

- **Pickers.** Owner, Sprint, Tags, Roles and custom field names/values use searchable comboboxes (cmdk, the shadcn/ui Combobox pattern) instead of native `<datalist>`. Typing a new value offers "Use …" / "Add …" after the matches.
- **Sorting.** `GET /api/projects/{id}/cases?sort=…&order=asc|desc` sorts within each section. Sections stay in tree order (`array_position` over the tree order), so grouping and drag-and-drop keep working. Keys: manual (drag order), id, title, priority, type, state, automation_status, owner, sprint (natural order), created_at, updated_at. Empty values go last. The runs list has `sort=created_at|name|closed_at`. The run page sorts its cases on the client.
- **Pagination.** The case list is paged on the server (50/100/200/500 per page; the size and the sort are remembered per browser). Empty sections are shown on the page where they fall in tree order. Selection and "select all in section" apply to the current page.
- **Case form (BrowserStack layout).** One column: Title*, Description, Preconditions, Steps (Step / Expected Result), Expected Result. Then a "Details" grid (Section, Owner, State, Priority, Type of Test Case, Automation Status, Tags) and "Custom Fields" (Automation Complexity, Automation Progress, Applicable Roles, Sprint No., Automation Key, other fields).
- **Description (migration 0007).** It is its own field; imports no longer merge it into Preconditions. Existing cases are fixed by re-importing the file.

## Phase 13: links into test reports

- **Playwright JSON (`app/playwright_report.py`).** The import endpoint also accepts Playwright's JSON reporter output (sniffed by content). It is turned into the same records as JUnit, with Playwright-JUnit-style names (`Describe › title`, classname = spec file), so matching and automation keys are identical. Case IDs come from a `case_id` annotation, `@C123` tags or the title. ANSI colours are stripped. Flaky tests count as passed, with a note.
- **Links (migration 0008).** `test_runs.report_url` is the run's HTML report: an import param (`--report-url`), editable on the run page. `test_results.report_link` is either an absolute http(s) URL (a `report_url`/`link` property in JUnit) or `#?testId=<id>` (the Playwright test id, which equals the HTML report's `testId`; verified on a real 1.65 report). It is resolved against the run's current report URL when served, so moving the report only needs the run's URL updated. Only http(s) URLs are accepted.
- **UI.** The run header has a "Report" button. Each run row has an icon linking to the test's page. Results show "Open in report", and case history links too.
- **One role, several spellings.** `role_key()` compares roles case-insensitively and treats a trailing abbreviation as part of the same role: "Super Admin (SA)" is "Super Admin". The abbreviation must start with the name's first letter and its letters must appear in the name in order, so "Admin (read-only)" stays its own role. When roles are written (case edit, bulk edit, import), `remember_roles` unifies the spellings in the project list and on every case of the project, preferring the spelling with the abbreviation (as BrowserStack exports it).

## Phase 14: run autotests from TestHarbor

- **Model (migration 0009).**
  - `automation_jobs`: `run_id`, `status` (queued, running, finished, error, cancelled), `case_ids` (empty means all tests), agent, exit code, message, the tail of the log (512 KB), and timestamps including `heartbeat_at`.
  - `automation_agents`: one row per project and agent name, with `last_seen_at`, for the "agent online" indicator.
- **Flow.** A user starts a job; without `run_id` a new CI run is created, holding the selected cases. One job can be active per run. `only_failed` takes the run's failed cases. An agent polls `claim`, which atomically takes the oldest queued job (`FOR UPDATE SKIP LOCKED`) and records itself as seen. It posts output to `progress`; the answer says whether the job was cancelled. Finally it uploads the report with `run_id` (which now also fills in the run's branch, commit and build when they are empty) and calls `finish`. Running jobs with no heartbeat for 2 minutes become errors when jobs are next read.
- **Security.** The server only sends case IDs. The command comes from the agent's command line. Selected cases become a `--grep` regex built from integers only, and the agent passes it as an argv element with no shell.
- **Agent (`testcli agent`).** Uses only the standard library. Removes the old report before each run, so a stale report is never uploaded. Strips ANSI codes. Stops the tests when the job is cancelled in TestHarbor, and reports the job as interrupted on Ctrl+C or SIGTERM. Verified end to end with real Playwright tests in Docker.
- **UI.** "Run autotests" on the runs page, in the case selection bar and on a run page. The dialog shows whether an agent is online and how to start one. The run page has a panel with status, elapsed time, live output and Cancel.


## Phase 15: run options and results per configuration

Built to run test suites that need choices per run (an environment, roles, a suite, a browser) from TestHarbor, without TestHarbor knowing about pytest or roles.

- **Model (migration 0010).**
  - `automation_agents.options` (JSONB): the run options the agent offers, refreshed on every `claim`.
  - `automation_jobs.params` (JSONB): the values chosen for a job, e.g. `{"ENV": "qa", "ROLES": ["admin"], "HEADED": true}`.
  - `test_results.config`: the configuration a result ran in (a role, a browser, a Playwright project).
- **Run options.** `testcli agent --options FILE` reads `{"options": [{name, label, type, choices, default, hint}]}`. `type` is `choice`, `multi` or `bool`. `name` is an environment variable of the agent's command. It must be UPPER_CASE and cannot be `PATH`, `LD_*`, `PYTHON*`, `BASH_ENV`, `TESTHARBOR_*` and similar. The dialog shows the options of an online agent (else the last agent seen with options) and remembers the last choice per project in the browser.
- **Security.** The server still never sends a command. It stores the values a person picked. The agent checks every value against its own file before running. An unknown option or a value outside its choices fails the job with nothing run. Then it sets one variable per offered option: a choice as is, a multi space-separated, a bool as `1` / `0`. `TESTHARBOR_TOKEN` is no longer passed to the tests.
- **Reports per job.** `--report` and `--report-url` may contain `{job_id}`, and `--report` may be a glob. Every matching file written during the job is uploaded as one import, for example a JUnit file per role in `reports/t{job_id}/*/junit.xml`. Files older than the job are ignored, so job ids repeating after a database reset never upload stale results.
- **Config per result.** A `config` / `configuration` JUnit property, or the project of a multi-project Playwright JSON report, fills `test_results.config`. One scenario that ran as several roles is one case with one result per role, each labelled with its role. The worst status stays the current one.
- **A test project's side** (example: a pytest-bdd suite with one process per role): tags such as `@case:C142` on scenarios become `case_id`, `automation_key` and `config` (role name) JUnit properties. Its runner reads `TESTHARBOR_CASE_IDS` / `TESTHARBOR_JOB_ID` and writes the options file, and a small script starts the agent.

## Phase 16: catalog of automated tests, synced into cases

Goal: run single automated tests from TestHarbor by selecting their cases, without hand-written case IDs in the tests and without duplicating the manual cases.

- **Model (migration 0011).**
  - `automation_catalogs`: one per project, the tests the agent last reported. Each test has `key`, `title`, `path`, `description`, `preconditions`, `steps`, `roles`, `tags` and `case_ids`.
  - `test_cases.catalog_managed`: the case was created from the catalog and follows its test.
- **Flow.** `testcli agent --catalog FILE` uploads the catalog when it starts (`PUT …/automation/catalog`), and nothing else changes then. The cases page shows "Autotests: N to sync". The preview (`GET …/automation/catalog`) and apply (`POST …/catalog/apply`, guarded by the catalog's `uploaded_at`) do the rest (`app/catalog.py`).
- **Matching.** Case ids the test is tagged with come first, then the automation key, then a new case. A tagged case wins the key from another case; a catalog case that loses its key becomes Outdated.
- **Who owns what.**
  - Catalog cases: title, description, preconditions, steps, roles and tags follow the test on every sync. Priority, owner, sprint, custom fields and the section stay the person's.
  - Manual cases linked to a test: only `automation_key` and `automation_status` are set.
  - A catalog case whose test is gone becomes Outdated, and comes back to Active if the test returns. Nothing is deleted.
- **New cases** go into the "Autotests" suite, in sections from the path (domain › feature). Type is smoke or regression from the tags. Roles take the project's spelling, as on import. Line breaks in steps become Markdown hard breaks.
- **No duplicates.** For each new test, the preview suggests up to 3 manual cases with similar titles: word overlap plus sequence ratio, ≥ 0.45. The person picks per test: create a case, link to a suggestion, link to any case by ID, or skip. Only manual cases can be link targets.
- **Running selected cases.** The claim answer now carries the automation keys of the job's cases. The agent writes `{"case_ids", "automation_keys"}` to a temp file named by `TESTHARBOR_SELECTION`. A custom runner selects its tests by key, or by a case tag. Outline rows share the scenario's key, so they become one case with a result per row and role.
- **Autotests page** (`/projects/{id}/autotests`, a tab next to Test runs). It holds the tree of the catalog's tests (path › test) with search and tri-state check boxes, the agent's status and run options, **Run selected** / **Run all**, and the recent jobs. Tests without a case are shown but can't be picked, and the page offers the sync, because their results would have nowhere to go. "Run autotests" on the runs page leads here; the dialog stays for selected cases on the cases page and for re-running a run's failed cases. The project header now fits phone width: the nav scrolls, and the project name is truncated.

## Phase 17: anyone can connect: testharbor.toml, built-in catalogs, local agents

Goal: any team connects its autotests in a few minutes. Two kinds of agents: local (a folder as it is) and, next, server (a git branch in a clean checkout).

- **`testharbor.toml`** (or `.json`) next to the tests holds `url`, `project`, `framework`, `command`, `report`, `select`, `catalog`, `options`, `prepare`, `env`, `name`, `poll`. `testcli agent` finds it in the folder or a parent and needs no flags.
  - Order of precedence: flags, then the environment, then the file, then the `TESTHARBOR_*` lines of the `.env` next to it, which are read as plain text and never executed.
  - The token is never in the file. An unknown setting is an error.
- **Presets per framework.**
  - `playwright`: `npx playwright test --reporter=list,json,html`. The JSON report goes to `reports/results.json` (via `PLAYWRIGHT_JSON_OUTPUT_NAME`). The selection is a `--grep` of the selected tests' titles plus `C<id>` tags. The catalog comes from `--list --reporter=json`.
  - `pytest`: `--junitxml=reports/junit.xml`. The selection is node ids as arguments. The catalog comes from `--collect-only -q`, one test per node id without parameters, with a title from the function name.
  - `custom`: everything from the file. The selection is only the `TESTHARBOR_SELECTION` file.
- **Keys line up with reports.** The Playwright JSON import sets `automation_key` = `<file>::<describe › title>`, the same in every project, so all projects of a test land in one case with a result per project. JUnit keys of parametrized tests also match without the `[...]` part.
- **`testcli init`** detects Playwright or pytest (and uv / poetry for pytest), writes `testharbor.toml`, and warns if `.env` is not git-ignored.
- **`prepare`** runs at start and after every job, then options and catalog are re-read and sent, so changed tests show up without restarting the agent.
- **Agent info (migration 0012).** `automation_agents.info` holds the mode, folder (`~`-shortened), branch, short commit, uncommitted changes and framework, shown in the agent status.
- **UI.** Autotests › **Connect autotests** walks through install, token, `testcli init`, `.env` and `testcli agent` for the chosen framework, with the formats of the catalog and the selection for custom runners. An empty Autotests page leads there.

## Phase 18: server runner (a git branch), choosing where a run goes

Goal: deploy TestHarbor on a server, pick a branch of the test repository (e.g. on Bitbucket) when starting a run, and the latest commit of that branch runs, with little setup. Local agents keep running a folder as it is.

- **Server agent** (`testcli agent --repo URL`, `cli/src/testharbor_cli/repo.py`).
  - It keeps one clone (`--no-checkout`) in its workdir and fetches before every job. Each job gets a fresh worktree of `origin/<branch>`, detached at the latest commit, which is removed after the run.
  - `testharbor.toml` is found at the root of the checkout or, if there is only one, up to two levels down; `--repo-path` picks one.
  - The tests' secrets are copied in: `--env-file` becomes `.env` next to the config, and the `--secret-files` folder is copied at the same paths.
  - Then `setup` (a new key, server only) runs, followed by `prepare`, options and the tests. Output goes into the job log, and the run gets the branch and commit.
  - Options and the catalog come from the default branch (re-sent after a run on it). Branches are re-listed every minute.
  - HTTPS credentials (`TESTHARBOR_GIT_TOKEN`, `TESTHARBOR_GIT_USER`, default `x-token-auth`) reach git only through `GIT_ASKPASS`. They are masked in errors and never passed to the tests, like `TESTHARBOR_TOKEN`.
- **Choosing where a run goes (migration 0013).**
  - `automation_jobs.target_agent` and `branch` exist; a branch name is validated (git-safe characters, no `..`, no leading `-`).
  - `claim` gives an agent only jobs that are untargeted or targeted at it, and never gives a job with a branch to a local agent.
  - Agents report `info.mode` (`local` / `repo`), and a server agent also its repository (without credentials), default branch and branches.
  - The claim answer and the jobs list carry both fields.
- **Docker** (`deploy/runner/`, the `runner` service of `docker-compose.yml`, profile `runner`).
  - The image is based on the Playwright image (Node, browser libraries) plus git, uv 0.13.7 and testcli. `/root/.cache` is a volume for uv, Pythons and browsers.
  - Settings come from `RUNNER_*` in `.env`, and secrets from `runner-secrets/` (`tests.env`, `files/`, `ssh/`), mounted read-only.
  - `make runner` / `make prod-runner` start it, and `make runner-token` creates a token for the "Autotests agent" service user (`python -m app.manage create-agent-token`). Guide: `docs/runner.md`.
- **Local secrets.** A new `secrets` key holds commands a local agent runs in the user's terminal when it starts, such as an MFA prompt for a short-lived session; `--no-secrets` skips them. Server agents skip them and say so in the log.
- **Expected Result.** Catalog tests may carry `expected_result`; otherwise the last step's expected result fills the case's Expected Result. It is a managed field of catalog cases.
- **UI.**
  - The Autotests page has **Run on**: the online agents, local ones with their folder and branch, server ones with their repository. A server agent also gets a **Branch** picker (search, default branch first).
  - The last choice is remembered per project. Jobs show their branch and agent.
  - Connect autotests is split into "On my computer" and "On a server". It covers secrets in both.
- **Verified end to end:**
  - the image built and ran against the local stack with a git repository: tests in a subfolder, a branch with an extra failing test, a secrets file read by a test;
  - `uv sync` worked in the container;
  - results and branch/commit arrived on the run.

## Phase 19: links from results to the HTML report

- **`report_html`** (a `testharbor.toml` key; the Playwright preset writes `reports/html/{job_id}/index.html` via `PLAYWRIGHT_HTML_OUTPUT_DIR`) names the report page.
  - A local agent serves the page's first folder (never the whole project) on 127.0.0.1:`report_port` (default 9323, or a free port) in a thread (`cli/.../serve.py`). It sets the run's `report_url` to the page, with `{job_id}` filled in.
  - A server agent copies the page's folder out of the checkout before removing it, keeps the latest 50 and serves them on 9323 (published on 127.0.0.1 by default). It links runs to `TESTHARBOR_REPORTS_URL/job-<id>/<page>`.
- **Per-result links** use the existing `pw_test_id` → `#?testId=` mechanism. A project that builds its own Playwright report can put the report's test id into a `pw_test_id` JUnit property to get the same per-test links.
- `{job_id}` is also filled into the `env` values of the config.

## Security fix: automation keys never become command options

The security review found that in `select = "args"` mode (the pytest preset) the agent appended the job's automation keys straight to the pytest argv. Any user can edit a case's automation key, so a tester could inject options: `--basetemp=<dir>` deletes a folder, `--junitxml=<file>` overwrites a file, `--log-file*` writes chosen text (code execution through a `.pth`), and `--tx` runs commands with pytest-xdist.

- **Agent (the trust boundary).** In `args` mode a key must be a plain relative test id: no leading `-`, no absolute or drive path, no `..` (`safe_test_id`). It must also be one of the agent's own tests: `known_keys` from its catalog, and for a server agent from the job's checkout. Otherwise the job fails with "refusing to run" and nothing starts. `grep` mode escapes keys into one `--grep` value. `env` mode hands them to the user's runner, which must validate them against the tests it knows.
- **Server (defence in depth).** `automation_key` (cases, CSV/JSON import) and catalog test keys are rejected with 422 if they start with `-`. A JUnit auto-created case gets no automation key in that case.

## Deleting runs: admins only, several at once

- `DELETE /api/runs/{id}` now needs the admin role. It was open to everyone before.
- `POST /api/projects/{id}/runs/delete` (`{"ids": [...]}`, admins) deletes several runs of the project. Ids of other projects are ignored. Results, run cases and autotest jobs go with them (database cascades).
- If a running job's run is deleted, the agent's `progress` call gets 404. The agent treats that as a cancel and stops the tests.
- UI: admins get check boxes and **Delete** in the runs list. "Delete run" in a run's menu is shown to admins only.
- Local agents: a failing `secrets` command is a warning, and the agent still starts and serves the reports.

## Reports stored in TestHarbor (replaces serving them from the agent)

Reports served by the agent only opened while that agent ran, and only on that machine, so they now live in TestHarbor.

- **Upload.** After uploading the results, the agent zips the folder of `report_html` (no symlinks) and sends it with `PUT /api/runs/{id}/report?page=…` (any signed-in user or token).
- **Storage** (`app/reports.py`). TestHarbor unpacks the zip into `REPORTS_DIR/<run id>` (the `reports-data` volume) and replaces the run's earlier report.
  - Unsafe members are skipped: absolute paths, `..`, drive letters, symlinks.
  - Limits: 20 000 files, and `MAX_REPORT_MB` (500) unpacked, counted while writing because the sizes in the zip's directory can lie.
  - The run's `report_url` becomes `/r/<token>/<page>`; the token is the run id signed with SECRET_KEY. Results keep their `#?testId=` links.
- **Serving.** `GET /r/{token}/{path}` (Next rewrites `/r/*`, and the session gate skips it) needs no cookie: the signed path is the access, so the report's relative files load.
  - Every response is `Content-Security-Policy: sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads allow-modals`, without `allow-same-origin`, plus `nosniff` and `no-referrer`. A report (HTML and JavaScript written by the tests) runs in an opaque origin, with no access to TestHarbor's cookies, storage or API.
  - HTML pages get a storage shim first, because Playwright's report reads localStorage and the sandbox would throw. Service-worker trace viewers don't run; trace files download.
- **Cleanup.** Deleting a run, several runs or a project deletes their reports.
- **Removed.** The agent's local report server (`serve.py`, `report_port`) and the runner's report port/volume.
- **Verified in a browser:** a merged Playwright report of a role-based suite opens from "Open in report" right at the failed test (errors with code, steps, retries), with no console errors.

## Retries in JUnit reports

pytest-rerunfailures (and similar) writes a test once per attempt. The earlier attempts often have no failure element, so they looked like passes, and a case got a bogus passed result next to the real one. `parse_junit` now keeps only the last attempt of a test (same classname, name and file within one report). If an earlier attempt needed a retry and the last one passed, the result says "Flaky: passed on retry N". If every attempt failed, its log starts with "Failed in all N attempts".

- **Upload size.** Next.js cuts proxied request bodies at 10 MB by default, so a larger report failed with a 500 and the run got no link. `experimental.proxyClientMaxBodySize` is now `500mb` (matching `MAX_REPORT_MB`). In production Caddy allows 500 MB on `/api/runs/*/report` and keeps 60 MB for everything else.

## Phase 20: case text from the tests' code, Pending review

Cases created from autotests used to have only a title (built-in catalogs) and went straight to Active.

- **States.** A catalog case is created as Pending review. When a sync rewrites its text (any managed field), it goes back to Pending review, so nobody misses the new text. A moved automation key alone keeps the state. A removed test's case comes back from Outdated as Pending review. The preview lists `state` among the changes.
- **Text from the code** (`cli/src/testharbor_cli/describe.py`). Only what people wrote in the tests is used, no generated prose. A test that states nothing gets "Automated test in `file:line`".
  - Docstrings and comments: prose is the description; `Preconditions:` / `Steps:` / `Expected result:` sections (unindented headers) fill the fields; steps are `1. action -> expected` items, with an `Expected: …` line under a step; Given/When/Then lines map like Gherkin.
  - Gherkin (pytest-bdd and docstrings): Given → preconditions, each When starts a step, Then → its expected result.
  - Playwright: the comment above `test(…)` (found by the `line` / `column` of `--list --reporter=json`, files under `config.rootDir`), `test.step` titles as steps (bracket matching that skips strings and comments; nested steps become sub-items), annotations `description` / `precondition` / `expected` / `issue` (deduplicated across projects).
  - pytest: a docstring's first short line becomes the title. Markers become tags (run-control markers such as `parametrize` or `skip` are left out). `case` markers and `C142` / `case:C142` names or tags give `case_ids`.
  - pytest details come from `catalog_plugin.py`. The agent copies it into a temp dir, prepends that to `PYTHONPATH` and runs `pytest --collect-only -p testharbor_catalog` with `TESTHARBOR_CATALOG_OUT`. It reads docstrings, markers and pytest-bdd templates (`scenario_wrapper_template_registry`, or `__scenario__` in older versions). If loading the plugin fails, the agent falls back to plain node ids.
- **Checked.** CLI tests cover both a real nested pytest run and a real pytest-bdd Scenario Outline. Real `playwright test --list` output (v1.65, two projects) was checked by hand.

