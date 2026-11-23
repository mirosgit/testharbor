# Convenience targets. Everything runs in Docker; no local Python/Node needed.
.PHONY: up down logs admin seed test test-backend test-cli e2e junit-samples prod-up prod-admin backup backups backup-check restore

PROD = docker compose -f docker-compose.yml -f docker-compose.prod.yml

up:            ## build and start db + backend + frontend + daily backups
	mkdir -p backups
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
	docker run --rm -v "$(CURDIR)/cli:/src:ro" python:3.12 sh -c \
	  'cp -r /src /tmp/cli && cd /tmp/cli && rm -rf .venv && pip install -q -e ".[dev]" && pytest -q'

E2E_EMAIL ?= e2e-admin@testharbor.local

e2e:           ## Playwright smoke tests against the running stack (uses a throwaway-password admin)
	@E2E_PASSWORD=$$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24); \
	printf '%s\n' "$$E2E_PASSWORD" | docker compose exec -T backend python -m app.manage create-admin \
	  --email $(E2E_EMAIL) --name "E2E Admin" --password-stdin --update >/dev/null && \
	E2E_EMAIL=$(E2E_EMAIL) E2E_PASSWORD="$$E2E_PASSWORD" docker compose --profile e2e run --rm e2e

runner:        ## start the test runner (RUNNER_* in .env, see docs/runner.md)
	@test -n "$$(grep -E '^RUNNER_TOKEN=.+' .env 2>/dev/null)" || { echo "Set RUNNER_TOKEN in .env first (make runner-token)"; exit 1; }
	mkdir -p runner-secrets && chmod 700 runner-secrets
	docker compose --profile runner up -d --build runner
	@echo "Logs: docker compose logs -f runner"

prod-runner:   ## production: start the test runner next to the production stack
	@test -n "$$(grep -E '^RUNNER_TOKEN=.+' .env 2>/dev/null)" || { echo "Set RUNNER_TOKEN in .env first (make prod-runner-token)"; exit 1; }
	mkdir -p runner-secrets && chmod 700 runner-secrets
	$(PROD) --profile runner up -d --build runner

prod-runner-token: ## production: print a new API token for the test runner
	$(PROD) exec -T backend python -m app.manage create-agent-token --quiet

runner-token:  ## print a new API token for the test runner
	docker compose exec -T backend python -m app.manage create-agent-token --quiet

prod-up:       ## production: HTTPS via Caddy (needs DOMAIN, SECRET_KEY, DB_PASSWORD in .env)
	mkdir -p backups
	$(PROD) up -d --build

prod-admin:    ## production: create an admin account
	$(PROD) exec backend python -m app.manage create-admin

backup:        ## a checked backup right now, into backups/manual (daily ones are made by the backup service)
	./deploy/backup.sh

backups:       ## list the backups
	docker compose run --rm --no-deps -T backup sh /opt/backup/backup.sh list

backup-check:  ## restore the newest daily backup into a scratch database and count its rows
	docker compose run --rm --no-deps -T backup sh /opt/backup/backup.sh verify $(or $(FILE),latest)

restore:       ## put a backup back: make restore FILE=latest (or a path under backups/); see deploy/restore.sh
	./deploy/restore.sh $(or $(FILE),latest)

junit-samples: ## regenerate real JUnit XML fixtures (pytest, Playwright, Surefire)
	backend/tests/fixtures/junit/generators/generate.sh
