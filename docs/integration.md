# Connecting automated tests

TestHarbor takes results from any test framework that writes **JUnit XML**. That includes
pytest, Playwright, Jest, JUnit and TestNG (Maven Surefire or Gradle), Cypress, Go
(`go-junit-report`), .NET (`JunitXml.TestLogger`) and most others.

```
your tests ──► junit.xml ──► testcli upload ──► POST /api/projects/{id}/runs/import-junit ──► CI run
```

Each upload creates a test run with `source = ci`, branch, commit and build URL. Every test in
the report is linked to a test case. The result's status, duration, error message and stack trace
are stored as that case's result in the run.

## 1. Create an API token

Open **Settings › API tokens › New token**. The token acts as you, with your role. Copy it, because it is only shown once. Store it
as a secret in your CI. Tokens are sent as `Authorization: Bearer <token>`.

## 2. Install the CLI

The CLI uses only the Python standard library (Python ≥ 3.9):

```sh
pip install "git+https://github.com/mirosgit/testharbor.git#subdirectory=cli"
# or, from a checkout of this repo:
pip install ./cli
```

It reads its configuration from environment variables:

| Variable | Meaning |
|---|---|
| `TESTHARBOR_URL` | Base URL, for example `https://testharbor.example.com` (the frontend address) |
| `TESTHARBOR_TOKEN` | API token |
| `TESTHARBOR_PROJECT` | Default for `--project` (optional) |

## 3. Link tests to cases

For every `<testcase>` in the report, TestHarbor tries these in order:

1. **Case ID.** It first looks for a `case_id` property (several ids can be comma-separated). If there
   is none, it looks for `C123` in the test name. The ID must be at the start of the name or come
   after a non-alphanumeric character, so `test_login_C142`, `C142 logs in` and `[C142] logs in`
   all match. `TC142` does not match, and neither does lowercase `c142`.
2. **automation_key.** A case matches if its *Automation key* field equals the test's key. The keys
   it tries, in order:
   - an `automation_key` property (the pytest plugin writes the node id here)
   - `classname::name`
   - `classname.name`
   - the pytest path form `tests/test_auth.py::TestClass::test_name`, rebuilt from pytest's dotted
     classname
   - `file::name`
   - the bare test name
3. **Auto-create.** With `--auto-create` (`auto_create=true` in the API), each unmatched test becomes
   a new case in the **Unsorted** suite, section **Automated**. The new case is set to
   `automation_status = automated` and its automation key is filled in. The next upload then matches
   it by key, so you can move the case anywhere in the tree afterwards.

A test that matches nothing is listed under `unmatched` in the response, together with the reason.
No result is stored for it.

### pytest

The CLI package includes a pytest plugin, which is enabled automatically once it is installed:

```python
import pytest

@pytest.mark.case("C142")
def test_login(): ...

@pytest.mark.case("C142", "C143")      # one test covers two cases
def test_login_and_logout(): ...

def test_signup_C150(): ...             # an ID in the name works without the plugin
```

```sh
pytest --junitxml=reports/junit.xml
```

The plugin writes `case_id` and `automation_key` (the node id, for example
`tests/test_auth.py::test_login`) as JUnit properties. If you paste a node id into a case's
*Automation key* field, that case is linked without needing a marker. To turn the plugin off, run
with `-p no:testharbor`.

> When a parametrized test (`test_x[a]`, `test_x[b]`) maps to one case, every result is stored. The
> **worst** status becomes the case's current status, so a failure is never hidden by a later pass.

### Playwright

Put the ID in the title, or use an annotation and let the reporter embed it as a property:

```ts
// playwright.config.ts
reporter: [["junit", { outputFile: "results/junit.xml", embedAnnotationsAsProperties: true }]],

// tests
test("C142 login with valid credentials", async ({ page }) => { ... });
test("wrong password", { annotation: { type: "case_id", description: "C143" } }, async ({ page }) => { ... });
```

#### Links to Playwright's HTML report

Upload Playwright's **JSON** report instead of (or as well as) JUnit. It carries each test's id, so
every case in the run links straight to that test's page in the HTML report
(`index.html#?testId=…`). Test names, case IDs and automation keys work the same as with JUnit, and
`@C142` tags are read as case IDs too.

```ts
// playwright.config.ts
reporter: [
  ["html", { open: "never" }],
  ["json", { outputFile: "reports/results.json" }],
],
```

```sh
testcli upload reports/results.json --report-url "https://ci.example.com/artifacts/playwright-report/index.html"
# or: curl ... -F "file=@reports/results.json" ".../runs/import-junit?report_url=https%3A%2F%2F…"
```

`--report-url` (`report_url` in the API, `TESTHARBOR_REPORT_URL` for the CLI) is where the HTML report
is published: a CI artifact, S3, GitHub Pages, or `npx playwright show-report` locally. You can set or
change it later on the run page (**⋯ › Report link…**), and the per-test links follow it. With
JUnit from other tools, a `report_url` / `link` property holding an absolute URL is used as that
test's link.

### Jest

Use [`jest-junit`](https://github.com/jest-community/jest-junit) and put the ID in the test title:
`it("C142 logs in", ...)`.

```sh
npx jest --reporters=default --reporters=jest-junit   # writes junit.xml
```

### JUnit 5 / TestNG (Maven Surefire, Gradle)

Put the ID at the end of the method name. Reports are written to `target/surefire-reports/*.xml`
or `build/test-results/test/*.xml`.

```java
@Test void declinedCard_C143() { ... }
```

Exceptions (`<error>`) are stored as **failed**, with an `[error]` prefix on the message.

### Cypress

Use `mocha-junit-reporter` and put the ID in the test title: `it("C142 logs in", ...)`.

## 4. Upload

```sh
testcli upload reports/junit.xml --project 1 \
  --run-name "Nightly #123" --branch main --commit abc123 --auto-create
```

- You can pass several files, globs (`'reports/**/*.xml'`) or directories (all `*.xml` files
  inside). They are uploaded together as **one** run.
- In GitHub Actions, Bitbucket Pipelines, GitLab CI and Jenkins, the branch, commit, build URL and
  a default run name (`GitHub Actions #57`) are detected automatically. Flags override them.
- `--run-id 42` adds the results to an existing open run instead of creating a new one.
- `--fail-on-unmatched` exits with code 3 if any test matched no case. This is useful for keeping
  the link between tests and cases complete.
- `--json` prints the raw API response.

Output:

```
Uploaded 1 file(s), 10 tests -> run #7 "Nightly #123"
  matched: 8  created: 2  unmatched: 0  (2 failed, 7 passed, 1 skipped)
  https://testharbor.example.com/projects/1/runs/7
```

Without the CLI, you can upload with `curl`:

```sh
curl -fsS -H "Authorization: Bearer $TESTHARBOR_TOKEN" \
  -F "file=@reports/junit.xml" \
  "$TESTHARBOR_URL/api/projects/1/runs/import-junit?run_name=Nightly&branch=main&auto_create=true"
```

### Status mapping

| JUnit | TestHarbor |
|---|---|
| `<failure>` | failed |
| `<error>` | failed (message prefixed with `[error]`) |
| `<skipped>` | skipped |
| no child element | passed |

`system-out` and `system-err` are appended to the stored stack trace / log. Each of these fields is
limited to 64 KB.

## 5. CI examples

- [GitHub Actions](ci/github-actions.yml)
- [Bitbucket Pipelines](ci/bitbucket-pipelines.yml)

Always upload **even when tests fail**. In GitHub Actions use `if: ${{ !cancelled() }}`. In
Bitbucket use `after-script`.

For parallel or sharded jobs, save each shard's XML as an artifact. Then upload all of them from a
single final job with `testcli upload 'reports/**/*.xml'`, so they end up in one run.

## Troubleshooting

- **`HTTP 401`.** The token is wrong or has been revoked. Check `TESTHARBOR_TOKEN`.
- **Everything is unmatched.** Check that the case IDs belong to the project passed in `--project`.
  IDs from other projects are ignored and reported as unmatched.
- **Duplicate cases after auto-create.** This happens when test names change, for example renamed
  tests or new parametrize ids. Either link those tests with a case ID, or update the case's
  automation key.
