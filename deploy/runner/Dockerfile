# The test runner: `testcli agent --repo …` on a server, with what test projects usually need:
# git, Node with Playwright's system libraries, and any Python through uv.
#   docker compose --profile runner up -d --build runner      (settings: RUNNER_* in .env)
FROM mcr.microsoft.com/playwright:v1.65.1-noble

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/
RUN apt-get update \
 && apt-get install -y --no-install-recommends git openssh-client ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv's own Python and tools live in the image; dependencies, Pythons the tests ask for and
# browsers go to /root/.cache, a volume, so they are downloaded once and reused by every run.
ENV UV_TOOL_DIR=/opt/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_PYTHON_INSTALL_DIR=/root/.cache/uv-python \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright \
    GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" \
    PYTHONUNBUFFERED=1

COPY cli /opt/testcli
RUN UV_PYTHON_INSTALL_DIR=/opt/uv/python uv tool install --python 3.12 /opt/testcli && testcli --version

COPY deploy/runner/entrypoint.sh /usr/local/bin/runner-entrypoint
RUN chmod +x /usr/local/bin/runner-entrypoint
WORKDIR /work
ENTRYPOINT ["runner-entrypoint"]
