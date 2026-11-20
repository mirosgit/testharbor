# The test runner on a server

The runner runs your autotests from TestHarbor on a git branch you pick when starting a run. For every run it
fetches the repository and checks the branch out at its latest commit, in a fresh folder. It then installs what the
tests need (`setup`), runs the selected tests, sends the results and removes the folder.

It is `testcli agent --repo …` in a Docker image that has git, Node with Playwright's system libraries, and uv for
any Python version. Dependencies, Pythons and browsers are cached in a volume, so only the first run downloads them.

To run tests from a folder on your own machine instead, see **Autotests › Connect autotests › On my computer**.

## 1. The test repository

Commit a `testharbor.toml` (`testcli init` writes one) with a `setup` that prepares a clean checkout:

```toml
framework = "pytest"                      # or playwright / custom
setup = ["uv sync --locked", "uv run playwright install chromium"]
# Playwright (JS): setup = ["npm ci", "npx playwright install chromium"]
```

The file may sit in a subfolder of the repository; the runner finds it. If there are several, set
`RUNNER_REPO_PATH`. The `secrets` command of the file is for local agents only, and the runner skips it.

## 2. Access to the repository

Create a read-only token:

- **Bitbucket:** Repository settings › Access tokens, with *Repositories: Read*. Its user name is
  `x-token-auth`, the default. For an app password, also set `RUNNER_GIT_USER` to your Bitbucket user name.
- **GitHub:** a fine-grained token with *Contents: read*.
- **GitLab:** a project access token with *read_repository*.

The runner gives the token to git through `GIT_ASKPASS`. It never shows up in a URL, a log or `git remote -v`.

**SSH instead of a token:** use an `ssh://` or `git@…:` URL and put the private key into `runner-secrets/ssh/`
(for example `id_ed25519`).

## 3. Settings

In the TestHarbor folder on the server:

```sh
make runner-token            # prints a new TestHarbor API token (production stack: make prod-runner-token)
```

Then add to `.env`:

```sh
RUNNER_TOKEN=th_...
RUNNER_PROJECT=1                                         # the number in /projects/<id>/…
RUNNER_REPO=https://bitbucket.org/your-team/your-tests.git
RUNNER_GIT_TOKEN=...
# optional:
# RUNNER_BRANCH=main            default branch (default: the repository's)
# RUNNER_REPO_PATH=qa           folder of testharbor.toml, if it is not found by itself
# RUNNER_NAME=server            how it is shown in TestHarbor
# RUNNER_GIT_USER=              for Bitbucket app passwords
```

The token belongs to a service user, "Autotests agent" (role Tester), whom nobody signs in as.

## 4. The tests' secrets

Put the tests' own secrets into `runner-secrets/` next to `docker-compose.yml`. The folder is git-ignored and
mounted read-only.

```
runner-secrets/
  tests.env                      becomes .env of every checkout (passwords of the test environment, users…)
  files/config/credentials.ini   files/ is copied into every checkout at the same paths
  ssh/id_ed25519                 only for an SSH repository URL
```

The runner reaches the environments and services the tests use from the server. Checks that need a VPN or credentials
available only on a laptop will fail there; give the server that access, or skip those checks on the server.

## 5. Start

```sh
make runner                      # production stack: make prod-runner
docker compose logs -f runner
```

The runner shows up in TestHarbor as **Server**. On the **Autotests** page, choose **Run on: Server**, pick a branch,
tick the tests and press **Run selected**. The run page shows the checkout, setup and test output live.

## Updating and troubleshooting

- **After updating TestHarbor,** run `make runner` again; it rebuilds the image.
- **"branch … is not in …":** the branch wasn't pushed. The list of branches refreshes every minute.
- **"no testharbor.toml in this branch":** commit one, or set `RUNNER_REPO_PATH`.
- **Authentication failed:** check `RUNNER_GIT_TOKEN`, and `RUNNER_GIT_USER` for app passwords.
- **Start from scratch:** `docker compose --profile runner down` and `docker volume rm testharbor_runner-work`.
