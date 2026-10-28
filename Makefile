# Developer entry points. Each recipe line is a single plain command, so it runs under sh (CI)
# and under Windows (GNU make from ezwinports).
COMPOSE := docker compose

.PHONY: all setup lint format test up down ps logs verify seed record deploy-bpmn workers e2e eval metrics readme

all: lint test

setup:
	uv sync --locked

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest

# Start Camunda + vcsim, then wait until every endpoint answers from the host.
up:
	$(COMPOSE) up -d
	uv run python -m stack.health --timeout 300

# Stop the stack and keep its volumes (use `docker compose down -v` to wipe the data).
down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps -a

logs:
	$(COMPOSE) logs --tail 200

# Read-only check of the ServiceNow and Jira credentials in .env.
verify:
	uv run python -m integrations.verify

# Create the NetCo catalog item if needed and order 5 synthetic requests in ServiceNow.
seed:
	uv run python -m integrations.seed

# Re-record the API cassettes against the real instances (creates test records there).
record: export CASSETTE_RECORD = 1
record:
	uv run pytest -m recorded

# Targets of later phases (see PLAN.md).
deploy-bpmn workers e2e:
	$(error make $@ arrives in phase P2)

eval:
	$(error make $@ arrives in phase P3)

metrics:
	$(error make $@ arrives in phase P6)

readme:
	$(error make $@ arrives in phase P8)
