# Developer entry points. Each recipe line is a single plain command, so it runs under sh (CI)
# and under Windows (GNU make from ezwinports).
COMPOSE := docker compose
KUBECTL := kubectl --context kind-netco

.PHONY: all setup lint format test up down ps logs kind-up kind-down verify seed record deploy-bpmn workers e2e eval metrics readme

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

# kind lab cluster with the NetCo network zones and their probes.
kind-up:
	kind create cluster --config infra/kind/cluster.yaml --wait 180s
	$(KUBECTL) apply -f infra/kind/zones.yaml
	$(KUBECTL) wait --for=condition=Ready pod -l app.kubernetes.io/name=probe -A --timeout=240s

kind-down:
	kind delete cluster --name netco

# Deploy the process, the decision table and the forms to the local engine.
deploy-bpmn:
	uv run python -m scenario.deploy

# Job workers and ServiceNow poller (Ctrl+C to stop). Needs `make up kind-up deploy-bpmn`.
workers:
	uv run python -m workers

# End-to-end scenario on the real tools; starts its own workers. Do not run `make workers` meanwhile.
e2e:
	uv run python -m scenario.e2e

# Targets of later phases (see PLAN.md).
eval:
	$(error make $@ arrives in phase P3)

metrics:
	$(error make $@ arrives in phase P6)

readme:
	$(error make $@ arrives in phase P8)
