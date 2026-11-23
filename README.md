# TestHarbor

TestHarbor is a lightweight, self-hosted, open-source alternative to TestRail. It holds test suites,
test cases and test runs, and it integrates directly with automated tests. You can upload JUnit XML
from any framework, link tests to cases with `C123` IDs, and see manual and CI results side by side.

<picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/dashboard-dark.png"><img src="docs/screenshots/dashboard.png" alt="Project dashboard: coverage, review queue, pass rate, failing and flaky cases"></picture>

<table>
  <tr><th>Test cases</th><th>Autotests</th></tr>
  <tr><td><picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/cases-dark.png"><img src="docs/screenshots/cases.png" alt="Test cases"></picture></td><td><picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/autotests-dark.png"><img src="docs/screenshots/autotests.png" alt="Autotests: pick tests and run them through an agent"></picture></td></tr>
  <tr><th>Test runs</th><th>A CI run with a failure</th></tr>
  <tr><td><picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/runs-dark.png"><img src="docs/screenshots/runs.png" alt="Test runs"></picture></td><td><picture><source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/run-dark.png"><img src="docs/screenshots/run.png" alt="A CI run with a failure"></picture></td></tr>
</table>

## Features

- **Dashboard per project.** Automation coverage (overall, by area and by priority), the Pending
  review queue, pass rate per day with the change against the previous period, the cases that
  fail most or flip between passed and failed, recent runs and the autotests catalog. Every number
  links to the cases or runs behind it.
- **Test cases in a tree.** Suites contain nested sections, and cases are listed on the right,
  similar to TestRail. You can drag and drop cases, including several at once, between sections.
- **Case editor.** It has a steps table (action and expected result), preconditions, priority,
  type, tags and automation status, plus state (Draft, Active, Pending review, Outdated,
  Rejected), owner, sprint, applicable roles, automation progress and automation complexity.
  Created / last updated dates and who last changed the case are tracked. Text fields support
  Markdown. Any number of **custom fields** can be added on top, and you can filter by them.
- **Search and filters.** Search by title or `C123`, and filter by tags, priority, type,
  automation status, state, owner, sprint, roles and custom fields.
- **Applicable Roles.** Each project keeps a list of user roles (Settings → Applicable Roles); cases pick from
  it. Renaming a role renames it in every case.
- **Bulk edit.** Select cases and change state, priority, type, automation fields, owner or sprint,
  or add/remove tags and roles on all of them at once.
- **Light and dark theme**, or follow the system setting.
- **Manual test runs.** Create a run from a whole suite, from chosen sections, from the current
  filter, or from selected cases. A case that was forgotten can be added to an open run later
  (**Add cases**: search, single cases or whole sections), marked New, and run right away: executed by
  hand, or with autotests through **Add & run autotests** ("Just added"). The run page shows a progress bar and per-status counts. Each
  case can have several results; the most recent one is its current status. "Save & next untested"
  moves you to the next case without a result.
- **Deleting runs** is for admins, one at a time or several from the runs list.
- **Run history per case.** Each case shows every run it was in and its result there.
- **Import and export.** Cases can be imported and exported as CSV (spreadsheet-friendly) or JSON
  (lossless). Import also reads **BrowserStack Test Management and TestRail CSV exports**:
  - Folders become sections. You choose the target section, or a new one.
  - Their IDs (`TC-770`) are kept, so re-importing updates cases instead of duplicating them.
  - Columns or values that can't be mapped are listed after the import, not silently dropped.
  - State, Owner, Sprint No., Applicable Roles, Automation Complexity, "Automation Status
    (custom)", Created At, Last Updated At and Last Updated By go into the matching built-in fields.
  - Before importing, a preview shows what will be created or updated. Other extra columns can
    be kept as custom fields.
- **Automation**
  - REST API with OpenAPI docs at `/docs`, plus API tokens.
  - `POST /api/projects/{id}/runs/import-junit` accepts JUnit XML from pytest, Playwright, Jest,
    JUnit/TestNG, Cypress and others.
  - Tests are linked to cases by a case ID, then by automation key. Optionally, a case is created
    automatically for any test that doesn't match.
  - `testcli upload` CLI, which detects the branch, commit and build URL in CI.
  - Playwright's JSON report is accepted too: each case in the run links to its test in
    Playwright's HTML report.
  - **On your machine or on a server**: a local agent runs a folder as it is; the server runner
    (`make runner`, [docs/runner.md](docs/runner.md)) runs the branch you pick, freshly pulled from
    Bitbucket, GitHub or GitLab.
  - **Connect in minutes**: `testcli init` writes a `testharbor.toml` for Playwright or pytest,
    then `testcli agent` runs in the tests' folder. The Autotests tab has a step-by-step guide.
  - **Run autotests from TestHarbor**: all of them, selected cases or a run's failed cases.
    `testcli agent` runs them on the machine with the tests, streams the output and uploads
    the results into the run. The agent can offer run options (environment, roles, browser…) that are
    chosen in the dialog and reach its command as environment variables.
  - The agent can send a **catalog of its tests**. After a preview they become cases, or get linked to
    similar manual cases instead of duplicating them. The description, preconditions, steps and expected
    result come from the code (docstrings, comments, `test.step` titles, annotations, pytest-bdd
    scenarios), and new or changed cases wait in **Pending review**. Single tests then run by selecting
    their cases.
  - Results carry their **configuration** (a role, a browser), so one case can show a result per
    role or browser in the same run.
  - A pytest plugin with a `@pytest.mark.case("C142")` marker.
- **Backups.** Daily database and report backups, each checked by a test restore, plus a dump before
  every update that changes the schema (see [docs/deployment.md](docs/deployment.md)).
- **Team accounts.** Testers are invited with one-time links. There are two roles, Admin and
  Tester. Passwords are hashed with argon2id, sign-ins are locked after repeated failures, and
  sessions can be revoked instantly. Results record who executed them.
- **Simple to run.** One `docker compose up` for local use, and HTTPS through Caddy on your own
  server (see [docs/deployment.md](docs/deployment.md)).

## Quick start

```sh
git clone https://github.com/mirosgit/testharbor.git
cd testharbor
docker compose up -d --build
```

Create your admin account (the command asks for an email, name and password):

```sh
docker compose exec backend python -m app.manage create-admin
```

Open **http://localhost:3000** and sign in. A demo project with about 30 cases and six weeks of runs is
created on first start, so the dashboard has something to show. Invite your testers from **Settings › Users**.

**On a server for your team**, follow **[docs/deployment.md](docs/deployment.md)**. It covers HTTPS
on your domain, the security checklist, backups and updates.

The API docs are at http://localhost:3000/docs. They are also served directly by the backend at
http://localhost:8000/docs.

### Configuration

Copy `.env.example` to `.env` and adjust the values. Compose picks the file up automatically.

| Variable | Default | |
|---|---|---|
| `SECRET_KEY` | `change-me-please` | Signs session cookies. Set it to a long random string (`openssl rand -hex 32`) |
| `DB_PASSWORD` | `testharbor` | Postgres password. Only applied when the database volume is first created |
| `SEED_DEMO` | `true` | Creates the demo project when the database is empty |
| `FRONTEND_PORT` / `BACKEND_PORT` / `DB_PORT` | `3000` / `8000` / `5433` | Host ports for local use |
| `DOMAIN` | — | Production only: the domain Caddy serves over HTTPS |

User accounts are not configured through environment variables. Create admins with
`python -m app.manage create-admin`, and invite everyone else from the UI.

Data is kept in the `db-data` volume. `docker compose down` keeps your data, while
`docker compose down -v` deletes it.

## Connect your automated tests

1. In TestHarbor, open **Settings › API tokens** and create a token. It acts as you.
2. Link tests to cases. Put the case ID in the test name (`test_login_C142`) or in a `case_id`
   property. With pytest you can use the marker instead:

   ```python
   @pytest.mark.case("C142")
   def test_login(): ...
   ```

   Tests without an ID are matched by the case's **automation key**, for example
   `tests/test_auth.py::test_login`. With `--auto-create`, unmatched tests become new cases.
3. Upload the report from CI:

   ```sh
   pip install "git+https://github.com/mirosgit/testharbor.git#subdirectory=cli"
   export TESTHARBOR_URL=https://testharbor.example.com TESTHARBOR_TOKEN=th_...

   pytest --junitxml=reports/junit.xml
   testcli upload reports/junit.xml --project 1 --run-name "Nightly #123" \
     --branch main --commit abc123 --auto-create
   ```

   Without the CLI, use plain `curl`:

   ```sh
   curl -H "Authorization: Bearer $TESTHARBOR_TOKEN" -F "file=@reports/junit.xml" \
     "$TESTHARBOR_URL/api/projects/1/runs/import-junit?run_name=Nightly&auto_create=true"
   ```

See **[docs/integration.md](docs/integration.md)** for the full matching rules and for Playwright,
Jest, JUnit/TestNG and Cypress setup. Ready-to-copy CI configs:

- [GitHub Actions](docs/ci/github-actions.yml)
- [Bitbucket Pipelines](docs/ci/bitbucket-pipelines.yml)

## Development

```
backend/    FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL, pytest
frontend/   Next.js (App Router), TypeScript, Tailwind, shadcn/ui, TanStack Query
  e2e/      Playwright smoke tests
cli/        testcli + pytest plugin (Python standard library only)
docs/       integration guide, CI examples, PLAN.md (design decisions)
```

Each command below runs in Docker; the `Makefile` has shortcuts for them.

| Command | |
|---|---|
| `make up` | Build and start the stack |
| `make admin` | Create an admin account (interactive) |
| `make test-backend` | Backend tests (94), run in the backend container against `testharbor_test` |
| `make test-cli` | CLI and pytest plugin tests (12) |
| `make e2e` | Playwright smoke tests against the running stack |
| `make junit-samples` | Regenerate the real pytest, Playwright and Surefire JUnit fixtures |

To develop locally without Docker:
- **Backend:** `cd backend && pip install -e ".[dev]"`, then
  `DATABASE_URL=postgresql+asyncpg://testharbor:testharbor@localhost:5433/testharbor uvicorn app.main:app --reload`.
- **Frontend:** `cd frontend && npm install && BACKEND_URL=http://localhost:8000 npm run dev`.

Database changes go through Alembic:

```sh
alembic revision --autogenerate -m "..."
```

A test fails if the models and migrations drift apart.

## Roadmap

- [x] User accounts, Admin and Tester roles, invite links
- [ ] Read-only Viewer role, SSO/OIDC, two-factor authentication, email (SMTP) invites and password resets
- [ ] Audit log of admin actions
- [ ] Case versioning, so results record which version of a case was run
- [ ] Shared steps and case templates
- [ ] Milestones and test plans that group runs
- [ ] Reports: pass-rate trends, flaky test detection, coverage by section
- [ ] Defects linked to Jira, GitHub and GitLab issues
- [ ] Attachments (screenshots, Playwright traces) on results
- [ ] Publish `testharbor-cli` to PyPI, and add an npm reporter for Playwright and Jest
- [ ] Webhooks and Slack notifications when a run finishes

## License

[MIT](LICENSE)
