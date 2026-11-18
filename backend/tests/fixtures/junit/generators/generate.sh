#!/bin/sh
# Regenerate the real JUnit XML samples in ../ by running the sample suites in containers
# (neutral hostname and paths, so nothing about the build machine leaks into the files).
# Usage: backend/tests/fixtures/junit/generators/generate.sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(dirname "$HERE")
REPO=$(cd "$HERE/../../../../.." && pwd)
UIDGID="$(id -u):$(id -g)"

echo "== pytest (with testharbor plugin, xunit2) and without plugin (xunit1)"
docker run --rm --hostname ci-runner -u "$UIDGID" -e HOME=/tmp \
  -v "$HERE/pytest:/src:ro" -v "$REPO/cli:/cli:ro" -v "$OUT:/out" python:3.12-slim sh -c '
  cp -r /src /tmp/work && mkdir /tmp/cli && cp -r /cli/pyproject.toml /cli/README.md /cli/src /tmp/cli && cd /tmp/work &&
  pip install -q --no-warn-script-location --user /tmp/cli pytest >/dev/null &&
  timeout 60 python -m pytest -q -o junit_family=xunit2 -o junit_logging=system-out --junitxml=/out/pytest-xunit2.xml || true;
  timeout 60 python -m pytest -q -p no:testharbor -o junit_family=xunit1 --junitxml=/out/pytest-xunit1-noplugin.xml || true'

echo "== Playwright"
docker run --rm --hostname ci-runner -u "$UIDGID" -e HOME=/tmp --ipc=host \
  -v "$HERE/playwright:/src:ro" -v "$OUT:/out" mcr.microsoft.com/playwright:v1.65.1-noble sh -c '
  cp -r /src /tmp/work && cd /tmp/work && npm install --silent --no-audit --no-fund >/dev/null &&
  npx playwright test || true; cp results/junit.xml /out/playwright.xml
  cp results/results.json /out/playwright.json'

echo "== Maven Surefire (JUnit 5)"
docker run --rm --hostname ci-runner -u "$UIDGID" -e HOME=/tmp -e MAVEN_CONFIG=/tmp/.m2 \
  -v "$HERE/maven:/src:ro" -v "$OUT:/out" maven:3.9-eclipse-temurin-21 sh -c '
  cp -r /src /tmp/work && cd /tmp/work && mvn -q -B -Dmaven.repo.local=/tmp/.m2/repository test || true;
  cp target/surefire-reports/TEST-com.example.shop.CheckoutTest.xml /out/surefire-junit5.xml'

ls -l "$OUT"/*.xml
