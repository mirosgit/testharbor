# testharbor-cli

A command-line uploader and pytest plugin for [TestHarbor](../README.md). It uses only the Python
standard library (Python ≥ 3.9), so it installs in about a second in CI.

```sh
pip install "git+https://github.com/mirosgit/testharbor.git#subdirectory=cli"

export TESTHARBOR_URL=https://testharbor.example.com
export TESTHARBOR_TOKEN=th_...           # Settings › API tokens

pytest --junitxml=reports/junit.xml
testcli upload reports/junit.xml --project 1 --run-name "Nightly #123" \
  --branch main --commit abc123 --auto-create
```

## `testcli upload`

| Option | |
|---|---|
| `FILES...` | JUnit XML files, globs (`'reports/**/*.xml'`) or directories. They are uploaded as one run |
| `--project`, `-p` | Project id. Can also be set with `TESTHARBOR_PROJECT` |
| `--run-name`, `-n` | Run name. Defaults to `<CI name> #<build>` in CI, otherwise a timestamp |
| `--branch`, `--commit`, `--build-url` | Detected automatically in GitHub Actions, Bitbucket, GitLab and Jenkins |
| `--auto-create` | Create cases for unmatched tests, in Unsorted › Automated |
| `--run-id` | Add to an existing open run |
| `--fail-on-unmatched` | Exit with code 3 if any test matched no case |
| `--json` | Print the raw API response |
| `--url`, `--token` | Override `TESTHARBOR_URL` and `TESTHARBOR_TOKEN` |

Exit codes:
- `0`: success
- `1`: upload or HTTP error
- `2`: usage or configuration error
- `3`: some tests were unmatched (only with `--fail-on-unmatched`)

## pytest plugin

The plugin is enabled automatically when the package is installed:

```python
@pytest.mark.case("C142")
def test_login(): ...
```

It writes `case_id` and `automation_key` (the pytest node id) into the JUnit XML report as
properties. To turn it off, run with `-p no:testharbor`.

See [docs/integration.md](../docs/integration.md) for how tests are matched to cases and for CI
examples.

## Development

```sh
pip install -e ".[dev]" && pytest
```
