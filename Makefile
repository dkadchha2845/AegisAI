# AegisAI — common tasks.
#
#   make gates     the four checks that must pass before anything is "done"
#   make up        start the dev stack (Postgres, Neo4j, Qdrant, Redis)
#   make down      stop it, keep data
#   make reset     stop it and DESTROY all data
#   make status    what is running, and what the API thinks of it

COMPOSE   := docker compose -f infra/compose/dev.yml
PY        := .venv/bin/python
WEB       := --prefix apps/web

.DEFAULT_GOAL := help
.PHONY: help gates check lint types cov audit test contract typecheck build up down reset status logs api web install verify-checkpoint eval

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- the gates --

gates: test contract typecheck build ## Run all four gates
	@echo "\n✓ all four gates green"

check: lint types gates ## Everything CI runs
	@echo "\n✓ lint + types + all four gates green"

lint: ## Ruff (curated toward defects; see pyproject.toml)
	.venv/bin/ruff check .

types: ## mypy on the agent layer
	.venv/bin/mypy

cov: ## Tests with the coverage gate
	$(PY) -m pytest services/api/tests --cov --cov-report=term

audit: ## Dependency vulnerability scan
	.venv/bin/pip-audit -r services/api/requirements.txt || true
	npm audit --audit-level=high $(WEB) || true

test: ## Backend test suite
	$(PY) -m pytest services/api/tests -q

contract: ## Pydantic <-> TypeScript contract check
	$(PY) schema/check_contract.py

typecheck: ## Frontend typecheck
	npm run typecheck $(WEB)

build: ## Frontend production build
	npm run build $(WEB)

verify-checkpoint: ## Check the on-disk model against the recorded metrics
	$(PY) -m ml.evaluation.manifest

eval: ## Re-run the promotion gate and refresh the manifest (~1 min, needs the checkpoint)
	$(PY) ml/evaluation/eval_backends.py

# ------------------------------------------------------------------- infra --

up: ## Start the dev stack and wait for every service to report healthy
	$(COMPOSE) up -d --wait
	@echo "\n✓ stack healthy"
	@$(COMPOSE) ps

down: ## Stop the stack, keep volumes
	$(COMPOSE) down

reset: ## Stop the stack and DESTROY all data
	@printf "This deletes all Postgres, Neo4j, Qdrant and Redis data. Type 'yes' to continue: " \
	  && read ans && [ "$$ans" = "yes" ] || (echo "aborted"; exit 1)
	$(COMPOSE) down -v

logs: ## Tail stack logs
	$(COMPOSE) logs -f --tail=100

status: ## Show container health and what the API can actually reach
	@$(COMPOSE) ps 2>/dev/null || echo "(compose not running)"
	@echo "\n--- as seen by the API ---"
	@$(PY) -c "from services.api.stores.probe import probe_all; import json; print(json.dumps(probe_all(force=True), indent=2))"

# --------------------------------------------------------------- run local --

api: ## Run the API (reload-dir set, or reloads wipe the ephemeral DB)
	$(PY) -m uvicorn services.api.main:app --reload \
	  --reload-dir services --reload-dir schema --port 8000

web: ## Run the frontend dev server
	npm run dev $(WEB)

install: ## Install backend deps (including the editable aegis-core) + frontend
	$(PY) -m pip install -r services/api/requirements.txt
	npm ci $(WEB)
