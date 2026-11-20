#!/bin/sh
# Secrets come from the read-only /secrets folder (runner-secrets/ next to docker-compose.yml):
#   tests.env   the tests' own .env (passwords of the test environment…), copied into every checkout
#   files/      other secret files, copied into every checkout at the same paths (config/credentials.ini…)
#   ssh/        an SSH key for git, if the repository URL is ssh (git@bitbucket.org:team/repo.git)
set -e
if [ -f /secrets/tests.env ]; then
  export TESTHARBOR_TESTS_ENV=/secrets/tests.env
fi
if [ -d /secrets/files ]; then
  export TESTHARBOR_SECRET_FILES=/secrets/files
fi
if [ -d /secrets/ssh ]; then
  mkdir -p /root/.ssh && cp /secrets/ssh/* /root/.ssh/ && chmod 700 /root/.ssh && chmod 600 /root/.ssh/*
fi
exec testcli agent "$@"
