# Convenience targets. Everything runs in Docker; no local Python/Node needed.
.PHONY: up down logs admin seed test test-backend test-cli e2e junit-samples

up:            ## build and start db + backend + frontend
	docker compose up -d --build

down:          ## stop (keeps the database volume)
	docker compose down

logs:
	docker compose logs -f backend frontend

admin:         ## create an admin account (interactive)
	docker compose exec backend python -m app.manage create-admin

seed:          ## add the demo project again
	docker compose exec backend python -m app.seed

test: test-backend test-cli

test-backend:  ## pytest against the testharbor_test database
	docker compose exec backend pytest -q

test-cli:
	docker run --rm -v "$(CURDIR)/cli:/src:ro" python:3.12-slim sh -c \
	  'cp -r /src /tmp/cli && cd /tmp/cli && rm -rf .venv && pip install -q -e ".[dev]" && pytest -q'

E2E_EMAIL ?= e2e-admin@testharbor.local

e2e:           ## Playwright smoke tests against the running stack (uses a throwaway-password admin)
	@E2E_PASSWORD=$$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24); \
	printf '%s\n' "$$E2E_PASSWORD" | docker compose exec -T backend python -m app.manage create-admin \
	  --email $(E2E_EMAIL) --name "E2E Admin" --password-stdin --update >/dev/null && \
	E2E_EMAIL=$(E2E_EMAIL) E2E_PASSWORD="$$E2E_PASSWORD" docker compose --profile e2e run --rm e2e

junit-samples: ## regenerate real JUnit XML fixtures (pytest, Playwright, Surefire)
	backend/tests/fixtures/junit/generators/generate.sh
